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
]
