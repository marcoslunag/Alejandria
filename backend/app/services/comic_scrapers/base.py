"""
Base Comic Scraper
Abstract base class for all comic scrapers
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class HostType(Enum):
    """Supported download hosts"""
    MEGA = "mega"
    MEDIAFIRE = "mediafire"
    GOOGLE_DRIVE = "gdrive"
    TERABOX = "terabox"
    DIRECT = "direct"
    UNKNOWN = "unknown"


@dataclass
class DownloadLink:
    """Represents a download link"""
    url: str
    host: HostType
    quality_score: int = 50  # 0-100, higher is better
    file_size: Optional[str] = None  # e.g., "150 MB"
    password: Optional[str] = None
    
    def __lt__(self, other):
        return self.quality_score < other.quality_score


@dataclass
class ScraperResult:
    """Result from scraping a comic"""
    title: str
    source: str  # Scraper name
    source_url: str  # Original page URL
    
    # Comic info
    issues: Optional[str] = None  # e.g., "1-13"
    language: str = "es"
    format: str = "cbr"
    
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
        HostType.MEGA: 90,
        HostType.MEDIAFIRE: 85,
        HostType.GOOGLE_DRIVE: 80,
        HostType.TERABOX: 60,
        HostType.DIRECT: 70,
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
    async def get_download_links(self, url: str) -> ScraperResult:
        """
        Get download links from a comic page
        
        Args:
            url: URL of the comic page
            
        Returns:
            ScraperResult with download links
        """
        pass
    
    def detect_host(self, url: str) -> HostType:
        """Detect the hosting service from URL"""
        url_lower = url.lower()
        
        if 'mega.nz' in url_lower or 'mega.co.nz' in url_lower:
            return HostType.MEGA
        elif 'mediafire.com' in url_lower:
            return HostType.MEDIAFIRE
        elif 'drive.google.com' in url_lower:
            return HostType.GOOGLE_DRIVE
        elif 'terabox' in url_lower or '1024tera' in url_lower:
            return HostType.TERABOX
        elif url_lower.endswith(('.cbr', '.cbz', '.zip', '.rar')):
            return HostType.DIRECT
        else:
            return HostType.UNKNOWN
    
    def get_quality_score(self, host: HostType) -> int:
        """Get quality score for a host"""
        return self.HOST_QUALITY.get(host, 30)
    
    def create_download_link(
        self, 
        url: str, 
        file_size: Optional[str] = None,
        password: Optional[str] = None,
        bonus_score: int = 0
    ) -> DownloadLink:
        """Create a DownloadLink with auto-detected host and quality"""
        host = self.detect_host(url)
        quality = self.get_quality_score(host) + bonus_score
        
        return DownloadLink(
            url=url,
            host=host,
            quality_score=min(quality, 100),  # Cap at 100
            file_size=file_size,
            password=password
        )
