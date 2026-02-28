"""
Authentication API Endpoints
Login, user management (admin-only), and password change
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from collections import defaultdict
from time import time
import logging

from app.database import get_db
from app.models.user import User
from app.schemas.user import (
    AdminCreateUser, UserLogin, UserResponse, Token, ChangePassword
)
from app.core.security import hash_password, verify_password, create_access_token
from app.core.deps import get_current_user, get_admin_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Simple in-memory rate limiter: max 10 failed attempts per IP per 15 minutes
_login_attempts: dict = defaultdict(list)
_RATE_LIMIT_MAX = 10
_RATE_LIMIT_WINDOW = 900  # 15 minutes


def _check_rate_limit(ip: str):
    now = time()
    attempts = _login_attempts[ip]
    # Remove old attempts outside the window
    _login_attempts[ip] = [t for t in attempts if now - t < _RATE_LIMIT_WINDOW]
    if len(_login_attempts[ip]) >= _RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos de login. Espera 15 minutos."
        )


@router.post("/login", response_model=Token)
async def login(data: UserLogin, request: Request, db: Session = Depends(get_db)):
    """Login with username and password"""
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)

    user = db.query(User).filter(User.username == data.username).first()

    if not user or not verify_password(data.password, user.password_hash):
        _login_attempts[client_ip].append(time())
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contrasena incorrectos"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario desactivado"
        )

    token = create_access_token({"sub": str(user.id)})
    safe_username = user.username.replace("
", "").replace("", "")
    logger.info(f"User logged in: {safe_username}")

    return Token(
        access_token=token,
        must_change_password=user.must_change_password,
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user info"""
    return UserResponse.model_validate(current_user)


@router.post("/change-password")
async def change_password(
    data: ChangePassword,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change current user's password"""
    if not verify_password(data.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contrasena actual incorrecta"
        )

    if len(data.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La nueva contrasena debe tener al menos 6 caracteres"
        )

    current_user.password_hash = hash_password(data.new_password)
    current_user.must_change_password = False
    db.commit()

    safe_username = current_user.username.replace("
", "").replace("", "")
    logger.info(f"User changed password: {safe_username}")
    return {"message": "Contrasena actualizada correctamente"}


# ── Admin-only endpoints ──────────────────────────────────────


@router.get("/users", response_model=List[UserResponse])
async def list_users(
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """List all users (admin only)"""
    users = db.query(User).order_by(User.id).all()
    return [UserResponse.model_validate(u) for u in users]


@router.post("/users", response_model=UserResponse, status_code=201)
async def create_user(
    data: AdminCreateUser,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Create a new user (admin only)"""
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El nombre de usuario ya existe"
        )

    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El email ya esta registrado"
        )

    if len(data.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contrasena debe tener al menos 6 caracteres"
        )

    user = User(
        username=data.username,
        email=data.email,
        password_hash=hash_password(data.password),
        is_active=True,
        is_admin=False,
        must_change_password=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info(f"Admin created user: {user.username}")
    return UserResponse.model_validate(user)


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Delete a user (admin only, cannot delete self)"""
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes eliminarte a ti mismo"
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )

    db.delete(user)
    db.commit()

    logger.info(f"Admin deleted user: {user.username}")
    return {"message": f"Usuario {user.username} eliminado"}


@router.patch("/users/{user_id}/toggle-active")
async def toggle_user_active(
    user_id: int,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Toggle user active status (admin only)"""
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes desactivarte a ti mismo"
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )

    user.is_active = not user.is_active
    db.commit()

    state = "activado" if user.is_active else "desactivado"
    logger.info(f"Admin toggled user {user.username}: {state}")
    return {"message": f"Usuario {user.username} {state}", "is_active": user.is_active}


@router.patch("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Reset a user's password to a random one (admin only)"""
    from app.database import _generate_password

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )

    new_password = _generate_password(12)
    user.password_hash = hash_password(new_password)
    user.must_change_password = True
    db.commit()

    logger.info(f"Admin reset password for user: {user.username}")
    return {"message": f"Nueva contrasena para {user.username}", "new_password": new_password}
