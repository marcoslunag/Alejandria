"""
Export/Import API - Backup y restauración de biblioteca
"""

import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.models.manga import Manga
from app.models.comic import Comic
from app.models.book import Book
from app.core.deps import get_current_user
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/export", tags=["export"])


@router.get("")
async def export_library(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Export user library as a JSON file download.
    Returns manga, comics, and books with their key metadata.
    """
    uid = current_user.id

    manga_list = db.query(Manga).filter(Manga.user_id == uid).all()
    comic_list = db.query(Comic).filter(Comic.user_id == uid).all()
    book_list = db.query(Book).filter(Book.user_id == uid).all()

    export_data = {
        "exported_at": datetime.utcnow().isoformat(),
        "version": "3.0",
        "user": current_user.username,
        "manga": [
            {
                "title": m.title,
                "anilist_id": m.anilist_id,
                "genres": m.genres,
                "status": m.status,
                "monitored": m.monitored,
                "reading_status": m.reading_status,
                "cover_image": m.cover_image,
            }
            for m in manga_list
        ],
        "comics": [
            {
                "title": c.title,
                "comicvine_id": c.comicvine_id,
                "publisher": c.publisher,
                "start_year": c.start_year,
                "count_of_issues": c.count_of_issues,
                "monitored": c.monitored,
                "reading_status": c.reading_status,
                "cover_image": c.cover_image,
            }
            for c in comic_list
        ],
        "books": [
            {
                "title": b.title,
                "google_books_id": b.google_books_id,
                "authors": b.authors,
                "isbn_13": b.isbn_13,
                "language": b.language,
                "monitored": b.monitored,
                "reading_status": b.reading_status,
                "cover_image": b.cover_image,
            }
            for b in book_list
        ],
    }

    json_bytes = json.dumps(export_data, ensure_ascii=False, indent=2).encode("utf-8")
    filename = f"alejandria-backup-{datetime.utcnow().strftime('%Y%m%d')}.json"

    return StreamingResponse(
        iter([json_bytes]),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import")
async def import_library(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Import library from a previously exported JSON backup.
    Creates items that don't already exist (by anilist_id/comicvine_id/google_books_id).
    Returns {imported, skipped, errors}.
    """
    uid = current_user.id
    imported = 0
    skipped = 0
    errors = []

    # Import manga
    for item in payload.get("manga", []):
        try:
            anilist_id = item.get("anilist_id")
            if not anilist_id:
                skipped += 1
                continue
            existing = db.query(Manga).filter(
                Manga.anilist_id == anilist_id, Manga.user_id == uid
            ).first()
            if existing:
                skipped += 1
                continue
            new_manga = Manga(
                user_id=uid,
                title=item.get("title", ""),
                anilist_id=anilist_id,
                genres=item.get("genres"),
                status=item.get("status"),
                monitored=item.get("monitored", True),
                reading_status=item.get("reading_status", "not_started"),
                cover_image=item.get("cover_image"),
                slug=f"anilist-{anilist_id}",
            )
            db.add(new_manga)
            imported += 1
        except Exception as e:
            errors.append(f"Manga '{item.get('title')}': {str(e)}")

    # Import comics
    for item in payload.get("comics", []):
        try:
            comicvine_id = item.get("comicvine_id")
            if not comicvine_id:
                skipped += 1
                continue
            existing = db.query(Comic).filter(
                Comic.comicvine_id == comicvine_id, Comic.user_id == uid
            ).first()
            if existing:
                skipped += 1
                continue
            import re
            slug_base = re.sub(r'[^a-z0-9]+', '-', item.get("title", "").lower()).strip('-')
            new_comic = Comic(
                user_id=uid,
                title=item.get("title", ""),
                comicvine_id=comicvine_id,
                publisher=item.get("publisher"),
                start_year=item.get("start_year"),
                count_of_issues=item.get("count_of_issues"),
                monitored=item.get("monitored", True),
                reading_status=item.get("reading_status", "not_started"),
                cover_image=item.get("cover_image"),
                slug=f"{slug_base}-{comicvine_id}",
            )
            db.add(new_comic)
            imported += 1
        except Exception as e:
            errors.append(f"Comic '{item.get('title')}': {str(e)}")

    # Import books
    for item in payload.get("books", []):
        try:
            google_books_id = item.get("google_books_id")
            if not google_books_id:
                skipped += 1
                continue
            existing = db.query(Book).filter(
                Book.google_books_id == google_books_id, Book.user_id == uid
            ).first()
            if existing:
                skipped += 1
                continue
            import re
            slug_base = re.sub(r'[^a-z0-9]+', '-', item.get("title", "").lower()).strip('-')
            new_book = Book(
                user_id=uid,
                title=item.get("title", ""),
                google_books_id=google_books_id,
                authors=item.get("authors"),
                isbn_13=item.get("isbn_13"),
                language=item.get("language"),
                monitored=item.get("monitored", True),
                reading_status=item.get("reading_status", "not_started"),
                cover_image=item.get("cover_image"),
                slug=f"{slug_base}-{google_books_id[:8]}",
            )
            db.add(new_book)
            imported += 1
        except Exception as e:
            errors.append(f"Book '{item.get('title')}': {str(e)}")

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error saving import: {str(e)}")

    return {"imported": imported, "skipped": skipped, "errors": errors}
