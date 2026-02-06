"""
Books API Endpoints - Integration with Google Books and EPUB Scrapers
"""

from datetime import datetime
import asyncio
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
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
from app.services.book_scrapers import LectulandiaScraper
import logging
from slugify import slugify

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/books", tags=["books"])


# ============================================================================
# SEARCH & DISCOVERY
# ============================================================================

@router.get("/search", response_model=BookSearchResponse)
async def search_books(
    q: str = Query(..., min_length=2, description="Search query"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=40),
    language: Optional[str] = Query(None, description="Language filter (es, en, etc.)"),
    source: str = Query("all", description="Search source (all, google, openlibrary, scrapers, lectulandia)"),
    db: Session = Depends(get_db)
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
                    Book.google_books_id == item.get('google_books_id')
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
                    Book.openlibrary_id == item.get('openlibrary_id')
                ).first()

                results.append({
                    **item,
                    'in_library': bool(in_library),
                    'library_id': in_library.id if in_library else None,
                    'source': 'openlibrary'
                })

        # Search in scrapers
        if source in ["all", "scrapers", "lectulandia"]:
            scraper_results = []

            # Only search Lectulandia (most reliable with Playwright)
            if source in ["all", "scrapers", "lectulandia"]:
                try:
                    lectulandia = LectulandiaScraper()
                    lect_results = await lectulandia.search(q, page=page)

                    for item in lect_results:
                        # Check by title (fuzzy match)
                        # Note: Can't use .contains() on JSON field in PostgreSQL easily
                        in_library = db.query(Book).filter(
                            Book.title.ilike(f"%{item['title'][:40]}%")
                        ).first()

                        scraper_results.append({
                            'title': item['title'],
                            'cover_image': item.get('cover'),
                            'thumbnail': item.get('cover'),
                            'source': 'lectulandia',
                            'source_url': item['url'],
                            'in_library': bool(in_library),
                            'library_id': in_library.id if in_library else None,
                            # Add placeholders for fields expected by frontend
                            'authors': [],
                            'google_books_id': None,
                            'description': None,
                            'published_date': None,
                            'publisher': None,
                        })
                except Exception as e:
                    logger.error(f"Lectulandia search error: {e}")

            # Add scraper results to main results
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
    db: Session = Depends(get_db)
):
    """
    Get books library with filtering and sorting
    """
    query = db.query(Book)

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
async def get_library_stats(db: Session = Depends(get_db)):
    """
    Get library statistics
    """
    total_books = db.query(Book).count()
    monitored_books = db.query(Book).filter(Book.monitored == True).count()

    total_files = db.query(BookChapter).count()
    downloaded_files = db.query(BookChapter).filter(
        BookChapter.status.in_(["downloaded", "sent"])
    ).count()
    sent_files = db.query(BookChapter).filter(BookChapter.status == "sent").count()

    return BookLibraryStats(
        total_books=total_books,
        monitored_books=monitored_books,
        total_files=total_files,
        downloaded_files=downloaded_files,
        sent_files=sent_files
    )


@router.get("/{book_id}/stats")
async def get_book_stats(book_id: int, db: Session = Depends(get_db)):
    """
    Get download statistics for a specific book
    """
    book = db.query(Book).filter(Book.id == book_id).first()
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
async def get_book(book_id: int, db: Session = Depends(get_db)):
    """
    Get detailed book information with chapters
    """
    book = db.query(Book).filter(Book.id == book_id).first()
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
    db: Session = Depends(get_db)
):
    """
    Add book to library from Google Books ID
    Automatically searches all scrapers for download links
    """
    # Check if already exists
    existing = db.query(Book).filter(
        Book.google_books_id == data.google_books_id
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Book already in library")

    # Fetch metadata from Google Books
    google_books = get_google_books_service()
    metadata = await google_books.get_book_by_id(data.google_books_id)

    if not metadata:
        raise HTTPException(status_code=404, detail="Book not found on Google Books")

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
    db: Session = Depends(get_db)
):
    """
    Add book from scraper URL directly
    """
    # Detect scraper from URL
    scrapers = {
        'epubera': EpuberaScraper(),
        'lectulandia': LectulandiaScraper()
    }

    scraper_name = data.scraper_name
    if not scraper_name:
        # Auto-detect from URL
        if 'epubera.com' in data.source_url:
            scraper_name = 'epubera'
        elif 'lectulandia' in data.source_url:
            scraper_name = 'lectulandia'
        else:
            raise HTTPException(status_code=400, detail="Could not detect scraper from URL")

    scraper = scrapers.get(scraper_name)
    if not scraper:
        raise HTTPException(status_code=400, detail=f"Unknown scraper: {scraper_name}")

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
    db: Session = Depends(get_db)
):
    """
    Update book settings
    """
    book = db.query(Book).filter(Book.id == book_id).first()
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
async def delete_book(book_id: int, db: Session = Depends(get_db)):
    """
    Delete book from library
    """
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    db.delete(book)
    db.commit()

    return {"message": "Book deleted successfully"}


@router.post("/{book_id}/refresh")
async def refresh_book(
    book_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Refresh book - re-check scrapers for new files
    """
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    # Re-search scrapers
    background_tasks.add_task(_search_scrapers_for_book, book.id, book.title)

    return {"message": "Refresh started"}


# ============================================================================
# CHAPTERS
# ============================================================================

@router.get("/{book_id}/chapters", response_model=List[BookChapterResponse])
async def get_book_chapters(book_id: int, db: Session = Depends(get_db)):
    """
    Get chapters for a book
    """
    book = db.query(Book).filter(Book.id == book_id).first()
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
    db: Session = Depends(get_db)
):
    """
    Queue selected chapters for download using the download queue system
    """
    book = db.query(Book).filter(Book.id == book_id).first()
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
    db: Session = Depends(get_db)
):
    """
    Send downloaded book EPUB to Kindle via STK
    """
    from app.services.stk_kindle_sender import get_stk_sender
    from app.models.settings import AppSettings

    sender = get_stk_sender()

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

    # Get device serials from settings
    device_serials = None
    settings = db.query(AppSettings).first()
    if settings and settings.stk_device_serial:
        device_serials = [settings.stk_device_serial]
        logger.info(f"Using saved device: {settings.stk_device_name or settings.stk_device_serial}")

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


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def _search_scrapers_for_book(book_id: int, title: str):
    """
    Search all scrapers for a book and create chapters
    Background task
    """
    from app.database import SessionLocal
    db = SessionLocal()

    try:
        book = db.query(Book).filter(Book.id == book_id).first()
        if not book:
            return

        scrapers = [
            LectulandiaScraper()
        ]

        for scraper in scrapers:
            try:
                # Search for book
                search_results = await scraper.search(title, page=1)

                if search_results:
                    # Take first result
                    first_result = search_results[0]

                    # Get download links
                    result = await scraper.get_download_links(first_result['url'])

                    if result.success and result.best_link:
                        # Update source URLs
                        if not book.source_urls:
                            book.source_urls = {}
                        book.source_urls[scraper.name] = first_result['url']

                        if not book.preferred_source:
                            book.preferred_source = scraper.name

                        # Create chapter if doesn't exist
                        existing_chapter = db.query(BookChapter).filter(
                            BookChapter.book_id == book_id,
                            BookChapter.source == scraper.name
                        ).first()

                        if not existing_chapter:
                            chapter = BookChapter(
                                book_id=book_id,
                                number=1,
                                title=book.title,
                                download_url=result.best_link.url,
                                backup_url=result.backup_link.url if result.backup_link else None,
                                source=scraper.name,
                                status="pending"
                            )
                            db.add(chapter)

                        db.commit()

            except Exception as e:
                logger.error(f"Error searching {scraper.name} for book {book_id}: {e}")
                continue

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
                            for host in ['antupload.com', 'beeupload', 'fireload', 'krakenfiles.com/view'])

        # Sanitize filename
        safe_title = "".join(c for c in book.title if c.isalnum() or c in (' ', '-', '_')).strip()
        filename = f"{safe_title}.epub"

        # If the URL needs resolving with Playwright, use Playwright to download directly
        if needs_resolving:
            logger.info(f"Downloading with Playwright (intermediate host)...")
            from app.services.book_scrapers.playwright_scraper import get_playwright_scraper
            from pathlib import Path

            playwright_scraper = await get_playwright_scraper()
            page = await playwright_scraper._create_page()

            try:
                # Navigate to the intermediate host page
                logger.info(f"Navigating to {chapter.download_url}")
                await page.goto(chapter.download_url, wait_until='domcontentloaded', timeout=30000)
                await asyncio.sleep(3)

                # Find the download button - different selectors for different hosts
                download_btn = None

                # Krakenfiles selectors
                if 'krakenfiles.com' in chapter.download_url.lower():
                    logger.info("Looking for krakenfiles download button...")
                    # Try multiple selectors for krakenfiles
                    selectors = [
                        'button.btn-primary:has-text("Download")',
                        'button:has-text("Download now")',
                        'a:has-text("Download now")',
                        'button.btn-primary',
                        'a.download-url',
                        'a[href*="krakenfiles.com/file/"]',
                        'button:has-text("Free Download")',
                        'a:has-text("Free Download")',
                        'a.btn-primary',
                        '.download-button',
                        'a[href*="/file/"]'
                    ]
                    for selector in selectors:
                        try:
                            btn = await page.query_selector(selector)
                            if btn and await btn.is_visible():
                                download_btn = btn
                                logger.info(f"Found download button with selector: {selector}")
                                break
                        except:
                            continue

                # Antupload selectors (already working)
                elif 'antupload.com' in chapter.download_url.lower():
                    logger.info("Looking for antupload download button...")
                    download_btn = await page.query_selector('#downloadB')

                # Generic selectors for other hosts
                else:
                    logger.info("Looking for generic download button...")
                    download_btn = await page.query_selector('a.btn-download, a[href*="download"], button:has-text("Download")')

                if not download_btn:
                    # Take a screenshot and dump HTML for debugging
                    logger.error("Download button not found. Taking screenshot and logging HTML...")
                    await page.screenshot(path='/downloads/books/debug_screenshot.png')

                    # Get page HTML for debugging
                    html_content = await page.content()
                    logger.error(f"Page HTML length: {len(html_content)}")

                    # Log all links and buttons on the page
                    all_links = await page.query_selector_all('a')
                    all_buttons = await page.query_selector_all('button')
                    logger.error(f"Found {len(all_links)} links and {len(all_buttons)} buttons on page")

                    # Check for links with "download" or "free" in href or text
                    for i, link in enumerate(all_links):
                        try:
                            href = await link.get_attribute('href')
                            text = await link.inner_text()
                            classes = await link.get_attribute('class')

                            if href and ('download' in href.lower() or 'file' in href.lower() or 'free' in (text or '').lower()):
                                logger.error(f"Potential download link {i+1}: href={href}, text={text[:50] if text else 'N/A'}, class={classes}")
                        except:
                            pass

                    # Check buttons
                    for i, btn in enumerate(all_buttons[:5]):
                        try:
                            text = await btn.inner_text()
                            classes = await btn.get_attribute('class')
                            logger.error(f"Button {i+1}: text={text[:50] if text else 'N/A'}, class={classes}")
                        except:
                            pass

                    raise Exception("Download button not found on page")

                logger.info("Found download button, attempting to click...")

                # Set up download path
                download_dir = Path("/downloads/books")
                download_dir.mkdir(parents=True, exist_ok=True)
                download_path = download_dir / filename

                # Try to trigger the download
                try:
                    logger.info("Waiting for download event...")
                    async with page.expect_download(timeout=30000) as download_info:
                        await download_btn.click()
                        logger.info("Button clicked, waiting for download to start...")

                    download = await download_info.value
                    logger.info(f"✅ Download started: {download.suggested_filename}")

                    # Save the file
                    await download.save_as(str(download_path))
                    logger.info(f"✅ Downloaded with Playwright: {filename}")

                    result_path = download_path

                except (asyncio.TimeoutError, Exception) as timeout_err:
                    if 'Timeout' not in str(timeout_err):
                        raise  # Re-raise if it's not a timeout error

                    # Download didn't start - maybe there's a redirect or intermediate page
                    logger.warning("Download event timeout - checking if page changed...")
                    await asyncio.sleep(5)  # Wait more for any JS to execute

                    current_url = page.url
                    logger.info(f"Current URL after click: {current_url}")

                    # Look for download links that might have appeared after the click
                    logger.info("Looking for download links on the page...")
                    all_links = await page.query_selector_all('a')

                    direct_link = None
                    for link in all_links:
                        try:
                            href = await link.get_attribute('href')
                            text = await link.inner_text() if await link.is_visible() else None

                            if href and (
                                'cdn' in href.lower() or
                                'files' in href.lower() or
                                'file/' in href.lower() or
                                href.endswith('.epub') or
                                (text and 'download' in text.lower() and 'Download now' not in text)
                            ):
                                logger.info(f"Found potential direct link: text='{text}', href={href[:80]}")
                                direct_link = href
                                break
                        except:
                            continue

                    if direct_link:
                        logger.info(f"Trying to download from: {direct_link}")

                        # Navigate to the download link and wait for actual download
                        try:
                            logger.info("Navigating to download link with Playwright...")
                            await page.goto(direct_link, wait_until='domcontentloaded', timeout=30000)
                            await asyncio.sleep(2)

                            # Try to trigger download from this page
                            logger.info("Waiting for download to start from new page...")
                            async with page.expect_download(timeout=45000) as dl_info:
                                # Sometimes download starts automatically, sometimes need to click
                                # Try to find and click a download button if present
                                try:
                                    final_download_btn = await page.query_selector('button:has-text("Download"), a:has-text("Download"), button.download, a.download')
                                    if final_download_btn and await final_download_btn.is_visible():
                                        logger.info("Found final download button, clicking...")
                                        await final_download_btn.click()
                                    else:
                                        logger.info("No button found, waiting for automatic download...")
                                except:
                                    logger.info("Waiting for automatic download...")
                                    pass

                            download = await dl_info.value
                            logger.info(f"✅ Download started: {download.suggested_filename}")

                            # Save the file
                            await download.save_as(str(download_path))
                            logger.info(f"✅ Downloaded with Playwright: {filename}")
                            result_path = download_path

                        except Exception as download_err:
                            logger.error(f"Failed to download from intermediate link: {download_err}")
                            raise
                    else:
                        # No direct link found - log all links for debugging
                        logger.error("No direct download link found. Logging all links:")
                        for i, link in enumerate(all_links[:15]):
                            try:
                                href = await link.get_attribute('href')
                                text = await link.inner_text() if await link.is_visible() else None
                                logger.error(f"Link {i+1}: text='{text[:30] if text else 'hidden'}', href={href[:60] if href else 'no href'}")
                            except:
                                pass
                        raise Exception("Download button clicked but no download link found on page")

            except Exception as e:
                logger.error(f"Playwright download failed: {e}")
                await page.close()
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
