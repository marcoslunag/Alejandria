"""
Download Queue Model
Manages download queue for chapters
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from datetime import datetime
from app.database import Base


class DownloadQueue(Base):
    """Download queue model for managing chapter downloads (manga and books)"""

    __tablename__ = "download_queue"

    id = Column(Integer, primary_key=True, index=True)

    # Support both manga chapters and book chapters
    chapter_id = Column(Integer, ForeignKey("chapters.id"), nullable=True, index=True)  # Manga chapters
    book_chapter_id = Column(Integer, ForeignKey("book_chapters.id"), nullable=True, index=True)  # Book chapters

    # Content type: 'manga' or 'book'
    content_type = Column(String(20), default="manga", index=True)

    # Status: queued, downloading, completed, failed
    status = Column(String(50), default="queued", index=True)

    # Progress tracking
    progress = Column(Integer, default=0)  # 0-100
    bytes_downloaded = Column(Integer, default=0)
    total_bytes = Column(Integer, default=0)

    # Error handling
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    # Priority (higher = more priority)
    priority = Column(Integer, default=0)

    def __repr__(self):
        return f"<DownloadQueue(id={self.id}, chapter_id={self.chapter_id}, status='{self.status}', progress={self.progress}%)>"

    @property
    def can_retry(self):
        """Check if download can be retried"""
        return self.status == "failed" and self.retry_count < self.max_retries

    @property
    def is_active(self):
        """Check if download is currently active"""
        return self.status in ["queued", "downloading"]
