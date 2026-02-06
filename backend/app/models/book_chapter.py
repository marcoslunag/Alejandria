"""
BookChapter Model
Represents individual book files (EPUBs)
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class BookChapter(Base):
    """BookChapter model - represents a single EPUB file"""

    __tablename__ = "book_chapters"

    id = Column(Integer, primary_key=True, index=True)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True)

    # Chapter info (for multi-volume books)
    number = Column(Integer, default=1)  # Volume number
    title = Column(String(500))  # Chapter/volume title if any

    # Download info
    download_url = Column(String(1000))  # Direct download URL
    backup_url = Column(String(1000))  # Backup download URL
    source = Column(String(50))  # Which scraper found it
    file_path = Column(String(1000))  # Local EPUB file path
    converted_path = Column(String(1000))  # Converted MOBI file path
    file_size = Column(Integer)  # Size in bytes

    # Status: pending, downloading, downloaded, converting, converted, sent, error
    status = Column(String(50), default="pending", index=True)

    error_message = Column(Text)
    download_attempts = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    downloaded_at = Column(DateTime)
    converted_at = Column(DateTime)
    sent_at = Column(DateTime)

    # Relationship
    book = relationship("Book", back_populates="chapters")

    def __repr__(self):
        return f"<BookChapter(id={self.id}, book_id={self.book_id}, status='{self.status}')>"

    @property
    def is_downloaded(self):
        """Check if chapter is downloaded"""
        return self.status in ["downloaded", "converting", "converted", "sent"]

    @property
    def is_sent(self):
        """Check if chapter has been sent to Kindle"""
        return self.status == "sent"

    @property
    def display_name(self):
        """Get display name for chapter"""
        if self.title:
            return f"Volume {self.number}: {self.title}"
        return f"Volume {self.number}"
