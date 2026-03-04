"""
Activity feed — recent events for the current user.

Builds a unified timeline from existing DB tables (no new tables needed):
  - DownloadQueue:    queued, downloading, completed, failed
  - Chapter.sent_at:  sent to Kindle (manga)
  - ComicIssue.sent_at: sent to Kindle (comics)
  - BookChapter.sent_at / file_path: sent to Kindle / available (books)
"""

from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.models.download import DownloadQueue
from app.models.chapter import Chapter
from app.models.comic import Comic, ComicIssue
from app.models.book import Book
from app.models.book_chapter import BookChapter
from app.models.manga import Manga
from app.models.user import User

router = APIRouter(prefix="/activity", tags=["activity"])


class ActivityEvent(BaseModel):
    timestamp: datetime
    event_type: str   # queued | downloading | completed | failed | sent_kindle | converting
    item_type: str    # manga | comic | book
    item_title: str
    item_id: int      # manga_id / comic_id / book_id
    detail: str       # "Tomo 3", "Issue #5", "Archivo 1"
    message: str
    error: Optional[str] = None


@router.get("/recent", response_model=List[ActivityEvent])
def get_recent_activity(
    hours: int = Query(48, ge=1, le=168),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns a unified activity timeline for the current user,
    sorted newest-first. Covers the last `hours` hours.
    """
    since = datetime.utcnow() - timedelta(hours=hours)
    events: List[ActivityEvent] = []

    # ── Manga download events ─────────────────────────────────────────────────
    manga_items = (
        db.query(DownloadQueue, Chapter, Manga)
        .join(Chapter, DownloadQueue.chapter_id == Chapter.id)
        .join(Manga, Chapter.manga_id == Manga.id)
        .filter(
            Manga.user_id == current_user.id,
            DownloadQueue.created_at >= since,
        )
        .all()
    )

    for q, ch, manga in manga_items:
        tomo = f"Tomo {int(ch.number)}" if ch.number else "Tomo ?"
        _add_queue_events(events, q, "manga", manga.title, manga.id, tomo)

    # ── Manga sent-to-Kindle events ───────────────────────────────────────────
    sent_chapters = (
        db.query(Chapter, Manga)
        .join(Manga, Chapter.manga_id == Manga.id)
        .filter(
            Manga.user_id == current_user.id,
            Chapter.sent_at != None,
            Chapter.sent_at >= since,
        )
        .all()
    )
    for ch, manga in sent_chapters:
        tomo = f"Tomo {int(ch.number)}" if ch.number else "Tomo ?"
        events.append(ActivityEvent(
            timestamp=ch.sent_at,
            event_type="sent_kindle",
            item_type="manga",
            item_title=manga.title,
            item_id=manga.id,
            detail=tomo,
            message=f"Enviado a Kindle: {manga.title} — {tomo}",
        ))

    # ── Comic download events ─────────────────────────────────────────────────
    comic_items = (
        db.query(DownloadQueue, ComicIssue, Comic)
        .join(ComicIssue, DownloadQueue.comic_issue_id == ComicIssue.id)
        .join(Comic, ComicIssue.comic_id == Comic.id)
        .filter(
            Comic.user_id == current_user.id,
            DownloadQueue.created_at >= since,
        )
        .all()
    )
    for q, issue, comic in comic_items:
        issue_label = f"Issue #{issue.issue_number}" if issue.issue_number else "Issue ?"
        _add_queue_events(events, q, "comic", comic.title, comic.id, issue_label)

    # ── Comic sent-to-Kindle events ───────────────────────────────────────────
    sent_issues = (
        db.query(ComicIssue, Comic)
        .join(Comic, ComicIssue.comic_id == Comic.id)
        .filter(
            Comic.user_id == current_user.id,
            ComicIssue.sent_at != None,
            ComicIssue.sent_at >= since,
        )
        .all()
    )
    for issue, comic in sent_issues:
        issue_label = f"Issue #{issue.issue_number}" if issue.issue_number else "Issue ?"
        events.append(ActivityEvent(
            timestamp=issue.sent_at,
            event_type="sent_kindle",
            item_type="comic",
            item_title=comic.title,
            item_id=comic.id,
            detail=issue_label,
            message=f"Enviado a Kindle: {comic.title} — {issue_label}",
        ))

    # ── Book download events ──────────────────────────────────────────────────
    book_items = (
        db.query(DownloadQueue, BookChapter, Book)
        .join(BookChapter, DownloadQueue.book_chapter_id == BookChapter.id)
        .join(Book, BookChapter.book_id == Book.id)
        .filter(
            Book.user_id == current_user.id,
            DownloadQueue.created_at >= since,
        )
        .all()
    )
    for q, bc, book in book_items:
        detail = f"Archivo {int(bc.number)}" if bc.number else "Archivo"
        _add_queue_events(events, q, "book", book.title, book.id, detail)

    # ── Book sent-to-Kindle events ────────────────────────────────────────────
    sent_books = (
        db.query(BookChapter, Book)
        .join(Book, BookChapter.book_id == Book.id)
        .filter(
            Book.user_id == current_user.id,
            BookChapter.sent_at != None,
            BookChapter.sent_at >= since,
        )
        .all()
    )
    for bc, book in sent_books:
        detail = f"Archivo {int(bc.number)}" if bc.number else "Archivo"
        events.append(ActivityEvent(
            timestamp=bc.sent_at,
            event_type="sent_kindle",
            item_type="book",
            item_title=book.title,
            item_id=book.id,
            detail=detail,
            message=f"Enviado a Kindle: {book.title}",
        ))

    # Sort newest-first, deduplicate, cap at limit
    events.sort(key=lambda e: e.timestamp, reverse=True)
    return events[:limit]


def _add_queue_events(
    events: list,
    q: DownloadQueue,
    item_type: str,
    title: str,
    item_id: int,
    detail: str,
):
    """Convert a DownloadQueue row into one or more ActivityEvents."""
    if q.started_at and q.started_at >= (datetime.utcnow() - timedelta(hours=200)):
        if q.status in ("downloading", "completed", "failed", "converting"):
            events.append(ActivityEvent(
                timestamp=q.started_at,
                event_type="downloading",
                item_type=item_type,
                item_title=title,
                item_id=item_id,
                detail=detail,
                message=f"Descarga iniciada: {title} — {detail}",
            ))

    if q.status == "completed" and q.completed_at:
        events.append(ActivityEvent(
            timestamp=q.completed_at,
            event_type="completed",
            item_type=item_type,
            item_title=title,
            item_id=item_id,
            detail=detail,
            message=f"Descarga completada: {title} — {detail}",
        ))
    elif q.status == "converting" and q.completed_at:
        events.append(ActivityEvent(
            timestamp=q.completed_at,
            event_type="converting",
            item_type=item_type,
            item_title=title,
            item_id=item_id,
            detail=detail,
            message=f"Convirtiendo a EPUB: {title} — {detail}",
        ))
    elif q.status == "failed" and q.completed_at:
        events.append(ActivityEvent(
            timestamp=q.completed_at,
            event_type="failed",
            item_type=item_type,
            item_title=title,
            item_id=item_id,
            detail=detail,
            message=f"Error en descarga: {title} — {detail}",
            error=q.error_message,
        ))
    elif q.status == "queued":
        events.append(ActivityEvent(
            timestamp=q.created_at,
            event_type="queued",
            item_type=item_type,
            item_title=title,
            item_id=item_id,
            detail=detail,
            message=f"En cola: {title} — {detail}",
        ))
