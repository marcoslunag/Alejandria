"""
Comic Model
Represents a comic series (American comics) being monitored
Integrated with ComicVine API for metadata
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Float, JSON, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class Comic(Base):
    """Comic model for storing comic series information with ComicVine metadata"""

    __tablename__ = "comics"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Basic info
    title = Column(String(500), nullable=False, index=True)
    slug = Column(String(255), unique=True, index=True)

    # ComicVine integration (metadata source)
    comicvine_id = Column(Integer, unique=True, index=True)  # ComicVine volume ID
    
    # Titles
    title_original = Column(String(500))  # Original title
    aliases = Column(JSON)  # Alternative names

    # Rich metadata from ComicVine
    description = Column(Text)
    cover_image = Column(String(500))  # Main cover
    
    # Comic info
    publisher = Column(String(200))  # Marvel, DC, Image, etc.
    start_year = Column(Integer)  # Year started
    count_of_issues = Column(Integer)  # Total issues in volume
    
    # Categories and ratings
    genres = Column(JSON)  # Array of genres
    characters = Column(JSON)  # Main characters
    
    # Creators
    writers = Column(JSON)  # Array of writer names
    artists = Column(JSON)  # Array of artist names
    colorists = Column(JSON)  # Array of colorist names

    # External links
    comicvine_url = Column(String(500))
    
    # Download sources (multiple scrapers)
    source_urls = Column(JSON)  # Dict of {scraper_name: url}
    preferred_source = Column(String(50))  # Preferred scraper

    # Reading progress (Feature 3)
    reading_status = Column(String(20), default='not_started')  # not_started/reading/completed
    last_read_issue = Column(String(20), nullable=True)  # Issue number of last read issue

    # System fields
    monitored = Column(Boolean, default=True, index=True)
    auto_download = Column(Boolean, default=True)
    sources_searched = Column(Boolean, default=False)  # True after scrapers have been searched
    comicvine_search_attempted = Column(Boolean, default=False)  # True after ComicVine search attempted
    last_check = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    issues = relationship(
        "ComicIssue",
        back_populates="comic",
        cascade="all, delete-orphan",
        lazy="dynamic"
    )

    def __repr__(self):
        return f"<Comic(id={self.id}, title='{self.title}', publisher='{self.publisher}')>"

    @property
    def total_issues(self):
        """Get total number of issues in library"""
        return self.issues.count()

    @property
    def downloaded_issues(self):
        """Get number of downloaded issues"""
        return self.issues.filter_by(status="downloaded").count()


class ComicIssue(Base):
    """Comic Issue model - represents a single issue of a comic series"""

    __tablename__ = "comic_issues"

    id = Column(Integer, primary_key=True, index=True)
    comic_id = Column(Integer, ForeignKey("comics.id", ondelete="CASCADE"), nullable=False, index=True)

    # Issue info
    issue_number = Column(String(20))  # "1", "1.5", "Annual 1", etc.
    title = Column(String(500))  # Issue title if any
    
    # ComicVine metadata
    comicvine_id = Column(Integer, index=True)  # ComicVine issue ID
    cover_image = Column(String(500))
    description = Column(Text)
    release_date = Column(String(50))  # YYYY-MM-DD
    
    # Creators for this specific issue
    writers = Column(JSON)
    artists = Column(JSON)
    colorists = Column(JSON)
    
    # Download info
    download_url = Column(String(1000))  # Direct download URL
    backup_url = Column(String(1000))  # Backup download URL
    source = Column(String(50))  # Which scraper found it
    link_status = Column(String(20), default="resolved")  # resolved, shortener, needs_captcha, failed
    file_path = Column(String(1000))  # Local file path after download
    file_size = Column(Integer)  # Size in bytes

    # Conversion info (KCC)
    converted_path = Column(String(2000))  # Path(s) to converted file(s), separated by '|' if multiple parts
    converted_at = Column(DateTime)  # When conversion completed

    # Bundle/Collection info (for TPB, HC, Complete collections)
    bundle_id = Column(String(64), index=True)  # Unique ID for bundle (hash of download URL)
    bundle_title = Column(String(255))  # Title of bundle (e.g., "Paper Girls Vol. 6 (TPB)")
    bundle_range = Column(String(50))  # Issue range covered (e.g., "#26-30")
    is_bundle_master = Column(Boolean, default=False)  # True if this issue downloads for the whole bundle

    # Status
    status = Column(String(50), default="pending", index=True)
    # pending, downloading, downloaded, converting, converted, sent, error

    error_message = Column(Text)
    download_attempts = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    downloaded_at = Column(DateTime)
    sent_at = Column(DateTime)  # When sent to Kindle
    read_at = Column(DateTime, nullable=True)  # Feature 3: reading progress

    # Relationship
    comic = relationship("Comic", back_populates="issues")

    def __repr__(self):
        return f"<ComicIssue(id={self.id}, comic_id={self.comic_id}, issue='{self.issue_number}')>"
