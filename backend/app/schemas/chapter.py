"""
Chapter Pydantic Schemas
For request/response validation
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ChapterBase(BaseModel):
    """Base chapter schema with common fields"""

    number: float = Field(..., ge=0)
    title: Optional[str] = Field(None, max_length=255)
    url: str = Field(..., min_length=1, max_length=500)
    download_url: Optional[str] = Field(None, max_length=500)


class ChapterCreate(ChapterBase):
    """Schema for creating a new chapter"""

    manga_id: int


class ChapterUpdate(BaseModel):
    """Schema for updating chapter"""

    title: Optional[str] = Field(None, max_length=255)
    status: Optional[str] = Field(None, pattern="^(pending|downloading|downloaded|converting|converted|sent|error)$")
    download_url: Optional[str] = None


class ChapterResponse(BaseModel):
    """Schema for chapter response"""

    id: int
    manga_id: int
    number: float
    title: Optional[str]
    url: str
    download_url: Optional[str]
    backup_url: Optional[str] = None
    download_host: Optional[str] = None
    status: str
    file_path: Optional[str]
    converted_path: Optional[str]
    downloaded_at: Optional[datetime]
    converted_at: Optional[datetime]
    sent_at: Optional[datetime]
    created_at: datetime
    retry_count: int
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class ChapterDetailResponse(ChapterResponse):
    """Extended chapter response with manga info"""

    manga_title: Optional[str] = None

    class Config:
        from_attributes = True
