"""
Book Pydantic Schemas
Integration with Google Books and Open Library
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ============================================================================
# Google Books Search Schemas
# ============================================================================

class GoogleBooksSearch(BaseModel):
    """Schema for book search result (from any source)"""

    # Core fields (always present)
    title: str
    source: str = Field(default="google_books", description="Source: google_books, openlibrary, lectulandia, etc.")

    # Optional fields (may not be present for all sources)
    google_books_id: Optional[str] = None
    openlibrary_id: Optional[str] = None
    subtitle: Optional[str] = None
    authors: List[str] = []
    publisher: Optional[str] = None
    published_date: Optional[str] = None
    description: Optional[str] = None
    isbn_10: Optional[str] = None
    isbn_13: Optional[str] = None
    page_count: Optional[int] = None
    categories: List[str] = []
    average_rating: Optional[float] = None
    ratings_count: Optional[int] = None
    language: Optional[str] = None
    cover_image: Optional[str] = None
    thumbnail: Optional[str] = None
    google_books_url: Optional[str] = None

    # For scraper results
    source_url: Optional[str] = Field(None, description="URL from scraper (lectulandia, epubera, etc.)")

    # Library status
    in_library: bool = False
    library_id: Optional[int] = None


class BookSearchResponse(BaseModel):
    """Response for book search with pagination"""

    results: List[GoogleBooksSearch]
    total: int
    page: int
    per_page: int


# ============================================================================
# Book Creation and Update Schemas
# ============================================================================

class BookCreateFromGoogleBooks(BaseModel):
    """Schema for creating book from Google Books"""

    google_books_id: str = Field(..., description="Google Books volume ID")
    monitored: bool = Field(True, description="Monitor for updates")
    auto_download: bool = Field(True, description="Auto-download when available")


class BookCreateFromURL(BaseModel):
    """Schema for creating book from scraper URL"""

    source_url: str = Field(..., min_length=1, description="URL from EPUB scraper site")
    scraper_name: Optional[str] = Field(None, description="Scraper to use (epubera, lectulandia)")
    google_books_id: Optional[str] = Field(None, description="Optional: Link to Google Books for metadata")
    monitored: bool = Field(True, description="Monitor for updates")
    auto_download: bool = Field(True, description="Auto-download when available")


class BookUpdate(BaseModel):
    """Schema for updating book settings"""

    title: Optional[str] = Field(None, min_length=1, max_length=500)
    monitored: Optional[bool] = None
    auto_download: Optional[bool] = None
    description: Optional[str] = None
    preferred_source: Optional[str] = None


# ============================================================================
# Book Response Schemas
# ============================================================================

class BookChapterResponse(BaseModel):
    """Schema for book chapter (file) response"""

    id: int
    book_id: int
    number: int
    title: Optional[str] = None
    download_url: Optional[str] = None
    source: Optional[str] = None
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    downloaded_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BookResponse(BaseModel):
    """Schema for book response"""

    id: int
    title: str
    slug: str
    google_books_id: Optional[str] = None
    openlibrary_id: Optional[str] = None
    isbn_10: Optional[str] = None
    isbn_13: Optional[str] = None
    subtitle: Optional[str] = None
    description: Optional[str] = None
    cover_image: Optional[str] = None
    thumbnail: Optional[str] = None
    authors: List[str] = []
    publisher: Optional[str] = None
    published_date: Optional[str] = None
    language: Optional[str] = None
    page_count: Optional[int] = None
    categories: List[str] = []
    average_rating: Optional[float] = None
    ratings_count: Optional[int] = None
    source_urls: Optional[dict] = None
    preferred_source: Optional[str] = None
    monitored: bool
    auto_download: bool
    created_at: datetime
    updated_at: datetime

    # Computed fields
    total_chapters: Optional[int] = None
    downloaded_chapters: Optional[int] = None

    class Config:
        from_attributes = True


class BookDetailResponse(BookResponse):
    """Schema for detailed book response with chapters"""

    chapters: List[BookChapterResponse] = []


# ============================================================================
# Library Stats Schema
# ============================================================================

class BookLibraryStats(BaseModel):
    """Schema for book library statistics"""

    total_books: int = 0
    monitored_books: int = 0
    total_files: int = 0
    downloaded_files: int = 0
    sent_files: int = 0


# ============================================================================
# Chapter Download Schema
# ============================================================================

class ChapterDownloadRequest(BaseModel):
    """Schema for downloading chapters"""

    chapter_ids: List[int] = Field(..., min_items=1, description="List of chapter IDs to download")
