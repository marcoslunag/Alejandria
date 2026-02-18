"""
Notifications API - Badge de nuevos capítulos/issues/libros
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from app.database import get_db
from app.models.user import User
from app.models.manga import Manga
from app.models.chapter import Chapter
from app.models.comic import Comic, ComicIssue
from app.models.book import Book
from app.models.book_chapter import BookChapter
from app.core.deps import get_current_user
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/count")
def get_notification_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Returns count of new chapters/issues/books added since last_notification_check.
    Items added before the user's account was created are never counted.
    """
    since = current_user.last_notification_check or current_user.created_at
    uid = current_user.id

    items = []

    # New manga chapters grouped by manga
    manga_new = (
        db.query(Manga.id, Manga.title, Manga.cover_image, func.count(Chapter.id).label("cnt"))
        .join(Chapter, Chapter.manga_id == Manga.id)
        .filter(
            Manga.user_id == uid,
            Chapter.created_at > since,
            Chapter.status != "error",
        )
        .group_by(Manga.id, Manga.title, Manga.cover_image)
        .all()
    )
    for manga_id, title, cover, cnt in manga_new:
        items.append({"type": "manga", "id": manga_id, "title": title, "cover": cover, "count": cnt})

    # New comic issues grouped by comic
    comic_new = (
        db.query(Comic.id, Comic.title, Comic.cover_image, func.count(ComicIssue.id).label("cnt"))
        .join(ComicIssue, ComicIssue.comic_id == Comic.id)
        .filter(
            Comic.user_id == uid,
            ComicIssue.created_at > since,
            ComicIssue.status != "error",
        )
        .group_by(Comic.id, Comic.title, Comic.cover_image)
        .all()
    )
    for comic_id, title, cover, cnt in comic_new:
        items.append({"type": "comic", "id": comic_id, "title": title, "cover": cover, "count": cnt})

    # New book chapters grouped by book
    book_new = (
        db.query(Book.id, Book.title, Book.cover_image, func.count(BookChapter.id).label("cnt"))
        .join(BookChapter, BookChapter.book_id == Book.id)
        .filter(
            Book.user_id == uid,
            BookChapter.created_at > since,
            BookChapter.status != "error",
        )
        .group_by(Book.id, Book.title, Book.cover_image)
        .all()
    )
    for book_id, title, cover, cnt in book_new:
        items.append({"type": "book", "id": book_id, "title": title, "cover": cover, "count": cnt})

    total = sum(i["count"] for i in items)

    return {
        "total": total,
        "manga_new": sum(i["count"] for i in items if i["type"] == "manga"),
        "comic_new": sum(i["count"] for i in items if i["type"] == "comic"),
        "book_new": sum(i["count"] for i in items if i["type"] == "book"),
        "items": items,
    }


@router.post("/mark-seen")
def mark_notifications_seen(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark all current notifications as seen by updating last_notification_check."""
    current_user.last_notification_check = datetime.utcnow()
    db.commit()
    return {"ok": True}
