"""
Comic Pydantic Schemas
Integration with ComicVine and web scrapers
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ============================================================================
# Volume and Search Schemas
# ============================================================================

class VolumeInfo(BaseModel):
    """Information about a specific volume detected in scrapers"""
    number: int
    title: str
    source: str
    issues: int
    cover: Optional[str] = None
    url: Optional[str] = None


class ComicSearchResult(BaseModel):
    """Schema for ComicVine search result"""
    comicvine_id: int
    title: str
    description: Optional[str] = None
    cover_image: Optional[str] = None
    publisher: Optional[str] = None
    start_year: Optional[int] = None
    count_of_issues: Optional[int] = None
    comicvine_url: Optional[str] = None
    in_library: bool = False
    library_id: Optional[int] = None
    # Availability info from scrapers
    has_sources: bool = False
    available_sources: List[str] = []
    relevance_score: int = 0  # Higher = more relevant (original series > translations)
    volumes: List[VolumeInfo] = []  # Detected volumes from scrapers


class ComicSearchResponse(BaseModel):
    """Response for comic search with pagination"""
    results: List[ComicSearchResult]
    total: int
    page: int
    per_page: int


# ============================================================================
# Comic Creation and Update Schemas
# ============================================================================

class VolumeToAdd(BaseModel):
    """Volume information when adding a specific volume"""
    number: int
    title: str
    source: str
    issues: int
    url: str


class ComicCreate(BaseModel):
    """Schema for creating comic from ComicVine"""
    comicvine_id: int
    volume_to_add: Optional[VolumeToAdd] = None  # If adding a specific volume


class ComicUpdate(BaseModel):
    """Schema for updating comic settings"""
    monitored: Optional[bool] = None
    auto_download: Optional[bool] = None
    preferred_source: Optional[str] = None


# ============================================================================
# Comic Response Schemas
# ============================================================================

class ComicResponse(BaseModel):
    """Basic comic response"""
    id: int
    title: str
    slug: Optional[str] = None
    comicvine_id: Optional[int] = None
    description: Optional[str] = None
    cover_image: Optional[str] = None
    publisher: Optional[str] = None
    start_year: Optional[int] = None
    count_of_issues: Optional[int] = None
    writers: Optional[List[str]] = None
    artists: Optional[List[str]] = None
    comicvine_url: Optional[str] = None
    monitored: bool = True
    reading_status: str = 'not_started'
    total_issues: int = 0
    downloaded_issues: int = 0

    class Config:
        from_attributes = True


class IssueResponse(BaseModel):
    """Schema for comic issue response"""
    id: int
    comic_id: int
    issue_number: Optional[str] = None
    title: Optional[str] = None
    cover_image: Optional[str] = None
    release_date: Optional[str] = None
    status: str = "pending"
    file_path: Optional[str] = None
    converted_path: Optional[str] = None  # Path(s) to converted EPUB, separated by '|' if multiple parts
    converted_at: Optional[str] = None
    download_url: Optional[str] = None
    backup_url: Optional[str] = None
    source: Optional[str] = None
    link_status: str = "resolved"
    sent_at: Optional[str] = None
    read_at: Optional[str] = None
    file_size: Optional[int] = None

    class Config:
        from_attributes = True


class ComicDetailResponse(ComicResponse):
    """Detailed comic response with issues"""
    aliases: Optional[List[str]] = None
    characters: Optional[List[str]] = None
    colorists: Optional[List[str]] = None
    source_urls: Optional[dict] = None
    issues: List[dict] = []


# ============================================================================
# Statistics Schemas
# ============================================================================

class ComicStats(BaseModel):
    """Overall comic library statistics"""
    total_comics: int
    monitored_comics: int
    total_issues: int
    downloaded_issues: int


class ComicIssueStats(BaseModel):
    """Download statistics for a specific comic"""
    total_issues: int
    downloaded: int
    downloading: int
    pending: int
    failed: int
    sent_to_kindle: int


# ============================================================================
# Download Schemas
# ============================================================================

class IssueDownloadRequest(BaseModel):
    """Schema for downloading comic issues"""
    issue_ids: List[int] = Field(..., min_length=1, description="List of issue IDs to download")
