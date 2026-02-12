"""
Base Comic Scraper
Abstract base class for all comic scrapers
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from enum import Enum
import logging
import aiohttp
import asyncio

logger = logging.getLogger(__name__)


# Reuse HostType and DownloadLink from book_scrapers
from ..book_scrapers.base import HostType, DownloadLink


@dataclass
class ComicScraperResult:
    """Result from scraping a comic issue"""
    title: str
    source: str  # Scraper name
    source_url: str  # Original page URL

    # Comic info
    issue_number: Optional[str] = None
    volume_name: Optional[str] = None
    language: str = "en"
    format: str = "cbr"  # cbr, cbz, pdf

    # Download links (primary + backups)
    download_links: List[DownloadLink] = field(default_factory=list)

    # Additional metadata
    description: Optional[str] = None
    cover_image: Optional[str] = None
    file_size: Optional[str] = None
    year: Optional[int] = None

    # Status
    success: bool = True
    error: Optional[str] = None

    @property
    def best_link(self) -> Optional[DownloadLink]:
        """Get the best download link based on quality score"""
        if not self.download_links:
            return None
        return max(self.download_links, key=lambda x: x.quality_score)

    @property
    def backup_link(self) -> Optional[DownloadLink]:
        """Get the second best download link as backup"""
        if len(self.download_links) < 2:
            return None
        sorted_links = sorted(self.download_links, key=lambda x: x.quality_score, reverse=True)
        return sorted_links[1]


class ComicScraperBase(ABC):
    """
    Abstract base class for comic scrapers

    Each scraper should implement:
    - search(): Search for comics
    - get_download_links(): Get download links from a comic page
    """

    name: str = "base"
    base_url: str = ""

    # Quality scores for different hosts (0-100)
    HOST_QUALITY = {
        HostType.MEGA: 70,  # Lowered from 95 - rate limit issues (~6h/5GB)
        HostType.GOOGLE_DRIVE: 95,  # Raised from 90 - best option, no severe limits
        HostType.MEDIAFIRE: 90,  # Raised from 85 - good option
        HostType.FIRELOAD: 75,
        HostType.KRAKENFILES: 70,
        HostType.DIRECT: 70,
        HostType.MEGAUP: 65,
        HostType.TERABOX: 60,
        HostType.UPLOADEE: 55,
        HostType.SENDNOW: 50,
        HostType.UNKNOWN: 30,
    }

    def __init__(self):
        self.session = None

    @abstractmethod
    async def search(self, query: str, page: int = 1) -> List[Dict]:
        """
        Search for comics

        Args:
            query: Search term
            page: Page number

        Returns:
            List of search results with title, url, cover, etc.
        """
        pass

    @abstractmethod
    async def get_download_links(self, url: str) -> ComicScraperResult:
        """
        Get download links from a comic page

        Args:
            url: URL of the comic page

        Returns:
            ComicScraperResult with download links
        """
        pass

    def detect_host(self, url: str) -> HostType:
        """Detect the hosting service from URL"""
        url_lower = url.lower()

        if 'mega.nz' in url_lower or 'mega.co' in url_lower:
            return HostType.MEGA
        elif 'mediafire.com' in url_lower:
            return HostType.MEDIAFIRE
        elif 'drive.google.com' in url_lower:
            return HostType.GOOGLE_DRIVE
        elif 'terabox' in url_lower or '1024tera' in url_lower:
            return HostType.TERABOX
        elif 'fireload' in url_lower:
            return HostType.FIRELOAD
        elif 'krakenfiles.com' in url_lower:
            return HostType.KRAKENFILES
        elif 'upload.ee' in url_lower:
            return HostType.UPLOADEE
        elif 'megaup.net' in url_lower:
            return HostType.MEGAUP
        elif 'send.now' in url_lower:
            return HostType.SENDNOW
        elif 'zippyshare' in url_lower:
            return HostType.DIRECT  # Zippyshare acts like direct
        elif url_lower.endswith(('.cbr', '.cbz', '.pdf')):
            return HostType.DIRECT
        else:
            return HostType.UNKNOWN

    def get_quality_score(self, host: HostType) -> int:
        """Get quality score for a host"""
        return self.HOST_QUALITY.get(host, 30)

    async def _get_page(self, url: str, timeout: int = 30) -> Optional[str]:
        """
        Simple HTTP GET request for scraping
        Uses aiohttp for async requests

        Args:
            url: URL to fetch
            timeout: Timeout in seconds

        Returns:
            HTML content or None if failed
        """
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        try:
            timeout_obj = aiohttp.ClientTimeout(total=timeout)
            async with aiohttp.ClientSession(timeout=timeout_obj) as session:
                async with session.get(url, headers=headers, allow_redirects=True) as response:
                    if response.status == 200:
                        return await response.text()
                    else:
                        logger.warning(f"HTTP {response.status} for {url}")
                        return None
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching {url}")
            return None
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

    def create_download_link(
        self,
        url: str,
        file_size: Optional[str] = None,
        bonus_score: int = 0
    ) -> DownloadLink:
        """Create a DownloadLink with auto-detected host and quality"""
        host = self.detect_host(url)
        quality = self.get_quality_score(host) + bonus_score

        return DownloadLink(
            url=url,
            host=host,
            quality_score=min(quality, 100),  # Cap at 100
            file_size=file_size
        )


# Alias for backwards compatibility
ScraperResult = ComicScraperResult
