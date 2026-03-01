"""
System API Endpoints
System status, health checks, and configuration
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models.manga import Manga
from app.models.chapter import Chapter
from app.models.comic import Comic, ComicIssue
from app.models.book import Book
from app.models.book_chapter import BookChapter
from app.models.download import DownloadQueue
from app.models.user import User
from app.schemas.download import SystemStatusResponse
from app.config import get_settings
from app.services.scraper import TomosMangaScraper
from app.services.converter import KCCConverter
from app.core.deps import get_current_user
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system", tags=["system"])
settings = get_settings()


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


@router.get("/status", response_model=SystemStatusResponse)
def get_system_status(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Get system status and statistics (filtered to current user's data)
    """
    uid = current_user.id
    total_manga = db.query(func.count(Manga.id)).filter(Manga.user_id == uid).scalar()
    monitored_manga = db.query(func.count(Manga.id)).filter(Manga.user_id == uid, Manga.monitored == True).scalar()
    total_chapters = (
        db.query(func.count(Chapter.id))
        .join(Manga, Chapter.manga_id == Manga.id)
        .filter(Manga.user_id == uid)
        .scalar()
    )
    downloaded_chapters = (
        db.query(func.count(Chapter.id))
        .join(Manga, Chapter.manga_id == Manga.id)
        .filter(Manga.user_id == uid, Chapter.status.in_(['downloaded', 'converted', 'sent']))
        .scalar()
    )
    queue_size = (
        db.query(func.count(DownloadQueue.id))
        .outerjoin(Chapter, DownloadQueue.chapter_id == Chapter.id)
        .outerjoin(Manga, Chapter.manga_id == Manga.id)
        .filter(
            DownloadQueue.status.in_(['queued', 'downloading']),
            Manga.user_id == uid
        )
        .scalar()
    )
    active_downloads = (
        db.query(func.count(DownloadQueue.id))
        .outerjoin(Chapter, DownloadQueue.chapter_id == Chapter.id)
        .outerjoin(Manga, Chapter.manga_id == Manga.id)
        .filter(
            DownloadQueue.status == 'downloading',
            Manga.user_id == uid
        )
        .scalar()
    )

    return SystemStatusResponse(
        status="running",
        version=settings.APP_VERSION,
        total_manga=total_manga or 0,
        monitored_manga=monitored_manga or 0,
        total_chapters=total_chapters or 0,
        downloaded_chapters=downloaded_chapters or 0,
        queue_size=queue_size or 0,
        active_downloads=active_downloads or 0
    )


@router.get("/health")
def health_check():
    """
    Simple health check endpoint

    Returns:
        Health status
    """
    return {"status": "healthy", "version": settings.APP_VERSION}


@router.get("/config")
def get_config(current_user: User = Depends(get_current_user)):
    """
    Get system configuration (non-sensitive)
    """
    return {
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "check_interval_hours": settings.CHECK_INTERVAL_HOURS,
        "max_concurrent_downloads": settings.MAX_CONCURRENT_DOWNLOADS,
        "kcc_profile": settings.KCC_PROFILE,
        "kcc_format": settings.KCC_FORMAT
    }


@router.get("/test/scraper")
def test_scraper(current_user: User = Depends(require_admin)):
    """
    Test scraper connection

    Returns:
        Scraper test result
    """
    scraper = TomosMangaScraper()

    try:
        success = scraper.test_connection()
        return {
            "service": "scraper",
            "status": "online" if success else "offline",
            "message": "Connection successful" if success else "Connection failed"
        }
    except Exception as e:
        logger.error(f"Scraper test failed: {e}")
        return {
            "service": "scraper",
            "status": "error",
            "message": str(e)
        }


@router.get("/test/kcc")
def test_kcc(current_user: User = Depends(require_admin)):
    """
    Test KCC installation

    Returns:
        KCC test result
    """
    converter = KCCConverter()

    return {
        "service": "kcc",
        "status": "available" if converter.kcc_available else "unavailable",
        "message": "KCC is installed and ready" if converter.kcc_available else "KCC not found",
        "profiles": converter.get_supported_profiles() if converter.kcc_available else {}
    }


@router.get("/test/stk")
def test_stk(current_user: User = Depends(require_admin)):
    """
    Test STK (Send to Kindle) connection

    Returns:
        STK test result
    """
    from app.services.stk_kindle_sender import get_stk_sender

    try:
        sender = get_stk_sender(current_user.id)
        is_auth = sender.is_authenticated()

        if is_auth:
            devices = sender.get_devices()
            return {
                "service": "stk",
                "status": "online",
                "message": f"STK authenticated with {len(devices)} device(s)",
                "devices": devices
            }
        else:
            return {
                "service": "stk",
                "status": "not_authenticated",
                "message": "STK not authenticated. Go to Settings to authorize."
            }
    except Exception as e:
        logger.error(f"STK test failed: {e}")
        return {
            "service": "stk",
            "status": "error",
            "message": "STK connection error"
        }


@router.get("/dashboard")
def get_dashboard(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Get personal dashboard stats for the current user.
    Returns library counts, reading stats, recent downloads, and error count.
    """
    uid = current_user.id

    # --- Library counts ---
    total_manga = db.query(func.count(Manga.id)).filter(Manga.user_id == uid).scalar() or 0
    total_comics = db.query(func.count(Comic.id)).filter(Comic.user_id == uid).scalar() or 0
    total_books = db.query(func.count(Book.id)).filter(Book.user_id == uid).scalar() or 0

    # --- Reading stats per type ---
    def reading_counts(query, model):
        rows = (
            query.with_entities(model.reading_status, func.count(model.id))
            .group_by(model.reading_status)
            .all()
        )
        counts = {"not_started": 0, "reading": 0, "completed": 0}
        for status, cnt in rows:
            if status in counts:
                counts[status] = cnt
        return counts

    manga_reading = reading_counts(db.query(Manga).filter(Manga.user_id == uid), Manga)
    comics_reading = reading_counts(db.query(Comic).filter(Comic.user_id == uid), Comic)
    books_reading = reading_counts(db.query(Book).filter(Book.user_id == uid), Book)

    # --- Recent downloads (last 5 across all types) ---
    recent = []

    # Manga chapters
    manga_dl = (
        db.query(Chapter, Manga.title, Manga.cover_image)
        .join(Manga, Chapter.manga_id == Manga.id)
        .filter(Manga.user_id == uid, Chapter.downloaded_at.isnot(None))
        .order_by(Chapter.downloaded_at.desc())
        .limit(5)
        .all()
    )
    for ch, manga_title, cover in manga_dl:
        recent.append({
            "type": "manga",
            "title": manga_title,
            "cover": cover,
            "item_title": f"Cap. {int(ch.number) if ch.number == int(ch.number) else ch.number}",
            "downloaded_at": ch.downloaded_at.isoformat() if ch.downloaded_at else None,
        })

    # Comic issues
    comic_dl = (
        db.query(ComicIssue, Comic.title, Comic.cover_image)
        .join(Comic, ComicIssue.comic_id == Comic.id)
        .filter(Comic.user_id == uid, ComicIssue.downloaded_at.isnot(None))
        .order_by(ComicIssue.downloaded_at.desc())
        .limit(5)
        .all()
    )
    for issue, comic_title, cover in comic_dl:
        recent.append({
            "type": "comic",
            "title": comic_title,
            "cover": cover,
            "item_title": f"#{issue.issue_number}" if issue.issue_number else issue.title or "",
            "downloaded_at": issue.downloaded_at.isoformat() if issue.downloaded_at else None,
        })

    # Book chapters
    book_dl = (
        db.query(BookChapter, Book.title, Book.cover_image)
        .join(Book, BookChapter.book_id == Book.id)
        .filter(Book.user_id == uid, BookChapter.downloaded_at.isnot(None))
        .order_by(BookChapter.downloaded_at.desc())
        .limit(5)
        .all()
    )
    for bc, book_title, cover in book_dl:
        recent.append({
            "type": "book",
            "title": book_title,
            "cover": cover,
            "item_title": bc.title or f"Vol. {bc.number}",
            "downloaded_at": bc.downloaded_at.isoformat() if bc.downloaded_at else None,
        })

    # Sort and keep top 5
    recent.sort(key=lambda x: x["downloaded_at"] or "", reverse=True)
    recent = recent[:5]

    # --- Error count ---
    manga_errors = (
        db.query(func.count(Chapter.id))
        .join(Manga, Chapter.manga_id == Manga.id)
        .filter(Manga.user_id == uid, Chapter.status == "error")
        .scalar() or 0
    )
    comic_errors = (
        db.query(func.count(ComicIssue.id))
        .join(Comic, ComicIssue.comic_id == Comic.id)
        .filter(Comic.user_id == uid, ComicIssue.status == "error")
        .scalar() or 0
    )
    book_errors = (
        db.query(func.count(BookChapter.id))
        .join(Book, BookChapter.book_id == Book.id)
        .filter(Book.user_id == uid, BookChapter.status == "error")
        .scalar() or 0
    )
    error_count = manga_errors + comic_errors + book_errors

    # --- Storage used ---
    comic_storage = (
        db.query(func.sum(ComicIssue.file_size))
        .join(Comic, ComicIssue.comic_id == Comic.id)
        .filter(Comic.user_id == uid, ComicIssue.file_size.isnot(None))
        .scalar() or 0
    )
    book_storage = (
        db.query(func.sum(BookChapter.file_size))
        .join(Book, BookChapter.book_id == Book.id)
        .filter(Book.user_id == uid, BookChapter.file_size.isnot(None))
        .scalar() or 0
    )
    storage_used_mb = round((comic_storage + book_storage) / (1024 * 1024), 1)

    return {
        "library": {"manga": total_manga, "comics": total_comics, "books": total_books},
        "reading_stats": {
            "manga": manga_reading,
            "comics": comics_reading,
            "books": books_reading,
        },
        "recent_downloads": recent,
        "error_count": error_count,
        "storage_used_mb": storage_used_mb,
    }


@router.get("/stats")
def get_detailed_stats(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """
    Get detailed system statistics

    Args:
        db: Database session

    Returns:
        Detailed statistics
    """
    # Chapter status counts
    chapter_statuses = {}
    status_query = db.query(
        Chapter.status,
        func.count(Chapter.id)
    ).group_by(Chapter.status).all()

    for status, count in status_query:
        chapter_statuses[status] = count

    # Download queue statuses
    queue_statuses = {}
    queue_query = db.query(
        DownloadQueue.status,
        func.count(DownloadQueue.id)
    ).group_by(DownloadQueue.status).all()

    for status, count in queue_query:
        queue_statuses[status] = count

    # Recent manga
    recent_manga = db.query(Manga).order_by(Manga.created_at.desc()).limit(5).all()

    return {
        "chapter_statuses": chapter_statuses,
        "queue_statuses": queue_statuses,
        "recent_manga": [
            {
                "id": m.id,
                "title": m.title,
                "monitored": m.monitored,
                "created_at": m.created_at.isoformat()
            }
            for m in recent_manga
        ]
    }


@router.post("/process-queue")
async def trigger_process_queue(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """
    Manually trigger processing of download queue

    Returns:
        Processing status
    """
    from app.services.scheduler import get_scheduler

    try:
        scheduler = get_scheduler()
        if scheduler:
            # Run the process_download_queue method
            await scheduler.process_download_queue()
            return {
                "ok": True,
                "message": "Download queue processing triggered"
            }
        else:
            return {
                "ok": False,
                "message": "Scheduler not available"
            }
    except Exception as e:
        logger.error(f"Error triggering queue processing: {e}")
        return {
            "ok": False,
            "message": "Queue processing failed"
        }


@router.post("/process-conversions")
async def trigger_process_conversions(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """
    Manually trigger processing of conversions (sync KCC output with DB)

    Returns:
        Processing status
    """
    from app.services.scheduler import get_scheduler

    try:
        scheduler = get_scheduler()
        if scheduler:
            await scheduler.process_conversions()
            return {
                "ok": True,
                "message": "Conversion processing triggered"
            }
        else:
            return {
                "ok": False,
                "message": "Scheduler not available"
            }
    except Exception as e:
        logger.error(f"Error triggering conversion processing: {e}")
        return {
            "ok": False,
            "message": "Conversion processing failed"
        }


@router.post("/cleanup")
async def trigger_cleanup(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """
    Manually trigger cleanup of old files

    Args:
        db: Database session

    Returns:
        Cleanup status
    """
    from app.services.scheduler import ContentScheduler
    from pathlib import Path
    from datetime import datetime, timedelta

    try:
        cutoff_date = datetime.utcnow() - timedelta(days=settings.CLEANUP_DAYS)

        old_chapters = db.query(Chapter).filter(
            Chapter.sent_at is not None,
            Chapter.sent_at < cutoff_date
        ).all()

        cleaned_count = 0
        for chapter in old_chapters:
            if chapter.file_path:
                file_path = Path(chapter.file_path)
                if file_path.exists():
                    file_path.unlink()
                    cleaned_count += 1

            if chapter.converted_path:
                converted_path = Path(chapter.converted_path)
                if converted_path.exists():
                    converted_path.unlink()
                    cleaned_count += 1

            chapter.file_path = None
            chapter.converted_path = None

        db.commit()

        return {
            "status": "completed",
            "files_cleaned": cleaned_count,
            "chapters_processed": len(old_chapters)
        }

    except Exception as e:
        logger.error(f"Cleanup error: {e}")
        return {
            "status": "error",
            "message": "Cleanup failed"
        }


@router.get("/logs/recent")
def get_recent_logs(
    limit: int = Query(50, ge=1, le=200),
    level: str = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Get recent system log entries from DB.

    Args:
        limit: Number of entries (default 50, max 200)
        level: Filter by level (INFO, WARNING, ERROR)

    Returns:
        List of log entries ordered by date desc
    """
    from app.services.log_service import get_system_logger
    logs = get_system_logger().get_recent(level=level, limit=limit, db=db)
    return {"logs": logs, "total": len(logs)}


@router.post("/translate")
def translate_text(text: str, source: str = "en", target: str = "es", current_user: User = Depends(get_current_user)):
    """
    Translate text using deep-translator (Google Translate)

    Args:
        text: Text to translate
        source: Source language code (default: en)
        target: Target language code (default: es)

    Returns:
        Translated text
    """
    from app.services.translator import get_translator

    if not text or len(text.strip()) == 0:
        return {"translated": "", "original": text}

    try:
        translator = get_translator()
        translated = translator.translate_text(text)
        return {
            "translated": translated,
            "original": text,
            "source": source,
            "target": target
        }
    except Exception as e:
        logger.error(f"Translation error: {e}")
        return {
            "translated": text,
            "original": text,
            "error": "Translation failed"
        }
