"""
Download Queue API Endpoints
Manages download queue
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from app.database import get_db, SessionLocal
from app.models.chapter import Chapter
from app.models.manga import Manga
from app.models.book import Book
from app.models.book_chapter import BookChapter
from app.models.comic import Comic, ComicIssue
from app.models.download import DownloadQueue
from app.schemas.download import DownloadQueueResponse, DownloadQueueDetailResponse
from app.models.user import User
from app.core.deps import get_current_user
import logging
import json
import asyncio

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/queue", tags=["queue"])


@router.get("/")
def list_queue(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
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
    status_map = {
        'downloading': ['downloading'],
        'converting': ['converting', 'downloaded'],  # 'downloaded' = pendiente de conversión KCC
        'completed': ['converted', 'sent'],
        'failed': ['error']
    }

    result = []

    # Pre-fetch next_retry_at from DownloadQueue for failed items
    failed_dq = db.query(DownloadQueue).filter(DownloadQueue.status == 'failed').all()
    nra_by_chapter = {qi.chapter_id: qi.next_retry_at for qi in failed_dq if qi.chapter_id}
    nra_by_book_chapter = {qi.book_chapter_id: qi.next_retry_at for qi in failed_dq if qi.book_chapter_id}
    nra_by_comic_issue = {qi.comic_issue_id: qi.next_retry_at for qi in failed_dq if qi.comic_issue_id}

    # Query MANGA chapters with download activity
    manga_query = db.query(Chapter).join(Manga).filter(Manga.user_id == current_user.id)

    if status:
        chapter_statuses = status_map.get(status, [status])
        manga_query = manga_query.filter(Chapter.status.in_(chapter_statuses))
    else:
        manga_query = manga_query.filter(Chapter.status.in_(['downloading', 'converting', 'downloaded', 'converted', 'sent', 'error']))

    from sqlalchemy import case, desc
    manga_query = manga_query.order_by(
        case(
            (Chapter.status == 'downloading', 0),
            (Chapter.status == 'converting', 1),
            (Chapter.status == 'error', 2),
            else_=3
        ),
        desc(Chapter.downloaded_at),
        desc(Chapter.created_at)
    )

    manga_chapters = manga_query.all()

    for chapter in manga_chapters:
        manga = chapter.manga
        queue_status = {
            'downloading': 'downloading',
            'converting': 'converting',
            'pending': 'pending',
            'downloaded': 'converting',   # pendiente de conversión por KCC Worker
            'converted': 'completed',
            'sent': 'completed',
            'error': 'failed'
        }.get(chapter.status, chapter.status)

        result.append({
            "id": chapter.id,
            "chapter_id": chapter.id,
            "content_type": "manga",
            "status": queue_status,
            "progress": 100 if chapter.status in ['converted', 'sent'] else 0,
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
            "sent_at": chapter.sent_at.isoformat() if chapter.sent_at else None,
            "has_epub": bool(chapter.converted_path),
            "converted_path": chapter.converted_path,
            "next_retry_at": nra_by_chapter.get(chapter.id).isoformat() if nra_by_chapter.get(chapter.id) else None,
        })

    # Query BOOK chapters with download activity
    book_query = db.query(BookChapter).join(Book).filter(Book.user_id == current_user.id)

    if status:
        chapter_statuses = status_map.get(status, [status])
        book_query = book_query.filter(BookChapter.status.in_(chapter_statuses))
    else:
        book_query = book_query.filter(BookChapter.status.in_(['downloading', 'converting', 'downloaded', 'converted', 'sent', 'error']))

    book_query = book_query.order_by(
        case(
            (BookChapter.status == 'downloading', 0),
            (BookChapter.status == 'converting', 1),
            (BookChapter.status == 'error', 2),
            else_=3
        ),
        desc(BookChapter.downloaded_at),
        desc(BookChapter.created_at)
    )

    book_chapters = book_query.all()

    for chapter in book_chapters:
        book = chapter.book
        queue_status = {
            'downloading': 'downloading',
            'converting': 'converting',
            'pending': 'pending',
            'downloaded': 'completed',
            'converted': 'completed',
            'sent': 'completed',
            'error': 'failed'
        }.get(chapter.status, chapter.status)

        result.append({
            "id": f"book_{chapter.id}",
            "book_chapter_id": chapter.id,
            "content_type": "book",
            "status": queue_status,
            "progress": 100 if chapter.status in ['downloaded', 'converted', 'sent'] else 0,
            "bytes_downloaded": 0,
            "total_bytes": 0,
            "error_message": chapter.error_message,
            "retry_count": 0,
            "max_retries": 3,
            "created_at": chapter.created_at.isoformat() if chapter.created_at else None,
            "started_at": chapter.downloaded_at.isoformat() if chapter.downloaded_at else None,
            "completed_at": chapter.downloaded_at.isoformat() if chapter.downloaded_at else None,
            "priority": 0,
            "book_id": book.id if book else None,
            "book_title": book.title if book else None,
            "book_cover": book.cover_image if book else None,
            "chapter_number": chapter.number,
            "chapter_title": chapter.title or book.title,
            "download_url": chapter.download_url,
            "sent_at": chapter.sent_at.isoformat() if chapter.sent_at else None,
            "has_epub": bool(chapter.file_path and chapter.file_path.endswith('.epub')),
            "file_path": chapter.file_path,
            "next_retry_at": nra_by_book_chapter.get(chapter.id).isoformat() if nra_by_book_chapter.get(chapter.id) else None,
        })

    # Query COMIC issues with download activity
    comic_query = db.query(ComicIssue).join(Comic).filter(Comic.user_id == current_user.id)

    if status:
        chapter_statuses = status_map.get(status, [status])
        comic_query = comic_query.filter(ComicIssue.status.in_(chapter_statuses))
    else:
        comic_query = comic_query.filter(ComicIssue.status.in_(['downloading', 'converting', 'downloaded', 'converted', 'sent', 'error']))

    comic_query = comic_query.order_by(
        case(
            (ComicIssue.status == 'downloading', 0),
            (ComicIssue.status == 'converting', 1),
            (ComicIssue.status == 'error', 2),
            else_=3
        ),
        desc(ComicIssue.downloaded_at),
        desc(ComicIssue.created_at)
    )

    comic_issues = comic_query.all()

    for issue in comic_issues:
        comic = issue.comic
        queue_status = {
            'downloading': 'downloading',
            'converting': 'converting',
            'pending': 'pending',
            'downloaded': 'converting',   # pendiente de conversión por KCC Worker
            'converted': 'completed',
            'sent': 'completed',
            'error': 'failed'
        }.get(issue.status, issue.status)

        result.append({
            "id": f"comic_{issue.id}",
            "comic_issue_id": issue.id,
            "content_type": "comic",
            "status": queue_status,
            "progress": 100 if issue.status in ['converted', 'sent'] else 0,
            "bytes_downloaded": 0,
            "total_bytes": 0,
            "error_message": issue.error_message,
            "retry_count": issue.download_attempts or 0,
            "max_retries": 3,
            "created_at": issue.created_at.isoformat() if issue.created_at else None,
            "started_at": issue.downloaded_at.isoformat() if issue.downloaded_at else None,
            "completed_at": issue.downloaded_at.isoformat() if issue.downloaded_at else None,
            "priority": 0,
            "comic_id": comic.id if comic else None,
            "comic_title": comic.title if comic else None,
            "comic_cover": comic.cover_image if comic else None,
            "issue_number": issue.issue_number,
            "issue_title": issue.title,
            "download_url": issue.download_url,
            "sent_at": issue.sent_at.isoformat() if issue.sent_at else None,
            "has_cbz": bool(issue.file_path),
            "has_epub": bool(issue.converted_path),
            "converted_path": issue.converted_path,
            "file_path": issue.file_path,
            "next_retry_at": nra_by_comic_issue.get(issue.id).isoformat() if nra_by_comic_issue.get(issue.id) else None,
        })

    # Sort combined results by completion date (most recent first)
    result.sort(key=lambda x: x.get('completed_at') or '', reverse=True)

    return result[skip:skip+limit]


@router.post("/reset-stuck")
def reset_stuck_downloads(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
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


@router.post("/clear")
def clear_queue(
    status: Optional[str] = Query(None, description="Clear only items with this status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
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

    # Build subquery of user's manga IDs to avoid join+update limitation
    user_manga_ids = db.query(Manga.id).filter(Manga.user_id == current_user.id).scalar_subquery()

    if status:
        chapter_statuses = status_map.get(status, [status])
    else:
        chapter_statuses = ['downloaded', 'converted', 'sent', 'error']

    chapters = db.query(Chapter).filter(
        Chapter.manga_id.in_(user_manga_ids),
        Chapter.status.in_(chapter_statuses)
    ).all()

    count = len(chapters)
    for chapter in chapters:
        chapter.status = 'pending'
        chapter.error_message = None
    db.commit()

    logger.info(f"Reset {count} chapters in queue")
    return {"cleared": count}


@router.post("/{chapter_id}", status_code=201)
def add_to_queue(
    chapter_id: int,
    priority: int = Query(0, ge=0, le=10),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
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
    # Check if chapter exists and belongs to current user
    chapter = db.query(Chapter).join(Manga).filter(
        Chapter.id == chapter_id,
        Manga.user_id == current_user.id
    ).first()
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
def remove_from_queue(chapter_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Remove chapter from download queue (reset its status)

    Args:
        chapter_id: Chapter ID
        db: Database session
    """
    chapter = db.query(Chapter).join(Manga).filter(
        Chapter.id == chapter_id,
        Manga.user_id == current_user.id
    ).first()

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
def cancel_download(chapter_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Cancel a download in progress and clean up partial files.
    
    If the chapter is part of a bundle (shares download_url with others),
    ALL chapters in the bundle will be cancelled.

    This endpoint:
    1. Finds all chapters in the same bundle (same download_url)
    2. Marks all bundled chapters as 'cancelled'
    3. Removes lock files (.downloading)
    4. Cleans up partial download files
    5. Removes the items from the download queue

    Args:
        chapter_id: Chapter ID
        db: Database session

    Returns:
        Cancellation status with list of all cancelled chapters
    """
    import os
    from pathlib import Path

    chapter = db.query(Chapter).join(Manga).filter(
        Chapter.id == chapter_id,
        Manga.user_id == current_user.id
    ).first()

    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    manga = db.query(Manga).filter(Manga.id == chapter.manga_id).first()

    # Can cancel downloading, pending, or error status
    if chapter.status not in ['downloading', 'pending', 'error', 'converting']:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel chapter with status '{chapter.status}'. Only downloading, pending, converting or error chapters can be cancelled."
        )
    
    # Find all chapters in the same bundle (same download_url)
    chapters_to_cancel = [chapter]
    if chapter.download_url:
        bundled_chapters = db.query(Chapter).filter(
            Chapter.manga_id == chapter.manga_id,
            Chapter.download_url == chapter.download_url,
            Chapter.id != chapter_id,
            Chapter.status.in_(['downloading', 'pending', 'error', 'converting'])
        ).all()
        chapters_to_cancel.extend(bundled_chapters)
        
        if bundled_chapters:
            logger.info(f"Found {len(bundled_chapters)} bundled chapters to cancel along with chapter {chapter_id}")

    cancelled_files = []
    cancelled_chapter_ids = []
    download_dir = Path(os.getenv('DOWNLOAD_DIR', '/downloads'))

    # Process all chapters in the bundle
    for ch in chapters_to_cancel:
        cancelled_chapter_ids.append(ch.id)
        
        # Find and clean up files related to this chapter
        if manga:
            # Pattern to find related files
            # Files are named like: manga-slug_ch00001.0.cbz
            slug = manga.slug or manga.title.lower().replace(' ', '-')
            patterns = [
                f"{slug}_ch{ch.number:05.1f}*",
                f"{slug}*tomo*{int(ch.number)}*",
                f"{manga.title}*tomo*{int(ch.number)}*",
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
        if ch.file_path:
            try:
                file_path = Path(ch.file_path)
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
            DownloadQueue.chapter_id == ch.id
        ).all()

        for item in queue_items:
            db.delete(item)

        # Reset chapter status
        ch.status = 'pending'
        ch.file_path = None
        ch.error_message = "Cancelled by user"
        ch.downloaded_at = None

    db.commit()

    logger.info(f"Cancelled download for {len(cancelled_chapter_ids)} chapters (bundle), cleaned {len(cancelled_files)} files")

    return {
        "cancelled": True,
        "chapter_id": chapter_id,
        "cancelled_chapters": cancelled_chapter_ids,
        "bundle_size": len(cancelled_chapter_ids),
        "files_deleted": cancelled_files,
        "status": "pending"
    }


@router.post("/{chapter_id}/retry")
def retry_download(chapter_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Retry failed download

    Args:
        chapter_id: Chapter ID
        db: Database session

    Returns:
        Updated chapter info
    """
    chapter = db.query(Chapter).join(Manga).filter(
        Chapter.id == chapter_id,
        Manga.user_id == current_user.id
    ).first()

    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    if chapter.status != 'error':
        raise HTTPException(status_code=400, detail="Only failed downloads can be retried")

    if chapter.retry_count >= 3:
        raise HTTPException(status_code=400, detail="Maximum retries exceeded")

    # Reset status for manual retry (override backoff delay)
    chapter.status = 'pending'
    chapter.error_message = None
    chapter.retry_count += 1

    # Clear next_retry_at so the queue item is picked up immediately
    queue_item = db.query(DownloadQueue).filter(
        DownloadQueue.chapter_id == chapter_id,
        DownloadQueue.status == 'failed'
    ).first()
    if queue_item:
        queue_item.status = 'queued'
        queue_item.next_retry_at = None

    db.commit()
    db.refresh(chapter)

    logger.info(f"Queued manual retry for chapter {chapter_id}")
    return {"id": chapter.id, "status": "pending", "retry_count": chapter.retry_count}


@router.delete("/{chapter_id}/file")
def delete_downloaded_file(chapter_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
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

    chapter = db.query(Chapter).join(Manga).filter(
        Chapter.id == chapter_id,
        Manga.user_id == current_user.id
    ).first()

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


# ============================================================================
# COMIC ISSUE QUEUE ACTIONS
# ============================================================================

@router.post("/comic/{issue_id}/cancel")
def cancel_comic_download(issue_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Cancel a comic issue download in progress and clean up partial files.
    If the issue is part of a bundle, ALL bundle issues will be cancelled.
    """
    import os
    from pathlib import Path

    issue = db.query(ComicIssue).join(Comic).filter(
        ComicIssue.id == issue_id,
        Comic.user_id == current_user.id
    ).first()
    if not issue:
        raise HTTPException(status_code=404, detail="Comic issue not found")

    comic = db.query(Comic).filter(Comic.id == issue.comic_id).first()

    if issue.status not in ['downloading', 'pending', 'error', 'converting']:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel issue with status '{issue.status}'"
        )

    # Find all issues in the same bundle
    issues_to_cancel = [issue]
    if issue.bundle_id:
        bundled = db.query(ComicIssue).filter(
            ComicIssue.bundle_id == issue.bundle_id,
            ComicIssue.id != issue_id,
            ComicIssue.status.in_(['downloading', 'pending', 'error', 'converting'])
        ).all()
        issues_to_cancel.extend(bundled)

    cancelled_files = []
    cancelled_ids = []

    for ci in issues_to_cancel:
        cancelled_ids.append(ci.id)

        # Delete downloaded file if exists
        if ci.file_path:
            try:
                fp = Path(ci.file_path)
                if fp.exists():
                    fp.unlink()
                    cancelled_files.append(str(fp))
                # Delete lock file
                lock = fp.parent / f"{fp.name}.downloading"
                if lock.exists():
                    lock.unlink()
                # Delete metadata
                meta = fp.with_suffix('.metadata.json')
                if meta.exists():
                    meta.unlink()
            except Exception as e:
                logger.warning(f"Could not delete comic file: {e}")

        # Remove from download queue
        db.query(DownloadQueue).filter(
            DownloadQueue.comic_issue_id == ci.id
        ).delete()

        # Reset issue status
        ci.status = 'pending'
        ci.file_path = None
        ci.error_message = "Cancelled by user"
        ci.downloaded_at = None

    db.commit()
    logger.info(f"Cancelled {len(cancelled_ids)} comic issue(s), cleaned {len(cancelled_files)} files")

    return {
        "cancelled": True,
        "issue_id": issue_id,
        "cancelled_issues": cancelled_ids,
        "bundle_size": len(cancelled_ids),
        "files_deleted": cancelled_files
    }


@router.post("/comic/{issue_id}/retry")
def retry_comic_download(issue_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Retry a failed comic issue download"""
    issue = db.query(ComicIssue).join(Comic).filter(
        ComicIssue.id == issue_id,
        Comic.user_id == current_user.id
    ).first()
    if not issue:
        raise HTTPException(status_code=404, detail="Comic issue not found")

    if issue.status != 'error':
        raise HTTPException(status_code=400, detail="Only failed downloads can be retried")

    # Reset issue status
    issue.status = 'downloading'
    issue.error_message = None
    issue.download_attempts = (issue.download_attempts or 0) + 1

    # Create new queue item
    queue_item = DownloadQueue(
        comic_issue_id=issue.id,
        content_type='comic',
        status='queued',
        priority=0
    )
    db.add(queue_item)
    db.commit()

    logger.info(f"Queued retry for comic issue {issue_id}")
    return {"id": issue.id, "status": "downloading", "retry_count": issue.download_attempts}


@router.delete("/comic/{issue_id}/file")
def delete_comic_file(issue_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Delete downloaded comic file and reset issue status"""
    import os
    from pathlib import Path

    issue = db.query(ComicIssue).join(Comic).filter(
        ComicIssue.id == issue_id,
        Comic.user_id == current_user.id
    ).first()
    if not issue:
        raise HTTPException(status_code=404, detail="Comic issue not found")

    if issue.status not in ['downloaded', 'converted', 'sent', 'error', 'converting']:
        raise HTTPException(status_code=400, detail="Issue has no downloaded file")

    deleted_files = []

    # Delete source file
    if issue.file_path:
        try:
            fp = Path(issue.file_path)
            if fp.exists():
                fp.unlink()
                deleted_files.append(str(fp))
            # Delete metadata
            meta = fp.with_suffix('.metadata.json')
            if meta.exists():
                meta.unlink()
        except Exception as e:
            logger.error(f"Error deleting comic file {issue.file_path}: {e}")

    # Delete converted files (may be multi-part separated by '|')
    if issue.converted_path:
        for conv_path in issue.converted_path.split('|'):
            conv_path = conv_path.strip()
            if conv_path:
                try:
                    if os.path.exists(conv_path):
                        os.remove(conv_path)
                        deleted_files.append(conv_path)
                except Exception as e:
                    logger.error(f"Error deleting converted file {conv_path}: {e}")

    # Reset issue status
    issue.status = 'pending'
    issue.file_path = None
    issue.converted_path = None
    issue.downloaded_at = None
    issue.converted_at = None
    issue.sent_at = None
    issue.error_message = None

    db.commit()

    return {
        "deleted": len(deleted_files) > 0,
        "issue_id": issue_id,
        "files_deleted": deleted_files,
        "count": len(deleted_files)
    }


@router.get("/stats")
def get_queue_stats(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Get queue statistics based on chapter status

    Only counts real download activity (not all pending chapters)

    Args:
        db: Database session

    Returns:
        Queue statistics
    """
    from sqlalchemy import func

    # Count from chapters table - only real activity for this user
    user_manga_ids = db.query(Manga.id).filter(Manga.user_id == current_user.id).scalar_subquery()

    downloading = db.query(func.count(Chapter.id)).filter(
        Chapter.manga_id.in_(user_manga_ids),
        Chapter.status == 'downloading'
    ).scalar() or 0

    completed = db.query(func.count(Chapter.id)).filter(
        Chapter.manga_id.in_(user_manga_ids),
        Chapter.status.in_(['downloaded', 'converted', 'sent'])
    ).scalar() or 0

    failed = db.query(func.count(Chapter.id)).filter(
        Chapter.manga_id.in_(user_manga_ids),
        Chapter.status == 'error'
    ).scalar() or 0

    return {
        "total": downloading + completed + failed,
        "downloading": downloading,
        "completed": completed,
        "failed": failed
    }


def _get_active_items_for_user(user_id: int, db: Session) -> list:
    """Get currently active (downloading + error) queue items for a user."""
    from sqlalchemy import case, desc

    result = []

    # Manga chapters that are downloading or error
    chapters = (
        db.query(Chapter, Manga)
        .join(Manga, Chapter.manga_id == Manga.id)
        .filter(
            Manga.user_id == user_id,
            Chapter.status.in_(["downloading", "error", "converting"]),
        )
        .all()
    )
    for ch, manga in chapters:
        result.append({
            "id": ch.id,
            "content_type": "manga",
            "status": ch.status,
            "manga_title": manga.title,
            "chapter_number": ch.number,
            "error_message": ch.error_message,
        })

    # Comic issues that are downloading, converting or error
    issues = (
        db.query(ComicIssue, Comic)
        .join(Comic, ComicIssue.comic_id == Comic.id)
        .filter(
            Comic.user_id == user_id,
            ComicIssue.status.in_(["downloading", "converting", "error"]),
        )
        .all()
    )
    for issue, comic in issues:
        result.append({
            "id": issue.id,
            "content_type": "comic",
            "status": issue.status,
            "comic_title": comic.title,
            "issue_number": issue.issue_number,
            "error_message": issue.error_message,
        })

    # Book chapters that are downloading or error
    bcs = (
        db.query(BookChapter, Book)
        .join(Book, BookChapter.book_id == Book.id)
        .filter(
            Book.user_id == user_id,
            BookChapter.status.in_(["downloading", "error"]),
        )
        .all()
    )
    for bc, book in bcs:
        result.append({
            "id": bc.id,
            "content_type": "book",
            "status": bc.status,
            "book_title": book.title,
            "chapter_number": bc.number,
            "error_message": bc.error_message,
        })

    return result


@router.get("/stream")
async def stream_queue(
    token: str = Query(..., description="JWT auth token"),
):
    """
    Server-Sent Events endpoint for real-time queue updates.
    Streams active queue items every 3 seconds.
    Accepts token as query param since EventSource doesn't support custom headers.
    """
    from app.core.security import decode_token
    from app.models.user import User as UserModel

    # Validate token
    try:
        payload = decode_token(token)
        user_id = int(payload.get("sub"))
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    async def event_generator():
        while True:
            db = SessionLocal()
            try:
                items = _get_active_items_for_user(user_id, db)
                data = json.dumps(items, default=str)
                yield f"data: {data}\n\n"
            except Exception as e:
                logger.warning(f"SSE queue error: {e}")
                yield f"data: []\n\n"
            finally:
                db.close()
            await asyncio.sleep(3)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
