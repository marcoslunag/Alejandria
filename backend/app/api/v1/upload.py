"""
Upload API - File upload endpoint for manga, comics, and books
Allows users to upload CBZ/CBR/EPUB/PDF files and add them to their library.
"""

import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.manga import Manga
from app.models.chapter import Chapter
from app.models.book import Book
from app.models.book_chapter import BookChapter
from app.models.comic import Comic, ComicIssue
from app.models.download import DownloadQueue
from app.models.user import User
from app.core.deps import get_current_user
from app.config import settings
import logging
from slugify import slugify

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/upload", tags=["upload"])

ALLOWED_EXTENSIONS = {".cbz", ".cbr", ".epub", ".pdf", ".zip"}


def _safe_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal."""
    return Path(filename).name


@router.post("")
async def upload_file(
    file: UploadFile = File(...),
    content_type: str = Form(...),   # manga | comic | book
    external_id: str = Form(...),    # anilist_id | google_books_id | comicvine_id
    item_number: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a file (CBZ, CBR, EPUB, PDF, ZIP) and add it to the library.

    - If the item doesn't exist in the library, it will be created from the external source.
    - The file is saved and queued for KCC conversion automatically.
    """
    # Validate content_type
    if content_type not in ("manga", "comic", "book"):
        raise HTTPException(status_code=400, detail="content_type must be 'manga', 'comic', or 'book'")

    # Validate file extension
    original_name = _safe_filename(file.filename or "upload.cbz")
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    # Parse item_number (tomo / chapter / issue number)
    number = 1.0
    if item_number and item_number.strip():
        try:
            number = float(item_number.strip())
        except ValueError:
            raise HTTPException(status_code=400, detail="item_number must be a valid number (e.g. 1, 2.5)")

    # Find or create item in library
    if content_type == "manga":
        item_id, item_title = await _find_or_create_manga(db, current_user, external_id)
        dir_path = Path(settings.DOWNLOAD_DIR) / "manga" / slugify(item_title)
    elif content_type == "comic":
        item_id, item_title = await _find_or_create_comic(db, current_user, external_id)
        dir_path = Path(settings.DOWNLOAD_DIR) / "comics" / slugify(item_title)
    else:
        item_id, item_title = await _find_or_create_book(db, current_user, external_id)
        dir_path = Path(settings.DOWNLOAD_DIR) / "books" / slugify(item_title)

    # Save file to disk
    dir_path.mkdir(parents=True, exist_ok=True)
    file_path = dir_path / original_name

    # Avoid overwriting existing files
    if file_path.exists():
        stem = Path(original_name).stem
        timestamp = int(datetime.utcnow().timestamp())
        file_path = dir_path / f"{stem}_{timestamp}{ext}"

    try:
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        logger.error(f"Failed to save uploaded file: {e}")
        raise HTTPException(status_code=500, detail="Failed to save file to disk")
    finally:
        await file.close()

    file_size = file_path.stat().st_size

    # Create DB record and queue for conversion
    if content_type == "manga":
        record_id = _create_manga_chapter(db, item_id, number, str(file_path))
        queue_entry = DownloadQueue(
            chapter_id=record_id,
            content_type="manga",
            status="completed",
            progress=100,
            bytes_downloaded=file_size,
            total_bytes=file_size,
            completed_at=datetime.utcnow(),
        )
    elif content_type == "comic":
        record_id = _create_comic_issue(db, item_id, number, str(file_path), file_size)
        queue_entry = DownloadQueue(
            comic_issue_id=record_id,
            content_type="comic",
            status="completed",
            progress=100,
            bytes_downloaded=file_size,
            total_bytes=file_size,
            completed_at=datetime.utcnow(),
        )
    else:
        record_id = _create_book_chapter(db, item_id, int(number), str(file_path), file_size)
        queue_entry = DownloadQueue(
            book_chapter_id=record_id,
            content_type="book",
            status="completed",
            progress=100,
            bytes_downloaded=file_size,
            total_bytes=file_size,
            completed_at=datetime.utcnow(),
        )

    db.add(queue_entry)
    db.commit()

    logger.info(f"Uploaded {content_type} '{item_title}' #{number}: {file_path} ({file_size} bytes)")

    return {
        "item_id": item_id,
        "item_title": item_title,
        "type": content_type,
        "file_path": str(file_path),
        "file_size": file_size,
    }


# ============================================================================
# HELPERS: Find or Create library items
# ============================================================================

async def _find_or_create_manga(db: Session, user: User, external_id: str):
    """Find existing manga by anilist_id or create it from AniList."""
    try:
        anilist_id = int(external_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="For manga, external_id must be a valid AniList ID (integer)")

    existing = db.query(Manga).filter(
        Manga.anilist_id == anilist_id,
        Manga.user_id == user.id
    ).first()

    if existing:
        return existing.id, existing.title

    # Create from AniList
    from app.services.anilist import AnilistService
    anilist = AnilistService()
    metadata = await anilist.get_manga_by_id(anilist_id)

    if not metadata:
        raise HTTPException(status_code=404, detail=f"Manga with AniList ID {anilist_id} not found")

    slug = slugify(metadata['title'])
    base_slug = slug
    counter = 1
    while db.query(Manga).filter(Manga.slug == slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1

    manga = Manga(
        title=metadata['title'],
        slug=slug,
        user_id=user.id,
        anilist_id=metadata['anilist_id'],
        mal_id=metadata.get('mal_id'),
        title_romaji=metadata.get('title_romaji'),
        title_english=metadata.get('title_english'),
        title_native=metadata.get('title_native'),
        description=metadata.get('description'),
        cover_image=metadata.get('cover_image'),
        banner_image=metadata.get('banner_image'),
        cover_color=metadata.get('cover_color'),
        format=metadata.get('format'),
        status=metadata.get('status'),
        start_date=metadata.get('start_date'),
        end_date=metadata.get('end_date'),
        chapters_total=metadata.get('chapters'),
        volumes_total=metadata.get('volumes'),
        genres=metadata.get('genres', []),
        tags=metadata.get('tags', []),
        authors=metadata.get('authors', []),
        artists=metadata.get('artists', []),
        average_score=metadata.get('average_score'),
        popularity=metadata.get('popularity'),
        anilist_url=metadata.get('anilist_url'),
        country=metadata.get('country'),
        monitored=True,
        auto_download=False,
    )
    db.add(manga)
    db.commit()
    db.refresh(manga)
    logger.info(f"Created manga from AniList for upload: {manga.title}")
    return manga.id, manga.title


async def _find_or_create_book(db: Session, user: User, external_id: str):
    """Find existing book by google_books_id or create it from Google Books."""
    existing = db.query(Book).filter(
        Book.google_books_id == external_id,
        Book.user_id == user.id
    ).first()

    if existing:
        return existing.id, existing.title

    from app.services.google_books import get_google_books_service
    google_books = get_google_books_service()
    metadata = await google_books.get_book_by_id(external_id)

    if not metadata:
        raise HTTPException(status_code=404, detail=f"Book with Google Books ID '{external_id}' not found")

    book = Book(
        title=metadata['title'],
        slug=slugify(metadata['title']),
        google_books_id=metadata['google_books_id'],
        subtitle=metadata.get('subtitle'),
        description=metadata.get('description'),
        cover_image=metadata.get('cover_image'),
        thumbnail=metadata.get('thumbnail'),
        authors=metadata.get('authors', []),
        publisher=metadata.get('publisher'),
        published_date=metadata.get('published_date'),
        language=metadata.get('language'),
        page_count=metadata.get('page_count'),
        categories=metadata.get('categories', []),
        average_rating=metadata.get('average_rating'),
        ratings_count=metadata.get('ratings_count'),
        isbn_10=metadata.get('isbn_10'),
        isbn_13=metadata.get('isbn_13'),
        google_books_url=metadata.get('google_books_url'),
        monitored=True,
        auto_download=False,
        user_id=user.id,
        source_urls={}
    )
    db.add(book)
    db.commit()
    db.refresh(book)
    logger.info(f"Created book from Google Books for upload: {book.title}")
    return book.id, book.title


async def _find_or_create_comic(db: Session, user: User, external_id: str):
    """Find existing comic by comicvine_id or create it from ComicVine."""
    try:
        comicvine_id = int(external_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="For comics, external_id must be a valid ComicVine ID (integer)")

    existing = db.query(Comic).filter(
        Comic.comicvine_id == comicvine_id,
        Comic.user_id == user.id
    ).first()

    if existing:
        return existing.id, existing.title

    from app.services.comicvine import get_comicvine_service
    comicvine = get_comicvine_service()
    details = await comicvine.get_volume(comicvine_id)

    if not details:
        raise HTTPException(status_code=404, detail=f"Comic with ComicVine ID {comicvine_id} not found")

    comic = Comic(
        title=details['title'],
        slug=slugify(details['title']),
        comicvine_id=details['comicvine_id'],
        title_original=details['title'],
        aliases=details.get('aliases'),
        description=details.get('description'),
        cover_image=details.get('cover_image'),
        publisher=details.get('publisher'),
        start_year=details.get('start_year'),
        count_of_issues=details.get('count_of_issues'),
        writers=details.get('writers'),
        artists=details.get('artists'),
        colorists=details.get('colorists'),
        characters=details.get('characters'),
        comicvine_url=details.get('comicvine_url'),
        monitored=True,
        auto_download=False,
        user_id=user.id,
        created_at=datetime.utcnow()
    )
    db.add(comic)
    db.commit()
    db.refresh(comic)
    logger.info(f"Created comic from ComicVine for upload: {comic.title}")
    return comic.id, comic.title


# ============================================================================
# HELPERS: Create chapter/issue records
# ============================================================================

def _create_manga_chapter(db: Session, manga_id: int, number: float, file_path: str) -> int:
    chapter = Chapter(
        manga_id=manga_id,
        number=number,
        url=f"uploaded:{file_path}",
        file_path=file_path,
        status="downloaded",
        downloaded_at=datetime.utcnow(),
    )
    db.add(chapter)
    db.commit()
    db.refresh(chapter)
    return chapter.id


def _create_book_chapter(db: Session, book_id: int, number: int, file_path: str, file_size: int) -> int:
    chapter = BookChapter(
        book_id=book_id,
        number=number,
        file_path=file_path,
        file_size=file_size,
        status="downloaded",
        downloaded_at=datetime.utcnow(),
    )
    db.add(chapter)
    db.commit()
    db.refresh(chapter)
    return chapter.id


def _create_comic_issue(db: Session, comic_id: int, number: float, file_path: str, file_size: int) -> int:
    issue_number = str(int(number)) if number == int(number) else str(number)
    issue = ComicIssue(
        comic_id=comic_id,
        issue_number=issue_number,
        file_path=file_path,
        file_size=file_size,
        status="downloaded",
        downloaded_at=datetime.utcnow(),
    )
    db.add(issue)
    db.commit()
    db.refresh(issue)
    return issue.id
