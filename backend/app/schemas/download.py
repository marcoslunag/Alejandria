"""
Download Queue Pydantic Schemas
For request/response validation
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class DownloadQueueBase(BaseModel):
    """Base download queue schema"""

    chapter_id: int
    priority: int = Field(0, ge=0, le=10)


class DownloadQueueResponse(BaseModel):
    """Schema for download queue response"""

    id: int
    chapter_id: int
    status: str
    progress: int
    bytes_downloaded: int
    total_bytes: int
    error_message: Optional[str]
    retry_count: int
    max_retries: int
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    priority: int

    class Config:
        from_attributes = True


class DownloadQueueDetailResponse(BaseModel):
    """Schema for download queue response with manga/chapter info"""

    id: int
    chapter_id: int
    status: str
    progress: int
    bytes_downloaded: int
    total_bytes: int
    error_message: Optional[str]
    retry_count: int
    max_retries: int
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    priority: int
    # Additional info
    manga_id: Optional[int] = None
    manga_title: Optional[str] = None
    manga_cover: Optional[str] = None
    chapter_number: Optional[float] = None
    chapter_title: Optional[str] = None
    download_url: Optional[str] = None

    class Config:
        from_attributes = True


class SystemStatusResponse(BaseModel):
    """Schema for system status response"""

    status: str
    version: str
    total_manga: int
    monitored_manga: int
    total_chapters: int
    downloaded_chapters: int
    queue_size: int
    active_downloads: int
