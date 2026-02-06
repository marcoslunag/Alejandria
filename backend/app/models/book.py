"""
Book Model
Represents a book or book series being monitored
Integrated with Google Books/Open Library for metadata
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Float, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class Book(Base):
    """Book model for storing book information with metadata"""

    __tablename__ = "books"

    id = Column(Integer, primary_key=True, index=True)

    # Basic info
    title = Column(String(500), nullable=False, index=True)
    slug = Column(String(255), unique=True, index=True)

    # Metadata source integration
    google_books_id = Column(String(100), unique=True, index=True)  # Google Books volume ID
    openlibrary_id = Column(String(100), index=True)  # Open Library work ID
    isbn_10 = Column(String(20))  # ISBN-10
    isbn_13 = Column(String(20), index=True)  # ISBN-13

    # Titles (multiple languages)
    title_original = Column(String(500))
    subtitle = Column(String(500))

    # Rich metadata
    description = Column(Text)
    cover_image = Column(String(500))  # Cover URL
    thumbnail = Column(String(500))  # Thumbnail URL

    # Book info
    authors = Column(JSON)  # Array of author names
    publisher = Column(String(200))
    published_date = Column(String(50))  # YYYY-MM-DD
    language = Column(String(10))  # en, es, etc.
    page_count = Column(Integer)

    # Categories and ratings
    categories = Column(JSON)  # Array of categories/genres
    average_rating = Column(Float)  # 0-5 rating
    ratings_count = Column(Integer)

    # External links
    google_books_url = Column(String(500))
    openlibrary_url = Column(String(500))
    preview_link = Column(String(500))
    info_link = Column(String(500))

    # Download sources (multiple scrapers)
    source_urls = Column(JSON)  # Dict of {scraper_name: url}
    preferred_source = Column(String(50))  # Preferred scraper

    # System fields
    monitored = Column(Boolean, default=True, index=True)
    auto_download = Column(Boolean, default=True)
    last_check = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    chapters = relationship(
        "BookChapter",
        back_populates="book",
        cascade="all, delete-orphan",
        lazy="dynamic"
    )

    def __repr__(self):
        return f"<Book(id={self.id}, title='{self.title}', monitored={self.monitored})>"

    @property
    def total_chapters(self):
        """Get total number of chapters (EPUB files)"""
        return self.chapters.count()

    @property
    def downloaded_chapters(self):
        """Get number of downloaded chapters"""
        return self.chapters.filter_by(status="downloaded").count()
