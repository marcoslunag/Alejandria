"""
ComicVine API Integration Service
Fetches comic metadata from ComicVine API
https://comicvine.gamespot.com/api/
"""

import aiohttp
import asyncio
import logging
import os
import re
from typing import List, Dict, Optional
from urllib.parse import quote

logger = logging.getLogger(__name__)


class ComicVineService:
    """
    Service for interacting with ComicVine API
    Provides comic metadata (covers, descriptions, creators, etc.)
    
    API Key required - get one at: https://comicvine.gamespot.com/api/
    Rate limit: 200 requests per resource per hour
    """

    API_URL = "https://comicvine.gamespot.com/api"
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("COMICVINE_API_KEY", "")
        if not self.api_key:
            logger.warning("ComicVine API key not configured. Set COMICVINE_API_KEY env var.")
    
    async def search_volumes(
        self,
        query: str,
        page: int = 1,
        per_page: int = 20
    ) -> Dict:
        """
        Search for comic volumes (series) on ComicVine
        
        Args:
            query: Search term
            page: Page number (1-indexed)
            per_page: Results per page (max 100)
            
        Returns:
            Dict with search results and pagination info
        """
        if not self.api_key:
            return {'results': [], 'total': 0, 'error': 'API key not configured'}
        
        try:
            params = {
                'api_key': self.api_key,
                'format': 'json',
                'resources': 'volume',
                'query': query,
                'limit': min(per_page, 100),
                'offset': (page - 1) * per_page,
                'field_list': 'id,name,deck,description,image,start_year,publisher,count_of_issues,api_detail_url,site_detail_url'
            }
            
            data = await self._make_request('/search/', params)
            
            if not data or data.get('status_code') != 1:
                error = data.get('error', 'Unknown error') if data else 'No response'
                logger.error(f"ComicVine search error: {error}")
                return {'results': [], 'total': 0, 'error': error}
            
            results = [self._transform_volume(vol) for vol in data.get('results', [])]
            
            return {
                'results': results,
                'total': data.get('number_of_total_results', 0),
                'page': page,
                'per_page': per_page
            }
            
        except Exception as e:
            logger.error(f"Error searching ComicVine: {e}")
            return {'results': [], 'total': 0, 'error': str(e)}
    
    async def get_volume(self, volume_id: int) -> Optional[Dict]:
        """
        Get detailed volume information by ComicVine ID
        
        Args:
            volume_id: ComicVine volume ID
            
        Returns:
            Detailed volume information
        """
        if not self.api_key:
            return None
            
        try:
            params = {
                'api_key': self.api_key,
                'format': 'json',
                'field_list': 'id,name,aliases,deck,description,image,start_year,publisher,count_of_issues,issues,characters,people,api_detail_url,site_detail_url'
            }
            
            data = await self._make_request(f'/volume/4050-{volume_id}/', params)
            
            if not data or data.get('status_code') != 1:
                logger.error(f"Volume {volume_id} not found")
                return None
            
            return self._transform_volume(data.get('results'), detailed=True)
            
        except Exception as e:
            logger.error(f"Error fetching volume {volume_id}: {e}")
            return None
    
    async def get_issue(self, issue_id: int) -> Optional[Dict]:
        """
        Get detailed issue information
        
        Args:
            issue_id: ComicVine issue ID
            
        Returns:
            Detailed issue information
        """
        if not self.api_key:
            return None
            
        try:
            params = {
                'api_key': self.api_key,
                'format': 'json',
                'field_list': 'id,name,issue_number,deck,description,image,cover_date,store_date,volume,person_credits,character_credits,site_detail_url'
            }
            
            data = await self._make_request(f'/issue/4000-{issue_id}/', params)
            
            if not data or data.get('status_code') != 1:
                return None
            
            return self._transform_issue(data.get('results'))
            
        except Exception as e:
            logger.error(f"Error fetching issue {issue_id}: {e}")
            return None
    
    async def get_volume_issues(self, volume_id: int, page: int = 1, per_page: int = 100) -> List[Dict]:
        """
        Get all issues for a volume
        
        Args:
            volume_id: ComicVine volume ID
            page: Page number
            per_page: Results per page
            
        Returns:
            List of issues
        """
        if not self.api_key:
            return []
            
        try:
            params = {
                'api_key': self.api_key,
                'format': 'json',
                'filter': f'volume:{volume_id}',
                'sort': 'issue_number:asc',
                'limit': min(per_page, 100),
                'offset': (page - 1) * per_page,
                'field_list': 'id,name,issue_number,deck,image,cover_date,store_date,site_detail_url'
            }
            
            data = await self._make_request('/issues/', params)
            
            if not data or data.get('status_code') != 1:
                return []
            
            return [self._transform_issue(issue) for issue in data.get('results', [])]
            
        except Exception as e:
            logger.error(f"Error fetching issues for volume {volume_id}: {e}")
            return []
    
    async def _make_request(self, endpoint: str, params: dict) -> Optional[Dict]:
        """Make API request to ComicVine"""
        try:
            url = f"{self.API_URL}{endpoint}"
            
            headers = {
                'User-Agent': 'Alejandria/1.0 (Comic Library Manager)',
                'Accept': 'application/json'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    if response.status == 420:
                        logger.warning("ComicVine rate limit reached")
                        return {'status_code': 0, 'error': 'Rate limit exceeded'}
                    
                    if response.status != 200:
                        logger.error(f"ComicVine API error: HTTP {response.status}")
                        return None
                    
                    return await response.json()
                    
        except asyncio.TimeoutError:
            logger.error("ComicVine API timeout")
            return None
        except Exception as e:
            logger.error(f"ComicVine request error: {e}")
            return None
    
    def _transform_volume(self, volume: Dict, detailed: bool = False) -> Dict:
        """Transform ComicVine volume to our format"""
        if not volume:
            return {}
        
        # Get cover image
        image = volume.get('image', {}) or {}
        cover_image = (
            image.get('original_url') or
            image.get('super_url') or
            image.get('screen_large_url') or
            image.get('medium_url')
        )
        
        # Get publisher name
        publisher = volume.get('publisher')
        publisher_name = publisher.get('name') if isinstance(publisher, dict) else None
        
        # Clean description (remove HTML)
        description = self._clean_html(volume.get('description') or volume.get('deck') or '')
        
        result = {
            'comicvine_id': volume.get('id'),
            'title': volume.get('name', 'Unknown'),
            'description': description,
            'cover_image': cover_image,
            'publisher': publisher_name,
            'start_year': volume.get('start_year'),
            'count_of_issues': volume.get('count_of_issues'),
            'comicvine_url': volume.get('site_detail_url'),
            'aliases': self._parse_aliases(volume.get('aliases')),
        }
        
        if detailed:
            # Extract creators from people
            people = volume.get('people', []) or []
            writers = []
            artists = []
            colorists = []
            
            for person in people:
                if isinstance(person, dict):
                    name = person.get('name')
                    role = (person.get('role') or '').lower()
                    if name:
                        if 'writer' in role:
                            writers.append(name)
                        elif 'artist' in role or 'penciler' in role or 'penciller' in role:
                            artists.append(name)
                        elif 'colorist' in role:
                            colorists.append(name)
            
            # Extract main characters
            characters = volume.get('characters', []) or []
            character_names = [c.get('name') for c in characters if isinstance(c, dict) and c.get('name')][:10]
            
            # Get issues summary
            issues = volume.get('issues', []) or []
            
            result.update({
                'writers': list(set(writers))[:5],
                'artists': list(set(artists))[:5],
                'colorists': list(set(colorists))[:5],
                'characters': character_names,
                'issues_count': len(issues),
            })
        
        return result
    
    def _transform_issue(self, issue: Dict) -> Dict:
        """Transform ComicVine issue to our format"""
        if not issue:
            return {}
        
        image = issue.get('image', {}) or {}
        cover_image = (
            image.get('original_url') or
            image.get('super_url') or
            image.get('screen_large_url')
        )
        
        # Get volume info
        volume = issue.get('volume', {}) or {}
        
        # Extract creators
        credits = issue.get('person_credits', []) or []
        writers = []
        artists = []
        colorists = []
        
        for person in credits:
            if isinstance(person, dict):
                name = person.get('name')
                role = (person.get('role') or '').lower()
                if name:
                    if 'writer' in role:
                        writers.append(name)
                    elif 'artist' in role or 'penciler' in role:
                        artists.append(name)
                    elif 'colorist' in role:
                        colorists.append(name)
        
        return {
            'comicvine_id': issue.get('id'),
            'issue_number': issue.get('issue_number'),
            'title': issue.get('name'),
            'description': self._clean_html(issue.get('description') or issue.get('deck') or ''),
            'cover_image': cover_image,
            'release_date': issue.get('cover_date') or issue.get('store_date'),
            'volume_id': volume.get('id'),
            'volume_name': volume.get('name'),
            'comicvine_url': issue.get('site_detail_url'),
            'writers': list(set(writers)),
            'artists': list(set(artists)),
            'colorists': list(set(colorists)),
        }
    
    def _clean_html(self, text: str) -> str:
        """Remove HTML tags from text"""
        if not text:
            return ''
        # Remove HTML tags
        clean = re.sub(r'<[^>]+>', '', text)
        # Normalize whitespace
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean
    
    def _parse_aliases(self, aliases: str) -> List[str]:
        """Parse aliases string into list"""
        if not aliases:
            return []
        # Aliases are usually newline-separated
        return [a.strip() for a in aliases.split('\n') if a.strip()]


# Singleton instance
_comicvine_service = None

def get_comicvine_service() -> ComicVineService:
    """Get ComicVine service singleton"""
    global _comicvine_service
    if _comicvine_service is None:
        _comicvine_service = ComicVineService()
    return _comicvine_service
