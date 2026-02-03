"""
Download Queue API Endpoints
Manages download queue
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from app.database import get_db
from app.models.chapter import Chapter
from app.models.manga import Manga
from app.models.download import DownloadQueue
from app.schemas.download import DownloadQueueResponse, DownloadQueueDetailResponse
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/queue", tags=["queue"])


@router.get("/")
def list_queue(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    List download activity - chapters with real download activity

    Shows chapters that are downloading, recently downloaded, or have errors.
    Does NOT show all 'pending' chapters (those are viewed per-manga).

    Args:
        skip: Number of records to skip
        limit: Maximum number of records
        status: Filter by status (downloading, completed, failed)
        db: Database session

    Returns:
        List of chapters with download activity
    """
    # Map frontend status to chapter status
    status_map = {
        'downloading': ['downloading'],
        'completed': ['downloaded', 'converted', 'sent'],
        'failed': ['error']
    }

    # Query chapters with download activity
    query = db.query(Chapter).join(Manga)

    if status:
        chapter_statuses = status_map.get(status, [status])
        query = query.filter(Chapter.status.in_(chapter_statuses))
    else:
        # Show only REAL activity: downloading, completed, or failed
        # NOT pending - those are just all chapters that haven't been downloaded
        query = query.filter(Chapter.status.in_(['downloading', 'downloaded', 'converted', 'sent', 'error']))

    # Order: downloading first, then errors, then completed by most recent
    from sqlalchemy import case, desc
    query = query.order_by(
        case(
            (Chapter.status == 'downloading', 0),
            (Chapter.status == 'error', 1),
            else_=2
        ),
        desc(Chapter.downloaded_at),
        desc(Chapter.created_at)
    )

    chapters = query.offset(skip).limit(limit).all()

    # Format response to match frontend expectations
    result = []
    for chapter in chapters:
        manga = chapter.manga

        # Map chapter status to queue status for frontend
        queue_status = {
            'downloading': 'downloading',
            'pending': 'pending',
            'downloaded': 'completed',
            'converted': 'completed',
            'sent': 'completed',
            'error': 'failed'
        }.get(chapter.status, chapter.status)

        result.append({
            "id": chapter.id,
            "chapter_id": chapter.id,
            "status": queue_status,
            "progress": 100 if chapter.status in ['downloaded', 'converted', 'sent'] else 0,
            "bytes_downloaded": 0,
            "total_bytes": 0,
            "error_message": chapter.error_message,
            "retry_count": chapter.retry_count,
            "max_retries": 3,
            "created_at": chapter.created_at.isoformat() if chapter.created_at else None,
            "started_at": chapter.downloaded_at.isoformat() if chapter.downloaded_at else None,
            "completed_at": chapter.downloaded_at.isoformat() if chapter.downloaded_at else None,
            "priority": 0,
            "manga_id": manga.id if manga else None,
            "manga_title": manga.title if manga else None,
            "manga_cover": manga.cover_image if manga else None,
            "chapter_number": chapter.number,
            "chapter_title": chapter.title,
            "download_url": chapter.download_url,
            # Kindle send fields
            "sent_at": chapter.sent_at.isoformat() if chapter.sent_at else None,
            "has_epub": bool(chapter.converted_path),
            "converted_path": chapter.converted_path
        })

    return result


@router.post("/reset-stuck")
def reset_stuck_downloads(db: Session = Depends(get_db)):
    """
    Reset stuck downloads (items with status='downloading' but no progress)
    This typically happens after a container restart
    """
    # Reset stuck queue items
    stuck_queue = db.query(DownloadQueue).filter(
        DownloadQueue.status == 'downloading'
    ).all()

    count = 0
    for item in stuck_queue:
        item.status = 'queued'
        item.progress = 0
        item.started_at = None
        count += 1

    # Also reset chapter status
    stuck_chapters = db.query(Chapter).filter(
        Chapter.status == 'downloading'
    ).all()

    for chapter in stuck_chapters:
        chapter.status = 'pending'

    db.commit()

    logger.info(f"Reset {count} stuck downloads and {len(stuck_chapters)} chapters")
    return {"reset_queue_items": count, "reset_chapters": len(stuck_chapters)}


@router.post("/{chapter_id}", status_code=201)
def add_to_queue(
    chapter_id: int,
    priority: int = Query(0, ge=0, le=10),
    db: Session = Depends(get_db)
):
    """
    Add chapter to download queue

    Args:
        chapter_id: Chapter ID
        priority: Priority (0-10, higher = more priority)
        db: Database session

    Returns:
        Queue item
    """
    # Check if chapter exists
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    # Check if already in queue
    existing = db.query(DownloadQueue).filter(
        DownloadQueue.chapter_id == chapter_id,
        DownloadQueue.status.in_(['queued', 'downloading'])
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Chapter already in queue")

    # Add to queue
    queue_item = DownloadQueue(
        chapter_id=chapter_id,
        status='queued',
        priority=priority
    )

    db.add(queue_item)
    db.commit()
    db.refresh(queue_item)

    logger.info(f"Added chapter {chapter_id} to queue")
    return queue_item


@router.delete("/{chapter_id}", status_code=204)
def remove_from_queue(chapter_id: int, db: Session = Depends(get_db)):
    """
    Remove chapter from download queue (reset its status)

    Args:
        chapter_id: Chapter ID
        db: Database session
    """
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()

    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    if chapter.status == 'downloading':
        raise HTTPException(status_code=400, detail="Cannot remove chapter that is currently downloading. Use /cancel endpoint instead.")

    # Reset chapter status to pending
    chapter.status = 'pending'
    chapter.error_message = None
    db.commit()

    logger.info(f"Reset chapter {chapter_id} status")
    return None


@router.post("/{chapter_id}/cancel")
def cancel_download(chapter_id: int, db: Session = Depends(get_db)):
    """
    Cancel a download in progress and clean up partial files.

    This endpoint:
    1. Marks the chapter as 'cancelled' (mapped to 'error' status internally)
    2. Removes lock files (.downloading)
    3. Cleans up partial download files
    4. Removes the item from the download queue

    Args:
        chapter_id: Chapter ID
        db: Database session

    Returns:
        Cancellation status
    """
    import os
    from pathlib import Path

    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()

    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    manga = db.query(Manga).filter(Manga.id == chapter.manga_id).first()

    # Can cancel downloading, pending, or error status
    if chapter.status not in ['downloading', 'pending', 'error', 'converting']:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel chapter with status '{chapter.status}'. Only downloading, pending, converting or error chapters can be cancelled."
        )

    cancelled_files = []
    download_dir = Path(os.getenv('DOWNLOAD_DIR', '/downloads'))

    # Find and clean up files related to this chapter
    if manga:
        # Pattern to find related files
        # Files are named like: manga-slug_ch00001.0.cbz
        slug = manga.slug or manga.title.lower().replace(' ', '-')
        patterns = [
            f"{slug}_ch{chapter.number:05.1f}*",
            f"{slug}*tomo*{int(chapter.number)}*",
            f"{manga.title}*tomo*{int(chapter.number)}*",
        ]

        for pattern in patterns:
            for file_path in download_dir.glob(pattern):
                try:
                    if file_path.is_file():
                        file_path.unlink()
                        cancelled_files.append(str(file_path))
                        logger.info(f"Deleted partial file: {file_path}")
                except Exception as e:
                    logger.warning(f"Could not delete {file_path}: {e}")

            # Also delete lock files
            for lock_file in download_dir.glob(f"{pattern}.downloading"):
                try:
                    lock_file.unlink()
                    logger.info(f"Deleted lock file: {lock_file}")
                except Exception as e:
                    logger.warning(f"Could not delete lock file {lock_file}: {e}")

    # Delete specific file if path is set
    if chapter.file_path:
        try:
            file_path = Path(chapter.file_path)
            if file_path.exists():
                file_path.unlink()
                cancelled_files.append(str(file_path))
                logger.info(f"Deleted chapter file: {file_path}")

            # Delete associated lock file
            lock_file = file_path.parent / f"{file_path.name}.downloading"
            if lock_file.exists():
                lock_file.unlink()
                logger.info(f"Deleted lock file: {lock_file}")
        except Exception as e:
            logger.warning(f"Could not delete chapter file: {e}")

    # Remove from download queue
    queue_items = db.query(DownloadQueue).filter(
        DownloadQueue.chapter_id == chapter_id
    ).all()

    for item in queue_items:
        db.delete(item)

    # Reset chapter status
    chapter.status = 'pending'
    chapter.file_path = None
    chapter.error_message = "Cancelled by user"
    chapter.downloaded_at = None

    db.commit()

    logger.info(f"Cancelled download for chapter {chapter_id}, cleaned {len(cancelled_files)} files")

    return {
        "cancelled": True,
        "chapter_id": chapter_id,
        "files_deleted": cancelled_files,
        "status": "pending"
    }


@router.post("/{chapter_id}/retry")
def retry_download(chapter_id: int, db: Session = Depends(get_db)):
    """
    Retry failed download

    Args:
        chapter_id: Chapter ID
        db: Database session

    Returns:
        Updated chapter info
    """
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()

    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    if chapter.status != 'error':
        raise HTTPException(status_code=400, detail="Only failed downloads can be retried")

    if chapter.retry_count >= 3:
        raise HTTPException(status_code=400, detail="Maximum retries exceeded")

    # Reset status for retry
    chapter.status = 'pending'
    chapter.error_message = None
    chapter.retry_count += 1

    db.commit()
    db.refresh(chapter)

    logger.info(f"Queued retry for chapter {chapter_id}")
    return {"id": chapter.id, "status": "pending", "retry_count": chapter.retry_count}


@router.post("/clear")
def clear_queue(
    status: Optional[str] = Query(None, description="Clear only items with this status"),
    db: Session = Depends(get_db)
):
    """
    Clear download queue (reset chapter statuses)

    Args:
        status: Only clear items with this status
        db: Database session

    Returns:
        Number of items cleared
    """
    # Map frontend status to chapter status
    status_map = {
        'completed': ['downloaded', 'converted', 'sent'],
        'failed': ['error'],
        'pending': ['pending']
    }

    query = db.query(Chapter)

    if status:
        chapter_statuses = status_map.get(status, [status])
        query = query.filter(Chapter.status.in_(chapter_statuses))
    else:
        # Clear completed and failed, not downloading
        query = query.filter(Chapter.status.in_(['downloaded', 'converted', 'sent', 'error']))

    # Reset status to pending
    count = query.update({Chapter.status: 'pending', Chapter.error_message: None}, synchronize_session=False)
    db.commit()

    logger.info(f"Reset {count} chapters in queue")
    return {"cleared": count}


@router.delete("/{chapter_id}/file")
def delete_downloaded_file(chapter_id: int, db: Session = Depends(get_db)):
    """
    Delete downloaded file and reset chapter status.

    Supports split files (multiple paths separated by '|' in converted_path).

    Args:
        chapter_id: Chapter ID
        db: Database session

    Returns:
        Status message with count of deleted files
    """
    import os

    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()

    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    if chapter.status not in ['downloaded', 'converted', 'sent', 'error', 'converting']:
        raise HTTPException(status_code=400, detail="Chapter has no downloaded file")

    deleted_files = []

    # Delete source file if exists
    if chapter.file_path:
        try:
            if os.path.exists(chapter.file_path):
                os.remove(chapter.file_path)
                deleted_files.append(chapter.file_path)
                logger.info(f"Deleted file: {chapter.file_path}")

            # Also delete metadata file
            metadata_path = chapter.file_path.rsplit('.', 1)[0] + '.metadata.json'
            if os.path.exists(metadata_path):
                os.remove(metadata_path)
                logger.info(f"Deleted metadata: {metadata_path}")
        except Exception as e:
            logger.error(f"Error deleting file {chapter.file_path}: {e}")

    # Delete converted files (can be multiple for split files)
    if chapter.converted_path:
        # Handle multiple paths separated by '|'
        converted_paths = [p.strip() for p in chapter.converted_path.split('|') if p.strip()]

        for conv_path in converted_paths:
            try:
                if os.path.exists(conv_path):
                    os.remove(conv_path)
                    deleted_files.append(conv_path)
                    logger.info(f"Deleted converted file: {conv_path}")
            except Exception as e:
                logger.error(f"Error deleting converted file {conv_path}: {e}")

    # Reset chapter status
    chapter.status = 'pending'
    chapter.file_path = None
    chapter.converted_path = None
    chapter.downloaded_at = None
    chapter.converted_at = None
    chapter.sent_at = None
    chapter.error_message = None

    db.commit()

    return {
        "deleted": len(deleted_files) > 0,
        "chapter_id": chapter_id,
        "files_deleted": deleted_files,
        "count": len(deleted_files)
    }


@router.get("/stats")
def get_queue_stats(db: Session = Depends(get_db)):
    """
    Get queue statistics based on chapter status

    Only counts real download activity (not all pending chapters)

    Args:
        db: Database session

    Returns:
        Queue statistics
    """
    from sqlalchemy import func

    # Count from chapters table - only real activity
    downloading = db.query(func.count(Chapter.id)).filter(
        Chapter.status == 'downloading'
    ).scalar() or 0

    completed = db.query(func.count(Chapter.id)).filter(
        Chapter.status.in_(['downloaded', 'converted', 'sent'])
    ).scalar() or 0

    failed = db.query(func.count(Chapter.id)).filter(
        Chapter.status == 'error'
    ).scalar() or 0

    return {
        "total": downloading + completed + failed,
        "downloading": downloading,
        "completed": completed,
        "failed": failed
    }
