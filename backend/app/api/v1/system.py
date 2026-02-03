"""
System API Endpoints
System status, health checks, and configuration
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models.manga import Manga
from app.models.chapter import Chapter
from app.models.download import DownloadQueue
from app.schemas.download import SystemStatusResponse
from app.config import get_settings
from app.services.scraper import TomosMangaScraper
from app.services.converter import KCCConverter
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system", tags=["system"])
settings = get_settings()


@router.get("/status", response_model=SystemStatusResponse)
def get_system_status(db: Session = Depends(get_db)):
    """
    Get system status and statistics

    Args:
        db: Database session

    Returns:
        System status information
    """
    # Count statistics
    total_manga = db.query(func.count(Manga.id)).scalar()
    monitored_manga = db.query(func.count(Manga.id)).filter(Manga.monitored == True).scalar()
    total_chapters = db.query(func.count(Chapter.id)).scalar()
    downloaded_chapters = db.query(func.count(Chapter.id)).filter(
        Chapter.status.in_(['downloaded', 'converted', 'sent'])
    ).scalar()
    queue_size = db.query(func.count(DownloadQueue.id)).filter(
        DownloadQueue.status.in_(['queued', 'downloading'])
    ).scalar()
    active_downloads = db.query(func.count(DownloadQueue.id)).filter(
        DownloadQueue.status == 'downloading'
    ).scalar()

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
def get_config():
    """
    Get system configuration (non-sensitive)

    Returns:
        System configuration
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
def test_scraper():
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
def test_kcc():
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
def test_stk():
    """
    Test STK (Send to Kindle) connection

    Returns:
        STK test result
    """
    from app.services.stk_kindle_sender import get_stk_sender

    try:
        sender = get_stk_sender()
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
            "message": str(e)
        }


@router.get("/stats")
def get_detailed_stats(db: Session = Depends(get_db)):
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
async def trigger_process_queue(db: Session = Depends(get_db)):
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
            "message": str(e)
        }


@router.post("/process-conversions")
async def trigger_process_conversions(db: Session = Depends(get_db)):
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
            "message": str(e)
        }


@router.post("/cleanup")
async def trigger_cleanup(db: Session = Depends(get_db)):
    """
    Manually trigger cleanup of old files

    Args:
        db: Database session

    Returns:
        Cleanup status
    """
    from app.services.scheduler import MangaScheduler
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
            "message": str(e)
        }


@router.get("/logs/recent")
def get_recent_logs(lines: int = 50):
    """
    Get recent log entries

    Args:
        lines: Number of log lines to return

    Returns:
        Recent log entries
    """
    # TODO: Implement log reading from file
    return {
        "message": "Log endpoint not implemented yet",
        "lines": lines
    }
