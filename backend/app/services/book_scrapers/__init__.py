"""
Book Scrapers Package
"""

from .base import BookScraperBase, BookScraperResult, DownloadLink, HostType
from .lectulandia import LectulandiaScraper

__all__ = [
    'BookScraperBase',
    'BookScraperResult',
    'DownloadLink',
    'HostType',
    'LectulandiaScraper'
]
