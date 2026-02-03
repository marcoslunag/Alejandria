"""
Chapter Model
Represents individual manga chapters
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Float, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class Chapter(Base):
    """Chapter model for storing manga chapter information"""

    __tablename__ = "chapters"

    id = Column(Integer, primary_key=True, index=True)
    manga_id = Column(Integer, ForeignKey("manga.id"), nullable=False, index=True)
    number = Column(Float, nullable=False)  # Supports 1, 1.5, 2, etc
    title = Column(String(255))
    url = Column(String(500), nullable=False)
    download_url = Column(String(500))  # URL principal de descarga
    backup_url = Column(String(500))    # URL de backup
    download_host = Column(String(50))  # Host principal (mediafire, fireload, etc.)

    # Status: pending, downloading, downloaded, converting, converted, sent, error
    status = Column(String(50), default="pending", index=True)

    # File paths
    file_path = Column(String(500))  # Original CBZ file
    converted_path = Column(String(500))  # Converted EPUB file

    # Timestamps
    downloaded_at = Column(DateTime)
    converted_at = Column(DateTime)
    sent_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Error tracking
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)

    # Relationships
    manga = relationship("Manga", back_populates="chapters")

    def __repr__(self):
        return f"<Chapter(id={self.id}, manga_id={self.manga_id}, number={self.number}, status='{self.status}')>"

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
            return f"Chapter {self.number}: {self.title}"
        return f"Chapter {self.number}"
