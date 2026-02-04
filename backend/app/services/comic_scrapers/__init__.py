"""
Comic Scrapers Package
Scrapers for various comic download sites
"""

from app.services.comic_scrapers.base import ComicScraperBase, ScraperResult
from app.services.comic_scrapers.megacomics import MegaComicsScraper

__all__ = [
    'ComicScraperBase',
    'ScraperResult', 
    'MegaComicsScraper',
]
