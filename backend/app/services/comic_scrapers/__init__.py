"""
Comic Scrapers Package
Scrapers for various comic download sites
"""

from .base import ComicScraperBase, ComicScraperResult, ScraperResult, HostType, DownloadLink
from .megacomics import MegaComicsScraper
from .zonacomics import ZonaComicsScraper
from .cbrcomics import CBRComicsScraper

__all__ = [
    'ComicScraperBase',
    'ComicScraperResult',
    'ScraperResult',
    'HostType',
    'DownloadLink',
    'MegaComicsScraper',
    'ZonaComicsScraper',
    'CBRComicsScraper',
]
