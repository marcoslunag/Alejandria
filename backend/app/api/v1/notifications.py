"""
Notifications API - Badge de nuevos capítulos/issues/libros
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
import asyncio
import json
from app.database import get_db, SessionLocal
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

    # Contar errores de descarga recientes (capítulos/issues con status='error')
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
    total_errors = manga_errors + comic_errors + book_errors

    return {
        "total": total,
        "manga_new": sum(i["count"] for i in items if i["type"] == "manga"),
        "comic_new": sum(i["count"] for i in items if i["type"] == "comic"),
        "book_new": sum(i["count"] for i in items if i["type"] == "book"),
        "errors": total_errors,
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


def _build_notification_payload(user_id: int, db: Session) -> dict:
    """Build the notifications payload for a user (reusable)."""
    from app.models.manga import Manga
    from app.models.chapter import Chapter
    from app.models.comic import Comic, ComicIssue
    from app.models.book import Book
    from app.models.book_chapter import BookChapter

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {"total": 0, "items": [], "errors": 0}

    since = user.last_notification_check or user.created_at
    items = []

    manga_new = (
        db.query(Manga.id, Manga.title, Manga.cover_image, func.count(Chapter.id).label("cnt"))
        .join(Chapter, Chapter.manga_id == Manga.id)
        .filter(Manga.user_id == user_id, Chapter.created_at > since, Chapter.status != "error")
        .group_by(Manga.id, Manga.title, Manga.cover_image).all()
    )
    for manga_id, title, cover, cnt in manga_new:
        items.append({"type": "manga", "id": manga_id, "title": title, "cover": cover, "count": cnt})

    comic_new = (
        db.query(Comic.id, Comic.title, Comic.cover_image, func.count(ComicIssue.id).label("cnt"))
        .join(ComicIssue, ComicIssue.comic_id == Comic.id)
        .filter(Comic.user_id == user_id, ComicIssue.created_at > since, ComicIssue.status != "error")
        .group_by(Comic.id, Comic.title, Comic.cover_image).all()
    )
    for comic_id, title, cover, cnt in comic_new:
        items.append({"type": "comic", "id": comic_id, "title": title, "cover": cover, "count": cnt})

    book_new = (
        db.query(Book.id, Book.title, Book.cover_image, func.count(BookChapter.id).label("cnt"))
        .join(BookChapter, BookChapter.book_id == Book.id)
        .filter(Book.user_id == user_id, BookChapter.created_at > since, BookChapter.status != "error")
        .group_by(Book.id, Book.title, Book.cover_image).all()
    )
    for book_id, title, cover, cnt in book_new:
        items.append({"type": "book", "id": book_id, "title": title, "cover": cover, "count": cnt})

    total = sum(i["count"] for i in items)

    manga_errors = db.query(func.count(Chapter.id)).join(Manga, Chapter.manga_id == Manga.id).filter(Manga.user_id == user_id, Chapter.status == "error").scalar() or 0
    comic_errors = db.query(func.count(ComicIssue.id)).join(Comic, ComicIssue.comic_id == Comic.id).filter(Comic.user_id == user_id, ComicIssue.status == "error").scalar() or 0
    book_errors = db.query(func.count(BookChapter.id)).join(Book, BookChapter.book_id == Book.id).filter(Book.user_id == user_id, BookChapter.status == "error").scalar() or 0

    return {
        "total": total,
        "manga_new": sum(i["count"] for i in items if i["type"] == "manga"),
        "comic_new": sum(i["count"] for i in items if i["type"] == "comic"),
        "book_new": sum(i["count"] for i in items if i["type"] == "book"),
        "errors": manga_errors + comic_errors + book_errors,
        "items": items,
    }


@router.get("/stream")
async def stream_notifications(
    token: str = Query(..., description="JWT auth token"),
):
    """
    Server-Sent Events endpoint for real-time notification badge.
    Sends an update whenever the notification count changes.
    Accepts token as query param since EventSource doesn't support custom headers.
    """
    from app.core.security import decode_token

    try:
        payload = decode_token(token)
        user_id = int(payload.get("sub"))
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    async def event_generator():
        last_total = -1
        last_errors = -1
        while True:
            db = SessionLocal()
            try:
                data = _build_notification_payload(user_id, db)
                # Only push when something changed
                if data["total"] != last_total or data["errors"] != last_errors:
                    last_total = data["total"]
                    last_errors = data["errors"]
                    yield f"data: {json.dumps(data)}\n\n"
                else:
                    # Heartbeat to keep connection alive
                    yield ": heartbeat\n\n"
            except Exception as e:
                yield ": error\n\n"
            finally:
                db.close()
            await asyncio.sleep(10)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
