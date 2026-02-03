"""
Kindle API Endpoints
Send books to Kindle via email
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
from app.services.kindle_sender import KindleSender

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/kindle", tags=["kindle"])


# Pydantic schemas
class SendRequest(BaseModel):
    chapter_id: int


class SendBatchRequest(BaseModel):
    chapter_ids: List[int]


class SendResponse(BaseModel):
    ok: bool
    message: str
    chapter_id: int
    sent_at: Optional[datetime] = None


class SendBatchResponse(BaseModel):
    ok: bool
    message: str
    success: List[int]
    failed: List[int]


class STKSendRequest(BaseModel):
    device_serial: Optional[str] = None  # If not provided, sends to all devices


def get_kindle_sender(db: Session) -> tuple[KindleSender, str]:
    """
    Get KindleSender instance from database settings
    Returns tuple of (sender, kindle_email)
    """
    settings = db.query(AppSettings).first()

    if not settings:
        raise HTTPException(
            status_code=400,
            detail="Settings not configured. Go to Settings to configure SMTP and Kindle email."
        )

    if not settings.is_kindle_configured:
        missing = []
        if not settings.kindle_email:
            missing.append("Kindle email")
        if not settings.smtp_user:
            missing.append("SMTP user")
        if not settings.smtp_password:
            missing.append("SMTP password")
        if not settings.smtp_from_email:
            missing.append("From email")

        raise HTTPException(
            status_code=400,
            detail=f"Kindle configuration incomplete. Missing: {', '.join(missing)}"
        )

    sender = KindleSender(
        smtp_server=settings.smtp_server,
        smtp_port=settings.smtp_port,
        smtp_user=settings.smtp_user,
        smtp_password=settings.smtp_password,
        from_email=settings.smtp_from_email
    )

    return sender, settings.kindle_email


@router.post("/send/{chapter_id}", response_model=SendResponse)
async def send_to_kindle(chapter_id: int, db: Session = Depends(get_db)):
    """
    Send a specific chapter/tomo to Kindle via email.
    Supports split files (multiple paths separated by '|' in converted_path).
    Note: Email method has 25MB limit per file.
    """
    # Get chapter
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()

    if not chapter:
        raise HTTPException(status_code=404, detail="Tomo not found")

    # Check if converted file exists
    if not chapter.converted_path:
        raise HTTPException(
            status_code=400,
            detail="Tomo has not been converted to EPUB yet"
        )

    # Handle multiple files (split files) separated by '|'
    file_paths = [Path(p.strip()) for p in chapter.converted_path.split('|') if p.strip()]

    # Verify all files exist
    missing_files = [str(f) for f in file_paths if not f.exists()]
    if missing_files:
        raise HTTPException(
            status_code=400,
            detail=f"EPUB files not found: {', '.join(missing_files)}"
        )

    # Check file sizes - email has 25MB limit
    MAX_EMAIL_SIZE_MB = 25  # Gmail limit
    oversized_files = []
    for fp in file_paths:
        size_mb = fp.stat().st_size / (1024 * 1024)
        if size_mb > MAX_EMAIL_SIZE_MB:
            oversized_files.append(f"{fp.name} ({size_mb:.0f}MB)")

    if oversized_files:
        raise HTTPException(
            status_code=400,
            detail=f"Archivos demasiado grandes para email (límite 25MB): {', '.join(oversized_files)}. "
                   f"Usa STK (Send to Kindle API) para archivos grandes."
        )

    # Get sender
    try:
        sender, kindle_email = get_kindle_sender(db)
    except HTTPException:
        raise

    # Send all files to Kindle
    try:
        all_success = True
        sent_count = 0

        for idx, file_path in enumerate(file_paths):
            # Include part number in subject if multiple files
            if len(file_paths) > 1:
                subject = f"Manga: {chapter.manga.title} - Tomo {chapter.number} - Parte {idx + 1}"
            else:
                subject = f"Manga: {chapter.manga.title} - Tomo {chapter.number}"

            success = sender.send_to_kindle(
                file_path=file_path,
                kindle_email=kindle_email,
                subject=subject
            )

            if success:
                sent_count += 1
                logger.info(f"Sent {file_path.name} to Kindle: {kindle_email}")
            else:
                all_success = False
                logger.error(f"Failed to send {file_path.name}")

        if sent_count > 0:
            # Update chapter status
            chapter.sent_at = datetime.utcnow()
            chapter.status = "sent"
            db.commit()

            message = f"Enviado a {kindle_email}"
            if len(file_paths) > 1:
                message = f"Enviadas {sent_count}/{len(file_paths)} partes a {kindle_email}"

            return SendResponse(
                ok=all_success,
                message=message,
                chapter_id=chapter_id,
                sent_at=chapter.sent_at
            )
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to send email. Check logs for details."
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending chapter {chapter_id} to Kindle: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error sending to Kindle: {str(e)}"
        )


@router.post("/send-batch", response_model=SendBatchResponse)
async def send_batch_to_kindle(data: SendBatchRequest, db: Session = Depends(get_db)):
    """
    Send multiple chapters/tomos to Kindle
    """
    if not data.chapter_ids:
        raise HTTPException(status_code=400, detail="No chapter IDs provided")

    # Get sender
    try:
        sender, kindle_email = get_kindle_sender(db)
    except HTTPException:
        raise

    success_ids = []
    failed_ids = []

    for chapter_id in data.chapter_ids:
        chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()

        if not chapter:
            failed_ids.append(chapter_id)
            continue

        if not chapter.converted_path:
            failed_ids.append(chapter_id)
            continue

        file_path = Path(chapter.converted_path)
        if not file_path.exists():
            failed_ids.append(chapter_id)
            continue

        try:
            result = sender.send_to_kindle(
                file_path=file_path,
                kindle_email=kindle_email,
                subject=f"Manga: {chapter.manga.title} - Tomo {chapter.number}"
            )

            if result:
                chapter.sent_at = datetime.utcnow()
                chapter.status = "sent"
                success_ids.append(chapter_id)
            else:
                failed_ids.append(chapter_id)

        except Exception as e:
            logger.error(f"Error sending chapter {chapter_id}: {e}")
            failed_ids.append(chapter_id)

    db.commit()

    return SendBatchResponse(
        ok=len(failed_ids) == 0,
        message=f"Enviados {len(success_ids)} de {len(data.chapter_ids)} tomos",
        success=success_ids,
        failed=failed_ids
    )


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

    # Calculate total size and max individual file size
    total_size_mb = 0
    max_file_size_mb = 0
    for f in existing_files:
        size = f.stat().st_size / (1024 * 1024)
        total_size_mb += size
        max_file_size_mb = max(max_file_size_mb, size)

    # For email, ALL files must be under 25MB
    can_send_email = has_epub and max_file_size_mb <= 25

    return {
        "chapter_id": chapter_id,
        "status": chapter.status,
        "sent_at": chapter.sent_at,
        "has_epub": has_epub,
        "file_count": len(existing_files),
        "file_size_mb": round(total_size_mb, 2),
        "max_file_size_mb": round(max_file_size_mb, 2),
        "can_send_email": can_send_email,
        "too_large_message": f"Archivos demasiado grandes ({max_file_size_mb:.0f}MB max) - usar STK" if has_epub and not can_send_email else None
    }


@router.get("/can-send")
async def check_kindle_configured(db: Session = Depends(get_db)):
    """
    Check if Kindle sending is properly configured
    """
    settings = db.query(AppSettings).first()

    if not settings:
        return {
            "configured": False,
            "message": "Settings not configured"
        }

    return {
        "configured": settings.is_kindle_configured,
        "kindle_email": settings.kindle_email if settings.is_kindle_configured else None,
        "message": "Ready to send" if settings.is_kindle_configured else "Configuration incomplete"
    }


# ============================================
# STK (Send to Kindle) API - OAuth2 based
# Supports large files (>25MB)
# ============================================

class STKAuthorizeRequest(BaseModel):
    redirect_url: str


@router.get("/stk/status")
async def stk_status():
    """
    Check if STK (Send to Kindle) is authenticated
    """
    from app.services.stk_kindle_sender import get_stk_sender

    sender = get_stk_sender()
    is_auth = sender.is_authenticated()

    devices = []
    if is_auth:
        devices = sender.get_devices()

    return {
        "authenticated": is_auth,
        "devices": devices,
        "message": "Ready to send large files" if is_auth else "Not authenticated. Use /stk/signin-url to get authorization URL."
    }


@router.get("/stk/signin-url")
async def stk_get_signin_url():
    """
    Get Amazon OAuth2 sign-in URL
    User must open this in browser and authorize
    After authorization, use the redirect URL with /stk/authorize
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
            "message": "Authorization successful! You can now send large files to Kindle.",
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
    data: Optional[STKSendRequest] = None,
    db: Session = Depends(get_db)
):
    """
    Send chapter to Kindle via STK (supports large files)

    Optionally specify device_serial to send to a specific device.
    If not specified, sends to all devices.
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
    import re
    file_paths = [Path(p.strip()) for p in chapter.converted_path.split('|') if p.strip()]

    # Verify all files exist
    missing_files = [str(f) for f in file_paths if not f.exists()]
    if missing_files:
        raise HTTPException(
            status_code=400,
            detail=f"EPUB/MOBI files not found: {', '.join(missing_files)}"
        )

    # Use the files directly from converted_path (already sorted by converter)
    files_to_send = file_paths

    if len(files_to_send) > 1:
        logger.info(f"Found {len(files_to_send)} parts to send: {[f.name for f in files_to_send]}")

    if not files_to_send:
        raise HTTPException(status_code=400, detail="No EPUB/MOBI files found to send")

    # Get author from authors list
    author = "Unknown"
    if chapter.manga.authors and len(chapter.manga.authors) > 0:
        author = chapter.manga.authors[0]

    # Get device serials - priority: request > settings > all devices
    device_serials = None
    if data and data.device_serial:
        # Use device from request
        device_serials = [data.device_serial]
    else:
        # Check settings for saved device preference
        settings = db.query(AppSettings).first()
        if settings and settings.stk_device_serial:
            device_serials = [settings.stk_device_serial]
            logger.info(f"Using saved device preference: {settings.stk_device_name or settings.stk_device_serial}")

    # Send ALL files
    sent_count = 0
    failed_files = []

    for idx, book_file in enumerate(files_to_send, 1):
        part_suffix = f" (Parte {idx}/{len(files_to_send)})" if len(files_to_send) > 1 else ""
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
            message += f" ({len(failed_files)} fallidos: {', '.join(failed_files)})"

        return SendResponse(
            ok=True,
            message=message,
            chapter_id=chapter_id,
            sent_at=chapter.sent_at
        )
    else:
        raise HTTPException(status_code=500, detail=f"Failed to send all files: {', '.join(failed_files)}")


@router.post("/stk/logout")
async def stk_logout():
    """
    Clear STK session
    """
    from app.services.stk_kindle_sender import get_stk_sender

    sender = get_stk_sender()
    sender.logout()

    return {"ok": True, "message": "STK session cleared"}
