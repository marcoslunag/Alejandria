"""
Settings API Endpoints
Manage application settings (SMTP, Kindle configuration)
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional
import logging

from app.database import get_db
from app.models.settings import AppSettings
from app.services.kindle_sender import KindleSender
import json
from pathlib import Path

logger = logging.getLogger(__name__)

# Archivo de configuración compartido con el worker KCC
KCC_CONFIG_FILE = Path("/downloads/.kcc_config.json")


def write_kcc_config(profile: str):
    """Escribe la configuración de KCC para que el worker la lea"""
    try:
        config = {
            "profile": profile,
            "format": "MOBI"  # MOBI para Kindle nativo
        }
        KCC_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(KCC_CONFIG_FILE, 'w') as f:
            json.dump(config, f)
        logger.info(f"KCC config updated: profile={profile}, format=MOBI")
    except Exception as e:
        logger.warning(f"Could not write KCC config: {e}")

router = APIRouter(prefix="/settings", tags=["settings"])


# Pydantic schemas
class SettingsResponse(BaseModel):
    kindle_email: Optional[str] = None
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_from_email: Optional[str] = None
    auto_send_to_kindle: bool = False
    is_smtp_configured: bool = False
    is_kindle_configured: bool = False
    # Amazon settings
    amazon_email: Optional[str] = None
    amazon_device_name: Optional[str] = None
    kindle_sync_method: str = "auto"
    is_amazon_configured: bool = False
    can_send_large_files: bool = False
    # KCC settings
    kcc_profile: str = "KPW5"
    # STK device settings
    stk_device_serial: Optional[str] = None
    stk_device_name: Optional[str] = None

    class Config:
        from_attributes = True


class SettingsUpdate(BaseModel):
    kindle_email: Optional[str] = None
    smtp_server: Optional[str] = "smtp.gmail.com"
    smtp_port: Optional[int] = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from_email: Optional[str] = None
    auto_send_to_kindle: Optional[bool] = False
    # Amazon settings
    amazon_email: Optional[str] = None
    amazon_password: Optional[str] = None
    amazon_device_name: Optional[str] = None
    kindle_sync_method: Optional[str] = "auto"
    # KCC settings
    kcc_profile: Optional[str] = None
    # STK device settings
    stk_device_serial: Optional[str] = None
    stk_device_name: Optional[str] = None


class TestSmtpRequest(BaseModel):
    test_email: Optional[str] = None  # If not provided, use kindle_email


def get_or_create_settings(db: Session) -> AppSettings:
    """Get settings from DB or create default"""
    settings = db.query(AppSettings).first()
    if not settings:
        settings = AppSettings()
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


@router.get("", response_model=SettingsResponse)
async def get_settings(db: Session = Depends(get_db)):
    """
    Get current application settings
    Note: Passwords are not returned for security
    """
    settings = get_or_create_settings(db)

    return SettingsResponse(
        kindle_email=settings.kindle_email,
        smtp_server=settings.smtp_server,
        smtp_port=settings.smtp_port,
        smtp_user=settings.smtp_user,
        smtp_from_email=settings.smtp_from_email,
        auto_send_to_kindle=settings.auto_send_to_kindle,
        is_smtp_configured=settings.is_smtp_configured,
        is_kindle_configured=settings.is_kindle_configured,
        # Amazon settings
        amazon_email=settings.amazon_email,
        amazon_device_name=settings.amazon_device_name,
        kindle_sync_method=settings.kindle_sync_method or "auto",
        is_amazon_configured=settings.is_amazon_configured,
        can_send_large_files=settings.can_send_large_files,
        # KCC settings
        kcc_profile=settings.kcc_profile or "KPW5",
        # STK device settings
        stk_device_serial=settings.stk_device_serial,
        stk_device_name=settings.stk_device_name
    )


@router.post("", response_model=SettingsResponse)
async def save_settings(data: SettingsUpdate, db: Session = Depends(get_db)):
    """
    Save application settings
    """
    settings = get_or_create_settings(db)

    # Update SMTP/Kindle fields
    if data.kindle_email is not None:
        settings.kindle_email = data.kindle_email

    if data.smtp_server is not None:
        settings.smtp_server = data.smtp_server

    if data.smtp_port is not None:
        settings.smtp_port = data.smtp_port

    if data.smtp_user is not None:
        settings.smtp_user = data.smtp_user

    if data.smtp_password is not None:
        settings.smtp_password = data.smtp_password

    if data.smtp_from_email is not None:
        settings.smtp_from_email = data.smtp_from_email

    if data.auto_send_to_kindle is not None:
        settings.auto_send_to_kindle = data.auto_send_to_kindle

    # Update Amazon fields
    if data.amazon_email is not None:
        settings.amazon_email = data.amazon_email

    if data.amazon_password is not None:
        settings.amazon_password = data.amazon_password

    if data.amazon_device_name is not None:
        settings.amazon_device_name = data.amazon_device_name

    if data.kindle_sync_method is not None:
        settings.kindle_sync_method = data.kindle_sync_method

    if data.kcc_profile is not None:
        settings.kcc_profile = data.kcc_profile
        # Escribir configuración para el worker KCC
        write_kcc_config(settings.kcc_profile)

    # STK device settings
    if data.stk_device_serial is not None:
        settings.stk_device_serial = data.stk_device_serial
    if data.stk_device_name is not None:
        settings.stk_device_name = data.stk_device_name

    db.commit()
    db.refresh(settings)

    logger.info("Settings updated successfully")

    return SettingsResponse(
        kindle_email=settings.kindle_email,
        smtp_server=settings.smtp_server,
        smtp_port=settings.smtp_port,
        smtp_user=settings.smtp_user,
        smtp_from_email=settings.smtp_from_email,
        auto_send_to_kindle=settings.auto_send_to_kindle,
        is_smtp_configured=settings.is_smtp_configured,
        is_kindle_configured=settings.is_kindle_configured,
        # Amazon settings
        amazon_email=settings.amazon_email,
        amazon_device_name=settings.amazon_device_name,
        kindle_sync_method=settings.kindle_sync_method or "auto",
        is_amazon_configured=settings.is_amazon_configured,
        can_send_large_files=settings.can_send_large_files,
        # KCC settings
        kcc_profile=settings.kcc_profile or "KPW5",
        # STK device settings
        stk_device_serial=settings.stk_device_serial,
        stk_device_name=settings.stk_device_name
    )


@router.post("/test-smtp")
async def test_smtp_connection(
    data: Optional[TestSmtpRequest] = None,
    db: Session = Depends(get_db)
):
    """
    Test SMTP connection with current settings
    Optionally sends a test email if test_email is provided
    """
    settings = get_or_create_settings(db)

    if not settings.is_smtp_configured:
        raise HTTPException(
            status_code=400,
            detail="SMTP not fully configured. Please fill in all SMTP fields."
        )

    try:
        sender = KindleSender(
            smtp_server=settings.smtp_server,
            smtp_port=settings.smtp_port,
            smtp_user=settings.smtp_user,
            smtp_password=settings.smtp_password,
            from_email=settings.smtp_from_email
        )

        # Test connection
        if sender.test_connection():
            return {
                "ok": True,
                "message": "SMTP connection successful"
            }
        else:
            raise HTTPException(
                status_code=400,
                detail="SMTP connection failed. Check credentials."
            )

    except Exception as e:
        logger.error(f"SMTP test failed: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"SMTP test failed: {str(e)}"
        )


@router.post("/test-amazon")
async def test_amazon_connection(db: Session = Depends(get_db)):
    """
    Test Amazon connection for Send to Kindle
    """
    settings = get_or_create_settings(db)

    if not settings.is_amazon_configured:
        raise HTTPException(
            status_code=400,
            detail="Amazon credentials not configured. Please fill in Amazon email and password."
        )

    try:
        from app.services.amazon_kindle_sender import AmazonKindleSender

        sender = AmazonKindleSender(
            amazon_email=settings.amazon_email,
            amazon_password=settings.amazon_password
        )

        result = await sender.test_connection()

        if result['success']:
            return {
                "ok": True,
                "message": result['message']
            }
        else:
            raise HTTPException(
                status_code=400,
                detail=result['message']
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Amazon test failed: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Amazon test failed: {str(e)}"
        )


@router.get("/terabox-status")
async def get_terabox_status():
    """
    Get TeraBox session status
    Shows if authentication is configured and valid
    """
    try:
        from app.services.terabox_session import get_session_manager

        session_mgr = get_session_manager()
        status = session_mgr.get_session_status()

        return {
            "ok": True,
            "is_configured": status.get('has_auth_file', False),
            "is_valid": status.get('is_valid', False),
            "needs_reauth": status.get('needs_reauth', True),
            "expires_at": status.get('expires_at'),
            "time_remaining": status.get('time_remaining'),
            "last_login": status.get('last_login'),
            "cookies_found": status.get('cookies_found', []),
            "cookies_missing": status.get('cookies_missing', []),
            "message": _get_terabox_status_message(status)
        }
    except ImportError:
        return {
            "ok": False,
            "is_configured": False,
            "is_valid": False,
            "needs_reauth": True,
            "message": "TeraBox module not available"
        }
    except Exception as e:
        logger.error(f"Error getting TeraBox status: {e}")
        return {
            "ok": False,
            "is_configured": False,
            "is_valid": False,
            "needs_reauth": True,
            "error": str(e),
            "message": f"Error: {str(e)}"
        }


def _get_terabox_status_message(status: dict) -> str:
    """Genera mensaje de estado legible para TeraBox."""
    if not status.get('has_auth_file'):
        return "No autenticado. Ejecuta el script de autenticación."

    if not status.get('is_valid'):
        missing = status.get('cookies_missing', [])
        return f"Sesión inválida. Faltan cookies: {', '.join(missing)}"

    time_remaining = status.get('time_remaining')
    if time_remaining:
        return f"Sesión activa. Expira en: {time_remaining}"

    return "Sesión activa"


@router.get("/smtp-guide")
async def get_smtp_guide():
    """
    Get Gmail App Password setup guide
    """
    return {
        "title": "Cómo obtener App Password de Gmail",
        "steps": [
            {
                "step": 1,
                "title": "Acceder a tu cuenta de Google",
                "description": "Ve a myaccount.google.com/security"
            },
            {
                "step": 2,
                "title": "Activar verificación en 2 pasos",
                "description": "En la sección 'Cómo inicias sesión en Google', activa la verificación en 2 pasos si aún no está activa"
            },
            {
                "step": 3,
                "title": "Crear contraseña de aplicación",
                "description": "Busca 'Contraseñas de aplicaciones' o ve a myaccount.google.com/apppasswords"
            },
            {
                "step": 4,
                "title": "Generar nueva contraseña",
                "description": "Selecciona 'Correo' como aplicación y 'Otro' como dispositivo. Ponle un nombre como 'Alejandria'"
            },
            {
                "step": 5,
                "title": "Copiar contraseña",
                "description": "Copia la contraseña de 16 caracteres (sin espacios) y pégala en el campo 'App Password' de esta aplicación"
            }
        ],
        "important_notes": [
            "La contraseña de aplicación es diferente a tu contraseña de Google",
            "Si no ves la opción de contraseñas de aplicaciones, asegúrate de tener la verificación en 2 pasos activa",
            "Guarda la contraseña en un lugar seguro, no podrás verla de nuevo en Google"
        ],
        "link": "https://myaccount.google.com/apppasswords"
    }
