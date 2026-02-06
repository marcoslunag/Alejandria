"""
Open Library API Integration Service
Fetches book metadata from Open Library API
https://openlibrary.org/developers/api
"""

import aiohttp
import asyncio
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class OpenLibraryService:
    """
    Service for interacting with Open Library API
    Free, no API key required
    """

    API_URL = "https://openlibrary.org"
    COVERS_URL = "https://covers.openlibrary.org"

    async def search_books(
        self,
        query: str,
        page: int = 1,
        per_page: int = 20
    ) -> Dict:
        """
        Search for books on Open Library

        Args:
            query: Search term
            page: Page number (1-indexed)
            per_page: Results per page

        Returns:
            Dict with search results and pagination info
        """
        try:
            offset = (page - 1) * per_page

            params = {
                'q': query,
                'offset': offset,
                'limit': per_page,
                'fields': 'key,title,author_name,first_publish_year,isbn,publisher,subject,cover_i,language,number_of_pages_median',
            }

            result = await self._make_request('/search.json', params)

            if not result:
                return {'results': [], 'total': 0}

            docs = result.get('docs', [])
            results = [self._transform_work(doc) for doc in docs]

            return {
                'results': results,
                'total': result.get('numFound', 0),
                'page': page,
                'per_page': per_page
            }

        except Exception as e:
            logger.error(f"Error searching Open Library: {e}")
            return {'results': [], 'total': 0}

    async def get_book_by_isbn(self, isbn: str) -> Optional[Dict]:
        """
        Get book information by ISBN

        Args:
            isbn: ISBN-10 or ISBN-13

        Returns:
            Book information
        """
        try:
            result = await self._make_request(f'/isbn/{isbn}.json')

            if not result:
                return None

            # Get work details for more complete info
            work_key = result.get('works', [{}])[0].get('key')
            if work_key:
                work_result = await self._make_request(f'{work_key}.json')
                if work_result:
                    result['work'] = work_result

            return self._transform_edition(result)

        except Exception as e:
            logger.error(f"Error fetching book by ISBN {isbn}: {e}")
            return None

    async def get_work(self, work_id: str) -> Optional[Dict]:
        """
        Get work details by Open Library work ID

        Args:
            work_id: Open Library work ID (e.g., OL45804W)

        Returns:
            Work information
        """
        try:
            # Remove /works/ prefix if present
            if work_id.startswith('/works/'):
                work_id = work_id.replace('/works/', '')

            result = await self._make_request(f'/works/{work_id}.json')

            if not result:
                return None

            return self._transform_work(result, detailed=True)

        except Exception as e:
            logger.error(f"Error fetching work {work_id}: {e}")
            return None

    async def _make_request(self, endpoint: str, params: dict = None) -> Optional[Dict]:
        """Make API request to Open Library"""
        try:
            url = f"{self.API_URL}{endpoint}"

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    if response.status != 200:
                        logger.error(f"Open Library API error: HTTP {response.status}")
                        return None

                    return await response.json()

        except asyncio.TimeoutError:
            logger.error("Open Library API timeout")
            return None
        except Exception as e:
            logger.error(f"Open Library request error: {e}")
            return None

    def _transform_work(self, work: Dict, detailed: bool = False) -> Dict:
        """Transform Open Library work to our format"""
        if not work:
            return {}

        # Get cover image
        cover_id = work.get('cover_i') or work.get('covers', [None])[0]
        cover_image = None
        thumbnail = None
        if cover_id:
            cover_image = f"{self.COVERS_URL}/b/id/{cover_id}-L.jpg"
            thumbnail = f"{self.COVERS_URL}/b/id/{cover_id}-M.jpg"

        # Extract work ID
        openlibrary_id = work.get('key', '').replace('/works/', '')

        result = {
            'openlibrary_id': openlibrary_id,
            'title': work.get('title', 'Unknown'),
            'subtitle': work.get('subtitle'),
            'authors': work.get('author_name', []),
            'first_publish_year': work.get('first_publish_year'),
            'description': self._extract_description(work.get('description')),
            'subjects': work.get('subject', [])[:10] if work.get('subject') else [],
            'cover_image': cover_image,
            'thumbnail': thumbnail,
            'openlibrary_url': f"{self.API_URL}{work.get('key')}" if work.get('key') else None,
            'language': work.get('language', [None])[0] if work.get('language') else None,
            'number_of_pages': work.get('number_of_pages_median'),
        }

        # Add ISBNs if available
        if work.get('isbn'):
            isbns = work.get('isbn', [])
            for isbn in isbns:
                if len(isbn) == 10:
                    result['isbn_10'] = isbn
                    break
            for isbn in isbns:
                if len(isbn) == 13:
                    result['isbn_13'] = isbn
                    break

        return result

    def _transform_edition(self, edition: Dict) -> Dict:
        """Transform Open Library edition to our format"""
        if not edition:
            return {}

        # Get cover image
        cover_id = edition.get('covers', [None])[0]
        cover_image = None
        thumbnail = None
        if cover_id:
            cover_image = f"{self.COVERS_URL}/b/id/{cover_id}-L.jpg"
            thumbnail = f"{self.COVERS_URL}/b/id/{cover_id}-M.jpg"

        # Extract ISBNs
        isbn_10 = edition.get('isbn_10', [None])[0]
        isbn_13 = edition.get('isbn_13', [None])[0]

        # Get work info if available
        work = edition.get('work', {})

        result = {
            'title': edition.get('title', 'Unknown'),
            'subtitle': edition.get('subtitle'),
            'authors': [author.get('name') if isinstance(author, dict) else str(author)
                       for author in edition.get('authors', [])],
            'publishers': edition.get('publishers', []),
            'publish_date': edition.get('publish_date'),
            'isbn_10': isbn_10,
            'isbn_13': isbn_13,
            'number_of_pages': edition.get('number_of_pages'),
            'cover_image': cover_image,
            'thumbnail': thumbnail,
            'description': self._extract_description(work.get('description')) if work else None,
            'subjects': work.get('subjects', [])[:10] if work else [],
            'openlibrary_url': f"{self.API_URL}{edition.get('key')}" if edition.get('key') else None,
        }

        return result

    def _extract_description(self, description) -> Optional[str]:
        """Extract description text from various formats"""
        if not description:
            return None

        if isinstance(description, str):
            return description

        if isinstance(description, dict):
            return description.get('value', '')

        return str(description)


# Singleton instance
_openlibrary_service = None

def get_openlibrary_service() -> OpenLibraryService:
    """Get Open Library service singleton"""
    global _openlibrary_service
    if _openlibrary_service is None:
        _openlibrary_service = OpenLibraryService()
    return _openlibrary_service
