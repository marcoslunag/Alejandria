"""
Google Books API Integration Service
Fetches book metadata from Google Books API
https://developers.google.com/books
"""

import aiohttp
import asyncio
import logging
import os
from typing import List, Dict, Optional
from urllib.parse import quote

logger = logging.getLogger(__name__)


class GoogleBooksService:
    """
    Service for interacting with Google Books API
    Provides rich book metadata (covers, descriptions, authors, ISBNs)
    """

    API_URL = "https://www.googleapis.com/books/v1"

    def __init__(self, api_key: str = None):
        """
        Initialize Google Books service

        Args:
            api_key: Optional API key for higher rate limits
        """
        self.api_key = api_key or os.getenv("GOOGLE_BOOKS_API_KEY", "")
        if not self.api_key:
            logger.warning("Google Books API key not configured. Rate limits may apply.")

    async def search_books(
        self,
        query: str,
        page: int = 1,
        per_page: int = 20,
        language: str = None
    ) -> Dict:
        """
        Search for books on Google Books

        Args:
            query: Search term
            page: Page number (1-indexed)
            per_page: Results per page (max 40)
            language: Language filter (e.g., 'es', 'en')

        Returns:
            Dict with search results and pagination info
        """
        try:
            start_index = (page - 1) * per_page

            params = {
                'q': query,
                'startIndex': start_index,
                'maxResults': min(per_page, 40),
                'printType': 'books',
            }

            if language:
                params['langRestrict'] = language

            if self.api_key:
                params['key'] = self.api_key

            result = await self._make_request('/volumes', params)

            if not result:
                return {'results': [], 'total': 0}

            items = result.get('items', [])
            results = [self._transform_volume(item) for item in items]

            return {
                'results': results,
                'total': result.get('totalItems', 0),
                'page': page,
                'per_page': per_page
            }

        except Exception as e:
            logger.error(f"Error searching Google Books: {e}")
            return {'results': [], 'total': 0}

    async def get_book_by_id(self, volume_id: str) -> Optional[Dict]:
        """
        Get detailed book information by Google Books volume ID

        Args:
            volume_id: Google Books volume ID

        Returns:
            Detailed book information
        """
        try:
            params = {}
            if self.api_key:
                params['key'] = self.api_key

            result = await self._make_request(f'/volumes/{volume_id}', params)

            if not result:
                logger.error(f"Book {volume_id} not found on Google Books")
                return None

            return self._transform_volume(result, detailed=True)

        except Exception as e:
            logger.error(f"Error fetching book {volume_id}: {e}")
            return None

    async def get_book_by_isbn(self, isbn: str) -> Optional[Dict]:
        """
        Get book information by ISBN

        Args:
            isbn: ISBN-10 or ISBN-13

        Returns:
            Book information
        """
        try:
            params = {
                'q': f'isbn:{isbn}',
            }

            if self.api_key:
                params['key'] = self.api_key

            result = await self._make_request('/volumes', params)

            if not result or not result.get('items'):
                return None

            # Return first match
            return self._transform_volume(result['items'][0], detailed=True)

        except Exception as e:
            logger.error(f"Error fetching book by ISBN {isbn}: {e}")
            return None

    async def _make_request(self, endpoint: str, params: dict) -> Optional[Dict]:
        """Make API request to Google Books"""
        try:
            url = f"{self.API_URL}{endpoint}"

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    if response.status != 200:
                        logger.error(f"Google Books API error: HTTP {response.status}")
                        return None

                    return await response.json()

        except asyncio.TimeoutError:
            logger.error("Google Books API timeout")
            return None
        except Exception as e:
            logger.error(f"Google Books request error: {e}")
            return None

    def _transform_volume(self, volume: Dict, detailed: bool = False) -> Dict:
        """Transform Google Books volume to our format"""
        if not volume:
            return {}

        volume_info = volume.get('volumeInfo', {})

        # Extract ISBNs
        isbn_10 = None
        isbn_13 = None
        for identifier in volume_info.get('industryIdentifiers', []):
            if identifier.get('type') == 'ISBN_10':
                isbn_10 = identifier.get('identifier')
            elif identifier.get('type') == 'ISBN_13':
                isbn_13 = identifier.get('identifier')

        # Get best cover image
        image_links = volume_info.get('imageLinks', {})
        cover_image = (
            image_links.get('extraLarge') or
            image_links.get('large') or
            image_links.get('medium') or
            image_links.get('thumbnail')
        )

        # Replace http with https for images
        if cover_image:
            cover_image = cover_image.replace('http://', 'https://')

        result = {
            'google_books_id': volume.get('id'),
            'title': volume_info.get('title', 'Unknown'),
            'subtitle': volume_info.get('subtitle'),
            'authors': volume_info.get('authors', []),
            'publisher': volume_info.get('publisher'),
            'published_date': volume_info.get('publishedDate'),
            'description': volume_info.get('description'),
            'isbn_10': isbn_10,
            'isbn_13': isbn_13,
            'page_count': volume_info.get('pageCount'),
            'categories': volume_info.get('categories', []),
            'average_rating': volume_info.get('averageRating'),
            'ratings_count': volume_info.get('ratingsCount'),
            'language': volume_info.get('language'),
            'cover_image': cover_image,
            'thumbnail': image_links.get('thumbnail', '').replace('http://', 'https://'),
            'preview_link': volume_info.get('previewLink'),
            'info_link': volume_info.get('infoLink'),
            'google_books_url': volume_info.get('canonicalVolumeLink'),
        }

        return result


# Singleton instance
_google_books_service = None

def get_google_books_service() -> GoogleBooksService:
    """Get Google Books service singleton"""
    global _google_books_service
    if _google_books_service is None:
        _google_books_service = GoogleBooksService()
    return _google_books_service
