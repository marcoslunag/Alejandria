"""Pydantic Schemas Package"""

from app.schemas.manga import (
    MangaCreateFromAnilist,
    MangaCreateFromURL,
    MangaUpdate,
    MangaResponse,
    MangaDetailResponse,
    MangaCardResponse,
    MangaStats,
    LibraryStats,
    AnilistMangaSearch,
    AnilistSearchResponse,
    MangaSearch,
    SearchResponse
)
from app.schemas.chapter import (
    ChapterBase,
    ChapterCreate,
    ChapterUpdate,
    ChapterResponse
)
from app.schemas.download import (
    DownloadQueueBase,
    DownloadQueueResponse
)
from app.schemas.comic import (
    VolumeInfo,
    ComicSearchResult,
    ComicSearchResponse,
    VolumeToAdd,
    ComicCreate,
    ComicResponse,
    ComicDetailResponse,
    IssueResponse,
    ComicUpdate,
    ComicStats,
    ComicIssueStats,
    IssueDownloadRequest,
)

__all__ = [
    "MangaCreateFromAnilist",
    "MangaCreateFromURL",
    "MangaUpdate",
    "MangaResponse",
    "MangaDetailResponse",
    "MangaCardResponse",
    "MangaStats",
    "LibraryStats",
    "AnilistMangaSearch",
    "AnilistSearchResponse",
    "MangaSearch",
    "SearchResponse",
    "ChapterBase",
    "ChapterCreate",
    "ChapterUpdate",
    "ChapterResponse",
    "DownloadQueueBase",
    "DownloadQueueResponse",
    "VolumeInfo",
    "ComicSearchResult",
    "ComicSearchResponse",
    "VolumeToAdd",
    "ComicCreate",
    "ComicResponse",
    "ComicDetailResponse",
    "IssueResponse",
    "ComicUpdate",
    "ComicStats",
    "ComicIssueStats",
    "IssueDownloadRequest",
]
