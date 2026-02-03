"""
Kindle API Endpoints
Send books to Kindle via STK (Send to Kindle API)
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
from app.models.settings import AppSettings

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
async def get_kindle_status(chapter_id: int, db: Session = Depends(get_db)):
    """
    Get Kindle send status for a chapter.
    Supports split files (multiple paths separated by '|' in converted_path).
    """
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()

    if not chapter:
        raise HTTPException(status_code=404, detail="Tomo not found")

    # Handle multiple files (split files) separated by '|'
    file_paths = []
    if chapter.converted_path:
        file_paths = [Path(p.strip()) for p in chapter.converted_path.split('|') if p.strip()]

    # Check if all files exist
    existing_files = [f for f in file_paths if f.exists()]
    has_epub = len(existing_files) > 0

    # Calculate total size
    total_size_mb = sum(f.stat().st_size / (1024 * 1024) for f in existing_files)

    return {
        "chapter_id": chapter_id,
        "status": chapter.status,
        "sent_at": chapter.sent_at,
        "has_epub": has_epub,
        "file_count": len(existing_files),
        "file_size_mb": round(total_size_mb, 2)
    }


@router.get("/can-send")
async def check_kindle_configured(db: Session = Depends(get_db)):
    """
    Check if STK is properly configured
    """
    from app.services.stk_kindle_sender import get_stk_sender

    sender = get_stk_sender()
    is_auth = sender.is_authenticated()

    settings = db.query(AppSettings).first()
    has_device = settings and settings.stk_device_serial if settings else False

    return {
        "configured": is_auth and has_device,
        "authenticated": is_auth,
        "device_configured": has_device,
        "device_name": settings.stk_device_name if has_device else None,
        "message": "Ready to send" if (is_auth and has_device) else "STK not configured"
    }


# ============================================
# STK (Send to Kindle) API - OAuth2 based
# ============================================

@router.get("/stk/status")
async def stk_status(db: Session = Depends(get_db)):
    """
    Check if STK (Send to Kindle) is authenticated
    """
    from app.services.stk_kindle_sender import get_stk_sender

    sender = get_stk_sender()
    is_auth = sender.is_authenticated()

    devices = []
    if is_auth:
        devices = sender.get_devices()

    # Get saved device preference
    settings = db.query(AppSettings).first()
    saved_device = None
    if settings and settings.stk_device_serial:
        saved_device = {
            "serial": settings.stk_device_serial,
            "name": settings.stk_device_name
        }

    return {
        "authenticated": is_auth,
        "devices": devices,
        "saved_device": saved_device,
        "message": "Ready to send" if is_auth else "Not authenticated. Use /stk/signin-url to get authorization URL."
    }


@router.get("/stk/signin-url")
async def stk_get_signin_url():
    """
    Get Amazon OAuth2 sign-in URL
    """
    from app.services.stk_kindle_sender import get_stk_sender

    sender = get_stk_sender()
    url = sender.get_signin_url()

    return {
        "signin_url": url,
        "instructions": "1. Open this URL in your browser. 2. Login to Amazon and authorize. 3. Copy the FULL URL from browser after redirect. 4. Send it to /stk/authorize"
    }


@router.post("/stk/authorize")
async def stk_authorize(data: STKAuthorizeRequest):
    """
    Complete STK authorization with the redirect URL from browser
    """
    from app.services.stk_kindle_sender import get_stk_sender

    sender = get_stk_sender()

    if not data.redirect_url:
        raise HTTPException(status_code=400, detail="redirect_url is required")

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
async def stk_get_devices():
    """
    Get list of Kindle devices
    """
    from app.services.stk_kindle_sender import get_stk_sender

    sender = get_stk_sender()

    if not sender.is_authenticated():
        raise HTTPException(
            status_code=401,
            detail="Not authenticated. Use /stk/signin-url first."
        )

    devices = sender.get_devices()
    return {"devices": devices}


@router.post("/stk/send/{chapter_id}")
async def stk_send_to_kindle(
    chapter_id: int,
    data: Optional[SendRequest] = None,
    db: Session = Depends(get_db)
):
    """
    Send chapter to Kindle via STK
    """
    from app.services.stk_kindle_sender import get_stk_sender

    sender = get_stk_sender()

    if not sender.is_authenticated():
        raise HTTPException(
            status_code=401,
            detail="STK not authenticated. Go to Settings and authorize with Amazon."
        )

    # Get chapter
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()

    if not chapter:
        raise HTTPException(status_code=404, detail="Tomo not found")

    if not chapter.converted_path:
        raise HTTPException(status_code=400, detail="Tomo has not been converted to EPUB yet")

    # Handle multiple files (split files) separated by '|'
    file_paths = [Path(p.strip()) for p in chapter.converted_path.split('|') if p.strip()]

    # Verify all files exist
    missing_files = [str(f) for f in file_paths if not f.exists()]
    if missing_files:
        raise HTTPException(
            status_code=400,
            detail=f"EPUB files not found: {', '.join(missing_files)}"
        )

    # Get author from authors list
    author = "Unknown"
    if chapter.manga.authors and len(chapter.manga.authors) > 0:
        author = chapter.manga.authors[0]

    # Get device serials - priority: request > settings > all devices
    device_serials = None
    if data and data.device_serial:
        device_serials = [data.device_serial]
    else:
        settings = db.query(AppSettings).first()
        if settings and settings.stk_device_serial:
            device_serials = [settings.stk_device_serial]
            logger.info(f"Using saved device: {settings.stk_device_name or settings.stk_device_serial}")

    # Send all files
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
            logger.info(f"Sent {book_file.name} to Kindle")
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

        return SendResponse(
            ok=True,
            message=message,
            chapter_id=chapter_id,
            sent_at=chapter.sent_at
        )
    else:
        raise HTTPException(status_code=500, detail=f"Failed to send: {', '.join(failed_files)}")


@router.post("/stk/logout")
async def stk_logout():
    """
    Clear STK session
    """
    from app.services.stk_kindle_sender import get_stk_sender

    sender = get_stk_sender()
    sender.logout()

    return {"ok": True, "message": "STK session cleared"}
