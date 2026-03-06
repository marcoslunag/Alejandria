"""
Books API Endpoints - Integration with Google Books and EPUB Scrapers
"""

from datetime import datetime
import asyncio
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func
from typing import List, Optional
from app.database import get_db
from app.models.book import Book
from app.models.book_chapter import BookChapter
from app.models.download import DownloadQueue
from app.schemas.book import (
    BookCreateFromGoogleBooks,
    BookCreateFromURL,
    BookResponse,
    BookDetailResponse,
    BookUpdate,
    BookSearchResponse,
    BookLibraryStats,
    BookChapterResponse,
    ChapterDownloadRequest
)
from app.services.google_books import get_google_books_service
from app.services.openlibrary import get_openlibrary_service
from app.services.book_scrapers import LectulandiaScraper, EpuberaScraper
import logging
from slugify import slugify
from app.models.user import User
from app.core.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/books", tags=["books"])


# ============================================================================
# SEARCH & DISCOVERY
# ============================================================================

@router.get("/search", response_model=BookSearchResponse)
async def search_books(
    q: str = Query(..., min_length=2, max_length=200, description="Search query"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=40),
    language: Optional[str] = Query(None, description="Language filter (es, en, etc.)"),
    source: str = Query("all", description="Search source (all, google, openlibrary, scrapers, lectulandia)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Search books on Google Books, Open Library, or EPUB scrapers

    Sources:
    - all: Combines Google Books + scrapers (recommended)
    - google: Google Books only
    - openlibrary: Open Library only
    - scrapers: All EPUB scrapers (lectulandia, epubera)
    - lectulandia: Lectulandia scraper only
    - epubera: Epubera scraper only
    """
    results = []

    try:
        # Search in Google Books
        if source in ["all", "google"]:
            google_books = get_google_books_service()
            search_results = await google_books.search_books(q, page=page, per_page=limit, language=language)

            for item in search_results['results']:
                # Check if already in library
                in_library = db.query(Book).filter(
                    Book.google_books_id == item.get('google_books_id'),
                    Book.user_id == current_user.id
                ).first()

                results.append({
                    **item,
                    'in_library': bool(in_library),
                    'library_id': in_library.id if in_library else None,
                    'source': 'google_books'
                })

        # Search in Open Library
        elif source == "openlibrary":
            openlibrary = get_openlibrary_service()
            search_results = await openlibrary.search_books(q, page=page, per_page=limit)

            for item in search_results['results']:
                in_library = db.query(Book).filter(
                    Book.openlibrary_id == item.get('openlibrary_id'),
                    Book.user_id == current_user.id
                ).first()

                results.append({
                    **item,
                    'in_library': bool(in_library),
                    'library_id': in_library.id if in_library else None,
                    'source': 'openlibrary'
                })

        # Search in scrapers (parallel)
        scraper_results = []
        scraper_title_index: dict = {}

        scraper_tasks = []
        if source in ["all", "scrapers", "lectulandia"]:
            scraper_tasks.append(("lectulandia", asyncio.wait_for(LectulandiaScraper().search(q, page=page), timeout=45.0)))
        if source in ["all", "scrapers", "epubera"]:
            scraper_tasks.append(("epubera", asyncio.wait_for(EpuberaScraper().search(q, page=page), timeout=30.0)))

        if scraper_tasks:
            gathered = await asyncio.gather(
                *[task for _, task in scraper_tasks],
                return_exceptions=True
            )

            for (scraper_name, _), result in zip(scraper_tasks, gathered):
                if isinstance(result, Exception):
                    logger.error(f"{scraper_name} search error: {result}")
                    continue

                for item in (result or []):
                    title_norm = item['title'].lower().strip()

                    # If already indexed by another scraper, merge sources
                    if title_norm in scraper_title_index:
                        existing_src, existing_url = scraper_title_index[title_norm]
                        scraper_title_index[title_norm] = (f"{existing_src},{scraper_name}", existing_url)
                        for sr in scraper_results:
                            if sr['title'].lower().strip() == title_norm:
                                sr['scraper_sources'].append(scraper_name)
                                break
                        continue

                    scraper_title_index[title_norm] = (scraper_name, item['url'])

                    in_library = db.query(Book).filter(
                        Book.title.ilike(f"%{item['title'][:40]}%"),
                        Book.user_id == current_user.id
                    ).first()

                    scraper_results.append({
                        'title': item['title'],
                        'cover_image': item.get('cover'),
                        'thumbnail': item.get('cover'),
                        'source': scraper_name,
                        'source_url': item['url'],
                        'scraper_sources': [scraper_name],
                        'scraper_url': item['url'],
                        'in_library': bool(in_library),
                        'library_id': in_library.id if in_library else None,
                        'authors': [item['author']] if item.get('author') else [],
                        'google_books_id': None,
                        'description': None,
                        'published_date': None,
                        'publisher': None,
                    })

        # Cross-reference: annotate Google Books results with scraper availability
        for result in results:
            title_key = result['title'].lower().strip()
            matched_sources = []
            matched_url = None
            for scraper_title, (src_names, src_url) in scraper_title_index.items():
                if title_key[:35] in scraper_title or scraper_title[:35] in title_key:
                    matched_sources = [s for s in src_names.split(",") if s]
                    matched_url = src_url
                    break
            result['scraper_sources'] = matched_sources
            result['scraper_url'] = matched_url

        # Add scraper results (as separate cards when not found via Google Books)
        results.extend(scraper_results)

        # Remove duplicates by title (case-insensitive)
        seen_titles = set()
        unique_results = []
        for result in results:
            title_key = result['title'].lower().strip()
            if title_key not in seen_titles:
                seen_titles.add(title_key)
                unique_results.append(result)

        # Limit results
        unique_results = unique_results[:limit]

        return BookSearchResponse(
            results=unique_results,
            total=len(unique_results),
            page=page,
            per_page=limit
        )

    except Exception as e:
        logger.error(f"Error searching books: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


# ============================================================================
# LIBRARY MANAGEMENT
# ============================================================================

@router.get("/library", response_model=List[BookResponse])
async def get_library(
    monitored: Optional[bool] = Query(None, description="Filter by monitored status"),
    search: Optional[str] = Query(None, description="Search in library"),
    sort: str = Query("title", description="Sort by: title, rating, recent"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get books library with filtering and sorting
    """
    query = db.query(Book).filter(Book.user_id == current_user.id)

    # Apply filters
    if monitored is not None:
        query = query.filter(Book.monitored == monitored)

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                Book.title.ilike(search_term),
                Book.title_original.ilike(search_term),
                func.json_array_length(Book.authors) > 0
            )
        )

    # Apply sorting
    if sort == "rating":
        query = query.order_by(Book.average_rating.desc().nullslast())
    elif sort == "recent":
        query = query.order_by(Book.created_at.desc())
    else:  # title
        query = query.order_by(Book.title.asc())

    # Pagination
    offset = (page - 1) * limit
    books = query.offset(offset).limit(limit).all()

    # Add computed fields
    result = []
    for book in books:
        book_dict = BookResponse.from_orm(book).dict()
        book_dict['total_chapters'] = book.total_chapters
        book_dict['downloaded_chapters'] = book.downloaded_chapters
        result.append(BookResponse(**book_dict))

    return result


@router.get("/library/stats", response_model=BookLibraryStats)
async def get_library_stats(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Get library statistics
    """
    user_book_ids = db.query(Book.id).filter(Book.user_id == current_user.id).scalar_subquery()
    total_books = db.query(Book).filter(Book.user_id == current_user.id).count()
    monitored_books = db.query(Book).filter(Book.user_id == current_user.id, Book.monitored == True).count()

    total_files = db.query(BookChapter).filter(BookChapter.book_id.in_(user_book_ids)).count()
    downloaded_files = db.query(BookChapter).filter(
        BookChapter.book_id.in_(user_book_ids),
        BookChapter.status.in_(["downloaded", "sent"])
    ).count()
    sent_files = db.query(BookChapter).filter(BookChapter.book_id.in_(user_book_ids), BookChapter.status == "sent").count()

    return BookLibraryStats(
        total_books=total_books,
        monitored_books=monitored_books,
        total_files=total_files,
        downloaded_files=downloaded_files,
        sent_files=sent_files
    )


@router.get("/{book_id}/stats")
async def get_book_stats(book_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Get download statistics for a specific book
    """
    book = db.query(Book).filter(Book.id == book_id, Book.user_id == current_user.id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    # Count chapters by status
    chapters = db.query(BookChapter).filter(BookChapter.book_id == book_id).all()

    stats = {
        "total_chapters": len(chapters),
        "downloaded": sum(1 for c in chapters if c.status in ["downloaded", "converted"]),
        "downloading": sum(1 for c in chapters if c.status == "downloading"),
        "pending": sum(1 for c in chapters if c.status == "pending"),
        "failed": sum(1 for c in chapters if c.status == "error"),
        "sent_to_kindle": sum(1 for c in chapters if c.status == "sent" or c.sent_at)
    }

    return stats


@router.get("/{book_id}", response_model=BookDetailResponse)
async def get_book(book_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Get detailed book information with chapters
    """
    book = db.query(Book).filter(Book.id == book_id, Book.user_id == current_user.id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    # Get chapters
    chapters = db.query(BookChapter).filter(
        BookChapter.book_id == book_id
    ).order_by(BookChapter.number.asc()).all()

    book_dict = BookResponse.from_orm(book).dict()
    book_dict['total_chapters'] = book.total_chapters
    book_dict['downloaded_chapters'] = book.downloaded_chapters
    book_dict['chapters'] = [BookChapterResponse.from_orm(ch) for ch in chapters]

    return BookDetailResponse(**book_dict)


# ============================================================================
# ADD BOOKS TO LIBRARY
# ============================================================================

@router.post("/from-google-books", response_model=BookResponse)
async def add_book_from_google_books(
    data: BookCreateFromGoogleBooks,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    force: bool = Query(False, description="Skip duplicate check")
):
    """
    Add book to library from Google Books ID
    Automatically searches all scrapers for download links
    """
    # Check if already exists for this user
    existing = db.query(Book).filter(
        Book.google_books_id == data.google_books_id,
        Book.user_id == current_user.id
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Book already in library")

    # Fetch metadata from Google Books
    google_books = get_google_books_service()
    metadata = await google_books.get_book_by_id(data.google_books_id)

    if not metadata:
        raise HTTPException(status_code=404, detail="Book not found on Google Books")

    # Feature 6: Fuzzy duplicate check (skip if force=True)
    if not force:
        from app.services.content_matcher import ContentMatcher
        matcher = ContentMatcher()
        duplicate = matcher.find_duplicate(db, metadata['title'], 'book', current_user.id)
        if duplicate:
            raise HTTPException(
                status_code=409,
                detail={"message": "Posible duplicado encontrado", "matched_id": duplicate.id, "matched_title": duplicate.title}
            )

    # Create book
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
        preview_link=metadata.get('preview_link'),
        info_link=metadata.get('info_link'),
        monitored=data.monitored,
        auto_download=data.auto_download,
        user_id=current_user.id,
        source_urls={}
    )

    db.add(book)
    db.commit()
    db.refresh(book)

    # Search in scrapers in background
    background_tasks.add_task(_search_scrapers_for_book, book.id, metadata['title'])

    return BookResponse.from_orm(book)


@router.post("/from-url", response_model=BookResponse)
async def add_book_from_url(
    data: BookCreateFromURL,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Add book from scraper URL directly
    """
    # Detect scraper from URL
    scraper_name = data.scraper_name
    if not scraper_name:
        if 'epubera.com' in data.source_url:
            scraper_name = 'epubera'
        elif 'lectulandia' in data.source_url:
            scraper_name = 'lectulandia'
        else:
            raise HTTPException(status_code=400, detail="Could not detect scraper from URL")

    scrapers = {
        'epubera': EpuberaScraper,
        'lectulandia': LectulandiaScraper,
    }

    scraper_cls = scrapers.get(scraper_name)
    if not scraper_cls:
        raise HTTPException(status_code=400, detail=f"Unknown scraper: {scraper_name}")
    scraper = scraper_cls()

    # Scrape book page
    result = await scraper.get_download_links(data.source_url)

    if not result.success:
        raise HTTPException(status_code=400, detail=f"Scraping failed: {result.error}")

    # Create book
    book = Book(
        title=result.title,
        slug=slugify(result.title),
        description=result.description,
        cover_image=result.cover_image,
        language="es",
        monitored=data.monitored,
        auto_download=data.auto_download,
        user_id=current_user.id,
        source_urls={scraper_name: data.source_url},
        preferred_source=scraper_name
    )

    # Try to enrich with Google Books metadata if provided
    if data.google_books_id:
        google_books = get_google_books_service()
        metadata = await google_books.get_book_by_id(data.google_books_id)
        if metadata:
            book.google_books_id = metadata['google_books_id']
            book.authors = metadata.get('authors', [])
            book.publisher = metadata.get('publisher')
            book.published_date = metadata.get('published_date')
            book.isbn_10 = metadata.get('isbn_10')
            book.isbn_13 = metadata.get('isbn_13')
            book.categories = metadata.get('categories', [])
            book.average_rating = metadata.get('average_rating')

    db.add(book)
    db.commit()
    db.refresh(book)

    # Create chapter entry for download
    if result.best_link:
        chapter = BookChapter(
            book_id=book.id,
            number=1,
            title=result.title,
            download_url=result.best_link.url,
            backup_url=result.backup_link.url if result.backup_link else None,
            source=scraper_name,
            status="pending"
        )
        db.add(chapter)
        db.commit()

    return BookResponse.from_orm(book)


# ============================================================================
# UPDATE & DELETE
# ============================================================================

@router.patch("/{book_id}", response_model=BookResponse)
async def update_book(
    book_id: int,
    data: BookUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update book settings
    """
    book = db.query(Book).filter(Book.id == book_id, Book.user_id == current_user.id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    # Update fields
    update_data = data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(book, field, value)

    book.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(book)

    return BookResponse.from_orm(book)


@router.delete("/{book_id}")
async def delete_book(book_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Delete book from library
    """
    book = db.query(Book).filter(Book.id == book_id, Book.user_id == current_user.id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    db.delete(book)
    db.commit()

    return {"message": "Book deleted successfully"}


@router.post("/{book_id}/refresh")
async def refresh_book(
    book_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Refresh book - re-check scrapers for new files
    """
    book = db.query(Book).filter(Book.id == book_id, Book.user_id == current_user.id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    # Re-search scrapers and enrich metadata
    background_tasks.add_task(_search_scrapers_for_book, book.id, book.title)
    background_tasks.add_task(_enrich_book_metadata, book.id)

    return {"message": "Refresh started"}


# ============================================================================
# CHAPTERS
# ============================================================================

@router.get("/{book_id}/chapters", response_model=List[BookChapterResponse])
async def get_book_chapters(book_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Get chapters for a book
    """
    book = db.query(Book).filter(Book.id == book_id, Book.user_id == current_user.id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    chapters = db.query(BookChapter).filter(
        BookChapter.book_id == book_id
    ).order_by(BookChapter.number.asc()).all()

    return [BookChapterResponse.from_orm(ch) for ch in chapters]


@router.post("/{book_id}/chapters/download", status_code=202)
async def download_chapters(
    book_id: int,
    data: ChapterDownloadRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Queue selected chapters for download using the download queue system
    """
    book = db.query(Book).filter(Book.id == book_id, Book.user_id == current_user.id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    # Verify chapters exist
    chapters = db.query(BookChapter).filter(
        BookChapter.id.in_(data.chapter_ids),
        BookChapter.book_id == book_id
    ).all()

    if len(chapters) != len(data.chapter_ids):
        raise HTTPException(status_code=400, detail="Some chapter IDs are invalid")

    queued_count = 0

    # Add to download queue
    for chapter in chapters:
        if chapter.status in ["pending", "error"]:
            # Check if already in queue
            existing = db.query(DownloadQueue).filter(
                DownloadQueue.book_chapter_id == chapter.id,
                DownloadQueue.status.in_(['queued', 'downloading'])
            ).first()

            if not existing:
                # Add to queue
                queue_item = DownloadQueue(
                    book_chapter_id=chapter.id,
                    content_type='book',
                    status='queued',
                    priority=0
                )
                db.add(queue_item)
                queued_count += 1

            # Mark chapter as downloading
            chapter.status = "downloading"

    db.commit()

    return {
        "status": "queued",
        "book_id": book_id,
        "chapters_queued": queued_count,
        "message": f"{queued_count} chapters added to download queue"
    }


@router.post("/{book_id}/chapters/{chapter_id}/send-to-kindle")
async def send_book_to_kindle(
    book_id: int,
    chapter_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Send downloaded book EPUB to Kindle via STK
    """
    from app.services.stk_kindle_sender import get_stk_sender

    sender = get_stk_sender(current_user.id)

    if not sender.is_authenticated():
        raise HTTPException(
            status_code=401,
            detail="STK not authenticated. Go to Settings and authorize with Amazon."
        )

    # Get book chapter
    chapter = db.query(BookChapter).filter(
        BookChapter.id == chapter_id,
        BookChapter.book_id == book_id
    ).first()

    if not chapter:
        raise HTTPException(status_code=404, detail="Book chapter not found")

    if not chapter.file_path or not chapter.file_path.endswith('.epub'):
        raise HTTPException(status_code=400, detail="Book has not been downloaded in EPUB format")

    # Verify file exists
    file_path = Path(chapter.file_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=400,
            detail=f"EPUB file not found: {chapter.file_path}"
        )

    # Get book info
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    # Get author
    author = "Unknown"
    if book.authors and len(book.authors) > 0:
        author = book.authors[0]

    # Get device serials from user settings
    device_serials = None
    if current_user.stk_device_serial:
        device_serials = [current_user.stk_device_serial]
        logger.info(f"Using saved device: {current_user.stk_device_name or current_user.stk_device_serial}")

    # Send to Kindle
    title = book.title
    if chapter.title and chapter.title != book.title:
        title = f"{book.title} - {chapter.title}"

    result = sender.send_file(
        file_path=file_path,
        title=title,
        author=author,
        device_serials=device_serials
    )

    if result['success']:
        chapter.sent_at = datetime.utcnow()
        chapter.status = "sent"
        db.commit()

        logger.info(f"Sent {file_path.name} to Kindle")
        return {
            "success": True,
            "message": f"Book sent to Kindle successfully",
            "title": title
        }
    else:
        logger.error(f"Failed to send {file_path.name}: {result['message']}")
        raise HTTPException(status_code=500, detail=result['message'])


@router.post("/{book_id}/chapters/{chapter_id}/mark-read")
async def mark_book_chapter_read(
    book_id: int,
    chapter_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark a book chapter as read"""
    book = db.query(Book).filter(Book.id == book_id, Book.user_id == current_user.id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    chapter = db.query(BookChapter).filter(BookChapter.id == chapter_id, BookChapter.book_id == book_id).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    chapter.read_at = datetime.utcnow()
    book.last_read_chapter = chapter.number

    total_sent = db.query(BookChapter).filter(
        BookChapter.book_id == book_id,
        BookChapter.status.in_(['sent', 'converted', 'downloaded'])
    ).count()
    total_read = db.query(BookChapter).filter(
        BookChapter.book_id == book_id,
        BookChapter.read_at.isnot(None)
    ).count() + 1
    book.reading_status = 'completed' if total_read >= total_sent and total_sent > 0 else 'reading'

    db.commit()
    return {"id": chapter_id, "read_at": chapter.read_at.isoformat()}


@router.post("/{book_id}/mark-all-read")
async def mark_all_book_chapters_read(
    book_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark all sent/downloaded book chapters as read"""
    book = db.query(Book).filter(Book.id == book_id, Book.user_id == current_user.id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    now = datetime.utcnow()
    chapters = db.query(BookChapter).filter(
        BookChapter.book_id == book_id,
        BookChapter.status.in_(['sent', 'converted', 'downloaded']),
        BookChapter.read_at.is_(None)
    ).all()

    for ch in chapters:
        ch.read_at = now

    if chapters:
        book.last_read_chapter = max(ch.number for ch in chapters)
        book.reading_status = 'completed'

    db.commit()
    return {"marked_read": len(chapters)}


class BookReadingStatusUpdate(BaseModel):
    status: str  # not_started | reading | completed


@router.patch("/{book_id}/reading-status")
async def update_book_reading_status(
    book_id: int,
    body: BookReadingStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Set reading status directly, without requiring downloaded chapters."""
    valid = {'not_started', 'reading', 'completed'}
    if body.status not in valid:
        raise HTTPException(status_code=400, detail=f"status must be one of {valid}")

    book = db.query(Book).filter(Book.id == book_id, Book.user_id == current_user.id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    book.reading_status = body.status

    if body.status == 'completed':
        now = datetime.utcnow()
        chapters = db.query(BookChapter).filter(
            BookChapter.book_id == book_id,
            BookChapter.read_at.is_(None)
        ).all()
        for ch in chapters:
            ch.read_at = now
        if chapters:
            book.last_read_chapter = max(ch.number for ch in chapters)

    db.commit()
    return {"id": book_id, "reading_status": book.reading_status}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def _search_scrapers_for_book(book_id: int, title: str):
    """
    Search all scrapers for a book and create chapters.
    Runs Lectulandia + Epubera in parallel, picks best link across all sources.
    """
    from app.database import SessionLocal
    db = SessionLocal()

    try:
        book = db.query(Book).filter(Book.id == book_id).first()
        if not book:
            return

        scrapers = [LectulandiaScraper(), EpuberaScraper()]
        title_lower = title.lower().strip()
        title_keywords = set(w for w in title_lower.split() if len(w) > 2)

        async def _search_one(scraper):
            try:
                results = await asyncio.wait_for(scraper.search(title, page=1), timeout=45.0)
                if not results:
                    return None

                # Find best matching result by title similarity
                best = None
                best_score = 0
                for r in results:
                    r_title = r['title'].lower().strip()
                    r_keywords = set(w for w in r_title.split() if len(w) > 2)

                    if r_title == title_lower or title_lower in r_title or r_title in title_lower:
                        score = 100
                    else:
                        overlap = len(title_keywords & r_keywords)
                        min_needed = min(2, max(1, len(title_keywords) // 2))
                        score = overlap * 10 if overlap >= min_needed else 0

                    if score > best_score:
                        best_score = score
                        best = r

                if not best or best_score == 0:
                    logger.info(f"{scraper.name}: No good title match for '{title}'")
                    return None

                logger.info(f"{scraper.name}: Best match '{best['title']}' (score={best_score})")
                dl_result = await asyncio.wait_for(scraper.get_download_links(best['url']), timeout=60.0)

                if dl_result.success and dl_result.best_link:
                    return (scraper.name, best, dl_result)
                return None
            except Exception as e:
                logger.error(f"Error searching {scraper.name} for book {book_id}: {e}")
                return None

        # Run all scrapers in parallel
        gathered = await asyncio.gather(*[_search_one(s) for s in scrapers], return_exceptions=True)

        all_links = []
        for result in gathered:
            if isinstance(result, Exception) or result is None:
                continue
            scraper_name, search_hit, dl_result = result

            if not book.source_urls:
                book.source_urls = {}
            book.source_urls[scraper_name] = search_hit['url']

            for link in dl_result.download_links:
                all_links.append((scraper_name, link))

        if not all_links:
            logger.info(f"No download links found for book {book_id} across any scraper")
            db.commit()
            return

        # Sort by quality score descending
        all_links.sort(key=lambda x: x[1].quality_score, reverse=True)

        best_name, best_link = all_links[0]
        backup_link = all_links[1][1] if len(all_links) > 1 else None

        logger.info(f"Book {book_id}: best link from {best_name} ({best_link.host.value}, score={best_link.quality_score})")

        if not book.preferred_source:
            book.preferred_source = best_name

        existing_chapter = db.query(BookChapter).filter(
            BookChapter.book_id == book_id,
            BookChapter.number == 1
        ).first()

        if existing_chapter:
            existing_chapter.download_url = best_link.url
            existing_chapter.backup_url = backup_link.url if backup_link else existing_chapter.backup_url
            existing_chapter.source = best_name
        else:
            chapter = BookChapter(
                book_id=book_id,
                number=1,
                title=book.title,
                download_url=best_link.url,
                backup_url=backup_link.url if backup_link else None,
                source=best_name,
                status="pending"
            )
            db.add(chapter)

        db.commit()

    finally:
        db.close()


async def _download_book_chapter(chapter_id: int):
    """
    Download a book chapter (EPUB file)
    Background task
    """
    from app.database import SessionLocal
    from app.services.book_downloader import BookDownloader
    import os

    db = SessionLocal()

    try:
        chapter = db.query(BookChapter).filter(BookChapter.id == chapter_id).first()
        if not chapter:
            logger.error(f"Chapter {chapter_id} not found")
            return

        book = db.query(Book).filter(Book.id == chapter.book_id).first()
        if not book:
            logger.error(f"Book {chapter.book_id} not found")
            return

        logger.info(f"Starting download for: {book.title}")
        logger.info(f"Download URL: {chapter.download_url}")

        # Check if URL is from an intermediate host that needs resolving
        needs_resolving = any(host in chapter.download_url.lower()
                            for host in ['antupload.com', 'beeupload', 'fireload', 'krakenfiles.com/view', 'send.now'])

        # Sanitize filename
        safe_title = "".join(c for c in book.title if c.isalnum() or c in (' ', '-', '_')).strip()
        filename = f"{safe_title}.epub"

        # If the URL needs resolving with Playwright, use Playwright to download directly
        if needs_resolving:
            from pathlib import Path
            download_dir = Path("/downloads/books")
            download_dir.mkdir(parents=True, exist_ok=True)
            download_path = download_dir / filename

            # Send.now: simple click sin captcha — downloader dedicado
            if 'send.now' in chapter.download_url.lower():
                logger.info("SendNow: usando downloader dedicado...")
                from app.services.sendnow_downloader import download_from_sendnow
                ok = await download_from_sendnow(chapter.download_url, download_path)
                if not ok:
                    raise Exception("SendNow download failed — ver logs para detalles")
                result_path = download_path

            # KrakenFiles: usa Cloudflare Turnstile — requiere 2captcha para resolver
            elif 'krakenfiles.com' in chapter.download_url.lower():
                logger.info("KrakenFiles: usando downloader dedicado (Turnstile + 2captcha)...")
                from app.services.krakenfiles_downloader import download_from_krakenfiles
                ok = await download_from_krakenfiles(chapter.download_url, download_path)
                if not ok:
                    raise Exception("KrakenFiles download failed — ver logs para detalles")
                result_path = download_path

            else:
                # Otros hosts (antupload, fireload, etc.) — Playwright + expect_download
                logger.info(f"Downloading with Playwright (intermediate host)...")
                from app.services.book_scrapers.playwright_scraper import get_playwright_scraper

                playwright_scraper = await get_playwright_scraper()
                page = await playwright_scraper._create_page()

                try:
                    logger.info(f"Navigating to {chapter.download_url}")
                    await page.goto(chapter.download_url, wait_until='domcontentloaded', timeout=30000)
                    await asyncio.sleep(3)

                    download_btn = None
                    if 'antupload.com' in chapter.download_url.lower():
                        download_btn = await page.query_selector('#downloadB')
                    else:
                        download_btn = await page.query_selector('a.btn-download, a[href*="download"], button:has-text("Download")')

                    if not download_btn:
                        raise Exception("Download button not found on page")

                    async with page.expect_download(timeout=60000) as download_info:
                        await download_btn.click()
                    download = await download_info.value
                    await download.save_as(str(download_path))
                    logger.info(f"✅ Downloaded with Playwright: {filename}")
                    result_path = download_path

                except Exception as e:
                    logger.error(f"Playwright download failed: {e}")
                    raise

                finally:
                    await page.close()

        else:
            # For direct links, use the normal downloader
            downloader = BookDownloader(download_dir="/downloads/books")

            def on_progress(current, total):
                # Update progress in DB if needed
                pass

            # Prepare backup URLs
            backup_urls = [chapter.backup_url] if chapter.backup_url else []

            # Download book
            result_path = await downloader.download_book(
                url=chapter.download_url,
                filename=filename,
                on_progress=on_progress,
                backup_urls=backup_urls
            )

        if result_path and result_path.exists():
            # Update chapter status
            chapter.status = "downloaded"
            chapter.file_path = str(result_path)
            chapter.file_size = os.path.getsize(result_path)
            chapter.downloaded_at = datetime.now()
            logger.info(f"✅ Downloaded: {book.title} ({chapter.file_size / (1024*1024):.2f} MB)")
        else:
            chapter.status = "error"
            chapter.error_message = "Download failed"
            logger.error(f"❌ Download failed for: {book.title}")

        db.commit()

    except Exception as e:
        logger.error(f"Error downloading chapter {chapter_id}: {e}")
        if chapter:
            chapter.status = "error"
            chapter.error_message = str(e)
            db.commit()
    finally:
        db.close()


async def _enrich_book_metadata(book_id: int):
    """Background task to enrich book metadata from Google Books"""
    from app.database import SessionLocal
    from app.services.metadata_enricher import get_metadata_enricher

    db = SessionLocal()
    try:
        enricher = get_metadata_enricher()
        await enricher.enrich_book(book_id, db)
    finally:
        db.close()
