"""
Kindle API Endpoints
Send books to Kindle via STK (Send to Kindle API)
Each user has their own isolated STK session.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path
from datetime import datetime
import logging

from app.database import get_db
from app.models.chapter import Chapter
from app.models.user import User
from app.core.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/kindle", tags=["kindle"])


# Pydantic schemas
class SendRequest(BaseModel):
    device_serial: Optional[str] = None


class SendResponse(BaseModel):
    ok: bool
    message: str
    chapter_id: int
    sent_at: Optional[datetime] = None


class STKAuthorizeRequest(BaseModel):
    redirect_url: str


@router.get("/status/{chapter_id}")
async def get_kindle_status(chapter_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get Kindle send status for a chapter."""
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="Tomo not found")

    file_paths = []
    if chapter.converted_path:
        file_paths = [Path(p.strip()) for p in chapter.converted_path.split('|') if p.strip()]

    existing_files = [f for f in file_paths if f.exists()]
    total_size_mb = sum(f.stat().st_size / (1024 * 1024) for f in existing_files)

    return {
        "chapter_id": chapter_id,
        "status": chapter.status,
        "sent_at": chapter.sent_at,
        "has_epub": len(existing_files) > 0,
        "file_count": len(existing_files),
        "file_size_mb": round(total_size_mb, 2)
    }


@router.get("/can-send")
async def check_kindle_configured(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Check if STK is properly configured for the current user"""
    from app.services.stk_kindle_sender import get_stk_sender

    sender = get_stk_sender(current_user.id)
    is_auth = sender.is_authenticated()
    has_device = bool(current_user.stk_device_serial)

    return {
        "configured": is_auth and has_device,
        "authenticated": is_auth,
        "device_configured": has_device,
        "device_name": current_user.stk_device_name if has_device else None,
        "message": "Ready to send" if (is_auth and has_device) else "STK not configured"
    }


# ── STK OAuth2 endpoints ──────────────────────────────────────

@router.get("/stk/status")
async def stk_status(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Check if STK is authenticated for the current user"""
    from app.services.stk_kindle_sender import get_stk_sender

    sender = get_stk_sender(current_user.id)
    is_auth = sender.is_authenticated()

    devices = sender.get_devices() if is_auth else []

    saved_device = None
    if current_user.stk_device_serial:
        saved_device = {
            "serial": current_user.stk_device_serial,
            "name": current_user.stk_device_name
        }

    return {
        "authenticated": is_auth,
        "devices": devices,
        "saved_device": saved_device,
        "message": "Ready to send" if is_auth else "Not authenticated. Use /stk/signin-url to get authorization URL."
    }


@router.get("/stk/signin-url")
async def stk_get_signin_url(current_user: User = Depends(get_current_user)):
    """Get Amazon OAuth2 sign-in URL for the current user"""
    from app.services.stk_kindle_sender import get_stk_sender

    sender = get_stk_sender(current_user.id)
    url = sender.get_signin_url()

    return {
        "signin_url": url,
        "instructions": "1. Open this URL in your browser. 2. Login to Amazon and authorize. 3. Copy the FULL URL from browser after redirect. 4. Send it to /stk/authorize"
    }


@router.post("/stk/authorize")
async def stk_authorize(data: STKAuthorizeRequest, current_user: User = Depends(get_current_user)):
    """Complete STK authorization with the redirect URL from browser"""
    from app.services.stk_kindle_sender import get_stk_sender

    if not data.redirect_url:
        raise HTTPException(status_code=400, detail="redirect_url is required")

    sender = get_stk_sender(current_user.id)
    success = sender.complete_authorization(data.redirect_url)

    if success:
        devices = sender.get_devices()
        return {
            "ok": True,
            "message": "Authorization successful!",
            "devices": devices
        }
    else:
        raise HTTPException(
            status_code=400,
            detail="Authorization failed. Make sure you copied the full redirect URL."
        )


@router.get("/stk/devices")
async def stk_get_devices(current_user: User = Depends(get_current_user)):
    """Get list of Kindle devices for the current user"""
    from app.services.stk_kindle_sender import get_stk_sender

    sender = get_stk_sender(current_user.id)
    if not sender.is_authenticated():
        raise HTTPException(status_code=401, detail="Not authenticated. Use /stk/signin-url first.")

    return {"devices": sender.get_devices()}


@router.post("/stk/send/{chapter_id}")
async def stk_send_to_kindle(
    chapter_id: int,
    data: Optional[SendRequest] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Send chapter to Kindle via STK using the current user's session"""
    from app.services.stk_kindle_sender import get_stk_sender

    sender = get_stk_sender(current_user.id)

    if not sender.is_authenticated():
        raise HTTPException(
            status_code=401,
            detail="STK not authenticated. Go to Settings and authorize with Amazon."
        )

    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="Tomo not found")

    if not chapter.converted_path:
        raise HTTPException(status_code=400, detail="Tomo has not been converted to EPUB yet")

    file_paths = [Path(p.strip()) for p in chapter.converted_path.split('|') if p.strip()]
    missing_files = [str(f) for f in file_paths if not f.exists()]
    if missing_files:
        raise HTTPException(status_code=400, detail=f"EPUB files not found: {', '.join(missing_files)}")

    author = "Unknown"
    if chapter.manga.authors and len(chapter.manga.authors) > 0:
        author = chapter.manga.authors[0]

    # Device priority: request param > user setting > all devices
    device_serials = None
    if data and data.device_serial:
        device_serials = [data.device_serial]
    elif current_user.stk_device_serial:
        device_serials = [current_user.stk_device_serial]
        logger.info(f"Using saved device: {current_user.stk_device_name or current_user.stk_device_serial}")

    sent_count = 0
    failed_files = []

    for idx, book_file in enumerate(file_paths, 1):
        part_suffix = f" (Parte {idx}/{len(file_paths)})" if len(file_paths) > 1 else ""
        title = f"{chapter.manga.title} - Tomo {chapter.number}{part_suffix}"

        result = sender.send_file(
            file_path=book_file,
            title=title,
            author=author,
            device_serials=device_serials
        )

        if result['success']:
            sent_count += 1
        else:
            failed_files.append(book_file.name)
            logger.error(f"Failed to send {book_file.name}: {result['message']}")

    if sent_count > 0:
        chapter.sent_at = datetime.utcnow()
        chapter.status = "sent"
        db.commit()

        message = f"Enviado {sent_count} archivo(s)"
        if failed_files:
            message += f" ({len(failed_files)} fallidos)"

        return SendResponse(ok=True, message=message, chapter_id=chapter_id, sent_at=chapter.sent_at)
    else:
        raise HTTPException(status_code=500, detail=f"Failed to send: {', '.join(failed_files)}")


@router.post("/stk/logout")
async def stk_logout(current_user: User = Depends(get_current_user)):
    """Clear STK session for the current user"""
    from app.services.stk_kindle_sender import get_stk_sender, remove_stk_sender

    sender = get_stk_sender(current_user.id)
    sender.logout()
    remove_stk_sender(current_user.id)

    return {"ok": True, "message": "STK session cleared"}
