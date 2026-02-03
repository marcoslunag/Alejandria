"""
Manga Pydantic Schemas
Enhanced with Anilist metadata integration
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ============================================================================
# Anilist Search Schemas
# ============================================================================

class AnilistMangaSearch(BaseModel):
    """Schema for Anilist manga search result"""

    anilist_id: int
    mal_id: Optional[int] = None
    title: str
    title_romaji: Optional[str] = None
    title_english: Optional[str] = None
    title_native: Optional[str] = None
    description: Optional[str] = None
    cover_image: Optional[str] = None
    banner_image: Optional[str] = None
    cover_color: Optional[str] = None
    format: Optional[str] = None  # MANGA, NOVEL, ONE_SHOT
    status: Optional[str] = None  # FINISHED, RELEASING, NOT_YET_RELEASED
    start_date: Optional[str] = None
    chapters: Optional[int] = None
    volumes: Optional[int] = None
    genres: List[str] = []
    average_score: Optional[float] = None
    popularity: Optional[int] = None
    anilist_url: Optional[str] = None
    country: Optional[str] = None


class AnilistSearchResponse(BaseModel):
    """Response for Anilist search with pagination"""

    results: List[AnilistMangaSearch]
    page_info: dict = {}


# ============================================================================
# Manga Creation and Update Schemas
# ============================================================================

class MangaCreateFromAnilist(BaseModel):
    """Schema for creating manga from Anilist (Kaizoku-style)"""

    anilist_id: int = Field(..., description="Anilist manga ID")
    source_url: Optional[str] = Field(None, description="Optional: Direct URL to download source")
    monitored: bool = Field(True, description="Monitor for new chapters")
    auto_download: bool = Field(True, description="Auto-download new chapters")


class MangaCreateFromURL(BaseModel):
    """Schema for creating manga from direct URL (legacy method)"""

    source_url: str = Field(..., min_length=1, description="URL on tomosmanga.com")
    anilist_id: Optional[int] = Field(None, description="Optional: Link to Anilist for metadata")
    monitored: bool = Field(True, description="Monitor for new chapters")
    auto_download: bool = Field(True, description="Auto-download new chapters")


class MangaUpdate(BaseModel):
    """Schema for updating manga settings"""

    title: Optional[str] = Field(None, min_length=1, max_length=500)
    source_url: Optional[str] = None
    monitored: Optional[bool] = None
    auto_download: Optional[bool] = None
    description: Optional[str] = None


# ============================================================================
# Manga Response Schemas
# ============================================================================

class MangaResponse(BaseModel):
    """Basic manga response"""

    id: int
    title: str
    slug: str

    # Source info
    source_url: Optional[str] = None
    source_type: Optional[str] = None

    # Anilist metadata
    anilist_id: Optional[int] = None
    mal_id: Optional[int] = None
    title_romaji: Optional[str] = None
    title_english: Optional[str] = None
    title_native: Optional[str] = None

    # Visual
    cover_image: Optional[str] = None
    banner_image: Optional[str] = None
    cover_color: Optional[str] = None

    # Basic info
    description: Optional[str] = None
    format: Optional[str] = None
    status: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None

    # Stats
    chapters_total: Optional[int] = None
    volumes_total: Optional[int] = None
    average_score: Optional[float] = None
    popularity: Optional[int] = None

    # Categories
    genres: Optional[List[str]] = []
    tags: Optional[List[str]] = []

    # System
    monitored: bool
    auto_download: bool
    last_check: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    # External links
    anilist_url: Optional[str] = None
    country: Optional[str] = None

    class Config:
        from_attributes = True


class MangaDetailResponse(MangaResponse):
    """Detailed manga response with chapter statistics"""

    # Chapter stats
    total_chapters_in_library: int = 0
    downloaded_chapters: int = 0
    pending_chapters: int = 0

    # Authors/Artists
    authors: Optional[List[str]] = []
    artists: Optional[List[str]] = []

    class Config:
        from_attributes = True


class MangaCardResponse(BaseModel):
    """Compact manga response for grid/list display (Kaizoku-style)"""

    id: int
    title: str
    cover_image: Optional[str] = None
    cover_color: Optional[str] = None
    format: Optional[str] = None
    status: Optional[str] = None
    average_score: Optional[float] = None
    genres: List[str] = []
    monitored: bool
    chapters_total: Optional[int] = None
    downloaded_chapters: int = 0
    anilist_id: Optional[int] = None

    class Config:
        from_attributes = True


# ============================================================================
# Search and Discovery Schemas
# ============================================================================

class MangaSearch(BaseModel):
    """Unified search result (can be from Anilist or TomosManga)"""

    # Common fields
    title: str
    description: Optional[str] = None
    cover: Optional[str] = None

    # Source identification
    source: str  # 'anilist' or 'tomosmanga'

    # Anilist fields (if source is anilist)
    anilist_id: Optional[int] = None
    anilist_url: Optional[str] = None
    genres: List[str] = []
    average_score: Optional[float] = None
    status: Optional[str] = None

    # TomosManga fields (if source is tomosmanga)
    tomosmanga_url: Optional[str] = None
    slug: Optional[str] = None

    # Matching status
    in_library: bool = False
    library_id: Optional[int] = None


class SearchResponse(BaseModel):
    """Combined search response"""

    query: str
    results: List[MangaSearch]
    total: int
    sources: List[str]  # Which sources were searched


# ============================================================================
# Statistics and Analytics
# ============================================================================

class MangaStats(BaseModel):
    """Statistics for a manga"""

    manga_id: int
    title: str
    total_chapters: int
    downloaded: int
    downloading: int
    pending: int
    failed: int
    sent_to_kindle: int
    last_download: Optional[datetime] = None
    last_check: Optional[datetime] = None


class LibraryStats(BaseModel):
    """Overall library statistics"""

    total_manga: int
    monitored_manga: int
    total_chapters: int
    downloaded_chapters: int
    pending_downloads: int
    disk_usage_mb: float
    genres_distribution: dict = {}
    status_distribution: dict = {}
