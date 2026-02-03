"""
Anilist API Integration Service
Fetches manga metadata from Anilist GraphQL API
Con traducción automática al español
"""

import aiohttp
import asyncio
import logging
from typing import List, Dict, Optional
from datetime import datetime
from app.services.translator import (
    translate_genres,
    translate_status,
    translate_format,
    get_translator
)

logger = logging.getLogger(__name__)


class AnilistService:
    """
    Service for interacting with Anilist GraphQL API
    Provides rich manga metadata (covers, descriptions, genres, ratings)
    """

    API_URL = "https://graphql.anilist.co"

    # GraphQL Query for searching manga
    SEARCH_QUERY = """
    query ($search: String, $page: Int, $perPage: Int) {
      Page(page: $page, perPage: $perPage) {
        pageInfo {
          total
          currentPage
          lastPage
          hasNextPage
        }
        media(search: $search, type: MANGA, sort: SEARCH_MATCH) {
          id
          idMal
          title {
            romaji
            english
            native
          }
          description(asHtml: false)
          coverImage {
            extraLarge
            large
            medium
            color
          }
          bannerImage
          format
          status
          startDate {
            year
            month
            day
          }
          chapters
          volumes
          genres
          tags {
            name
            rank
          }
          averageScore
          popularity
          siteUrl
          countryOfOrigin
        }
      }
    }
    """

    # GraphQL Query for getting manga by ID
    GET_BY_ID_QUERY = """
    query ($id: Int) {
      Media(id: $id, type: MANGA) {
        id
        idMal
        title {
          romaji
          english
          native
        }
        description(asHtml: false)
        coverImage {
          extraLarge
          large
          medium
          color
        }
        bannerImage
        format
        status
        startDate {
          year
          month
          day
        }
        endDate {
          year
          month
          day
        }
        chapters
        volumes
        genres
        tags {
          name
          rank
        }
        averageScore
        meanScore
        popularity
        favourites
        siteUrl
        countryOfOrigin
        synonyms
        isAdult
        relations {
          edges {
            relationType
            node {
              id
              title {
                romaji
              }
              type
            }
          }
        }
        staff {
          edges {
            role
            node {
              name {
                full
              }
            }
          }
        }
      }
    }
    """

    async def search_manga(
        self,
        query: str,
        page: int = 1,
        per_page: int = 20
    ) -> Dict:
        """
        Search for manga on Anilist

        Args:
            query: Search term
            page: Page number
            per_page: Results per page

        Returns:
            Dict with search results and pagination info
        """
        try:
            variables = {
                'search': query,
                'page': page,
                'perPage': per_page
            }

            result = await self._execute_query(self.SEARCH_QUERY, variables)

            if not result or 'data' not in result:
                logger.error("Invalid response from Anilist")
                return {'results': [], 'pageInfo': {}}

            page_data = result['data']['Page']
            media_list = page_data['media']

            # Transform to our format
            results = [self._transform_media(media) for media in media_list]

            return {
                'results': results,
                'pageInfo': page_data['pageInfo']
            }

        except Exception as e:
            logger.error(f"Error searching Anilist: {e}")
            return {'results': [], 'pageInfo': {}}

    async def get_manga_by_id(self, anilist_id: int) -> Optional[Dict]:
        """
        Get detailed manga information by Anilist ID

        Args:
            anilist_id: Anilist manga ID

        Returns:
            Detailed manga information
        """
        try:
            variables = {'id': anilist_id}
            result = await self._execute_query(self.GET_BY_ID_QUERY, variables)

            if not result or 'data' not in result or not result['data']['Media']:
                logger.error(f"Manga {anilist_id} not found on Anilist")
                return None

            media = result['data']['Media']
            return self._transform_media(media, detailed=True)

        except Exception as e:
            logger.error(f"Error fetching manga {anilist_id}: {e}")
            return None

    async def _execute_query(self, query: str, variables: dict) -> Optional[Dict]:
        """
        Execute GraphQL query against Anilist API

        Args:
            query: GraphQL query string
            variables: Query variables

        Returns:
            API response
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.API_URL,
                    json={
                        'query': query,
                        'variables': variables
                    },
                    headers={
                        'Content-Type': 'application/json',
                        'Accept': 'application/json',
                    },
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    if response.status != 200:
                        logger.error(f"Anilist API error: HTTP {response.status}")
                        return None

                    return await response.json()

        except asyncio.TimeoutError:
            logger.error("Anilist API timeout")
            return None
        except Exception as e:
            logger.error(f"Error executing Anilist query: {e}")
            return None

    def _transform_media(self, media: Dict, detailed: bool = False) -> Dict:
        """
        Transform Anilist media object to our format
        Con traducción automática al español

        Args:
            media: Anilist media object
            detailed: Include detailed information

        Returns:
            Transformed manga data (traducido al español)
        """
        # Get best title (prefer English, fallback to Romaji, then Native)
        title = (
            media['title'].get('english') or
            media['title'].get('romaji') or
            media['title'].get('native') or
            'Unknown Title'
        )

        # Clean description (remove HTML if present)
        description = media.get('description', '')
        description_es = ''
        if description:
            # Basic HTML cleaning (Anilist should already provide clean text)
            description = description.replace('<br>', '\n').replace('<br/>', '\n')
            description = description.replace('<i>', '').replace('</i>', '')
            description = description.replace('<b>', '').replace('</b>', '')

            # Traducir descripción al español
            try:
                translator = get_translator()
                description_es = translator.translate_description(description)
            except Exception as e:
                logger.warning(f"Translation failed: {e}")
                description_es = description

        # Get cover image (prefer extraLarge, fallback to large)
        cover_image = media['coverImage'].get('extraLarge') or media['coverImage'].get('large')

        # Format start date
        start_date = None
        if media.get('startDate'):
            sd = media['startDate']
            if sd.get('year'):
                start_date = f"{sd['year']}"
                if sd.get('month'):
                    start_date += f"-{sd['month']:02d}"
                    if sd.get('day'):
                        start_date += f"-{sd['day']:02d}"

        # Traducir géneros y estado
        genres_en = media.get('genres', [])
        genres_es = translate_genres(genres_en)
        status_es = translate_status(media.get('status', ''))
        format_es = translate_format(media.get('format', ''))

        result = {
            'anilist_id': media['id'],
            'mal_id': media.get('idMal'),
            'title': title,
            'title_romaji': media['title'].get('romaji'),
            'title_english': media['title'].get('english'),
            'title_native': media['title'].get('native'),
            'description': description_es if description_es else description,
            'description_en': description,  # Guardar original también
            'cover_image': cover_image,
            'banner_image': media.get('bannerImage'),
            'cover_color': media['coverImage'].get('color'),
            'format': format_es,
            'format_en': media.get('format'),
            'status': status_es,
            'status_en': media.get('status'),
            'start_date': start_date,
            'chapters': media.get('chapters'),
            'volumes': media.get('volumes'),
            'genres': genres_es,
            'genres_en': genres_en,
            'average_score': media.get('averageScore'),
            'popularity': media.get('popularity'),
            'anilist_url': media.get('siteUrl'),
            'country': media.get('countryOfOrigin'),
        }

        # Add detailed info if requested
        if detailed:
            # Get top tags
            tags = media.get('tags', [])
            top_tags = [tag['name'] for tag in sorted(tags, key=lambda x: x.get('rank', 0), reverse=True)[:10]]

            # Get authors/artists from staff
            staff = media.get('staff', {}).get('edges', [])
            authors = []
            artists = []
            for edge in staff:
                role = edge.get('role', '').lower()
                name = edge.get('node', {}).get('name', {}).get('full')
                if name:
                    if 'story' in role or 'author' in role:
                        authors.append(name)
                    elif 'art' in role:
                        artists.append(name)

            result.update({
                'end_date': self._format_date(media.get('endDate')),
                'mean_score': media.get('meanScore'),
                'favourites': media.get('favourites'),
                'synonyms': media.get('synonyms', []),
                'is_adult': media.get('isAdult', False),
                'tags': top_tags,
                'authors': authors,
                'artists': artists,
            })

        return result

    def _format_date(self, date_obj: Optional[Dict]) -> Optional[str]:
        """Format Anilist date object to string"""
        if not date_obj or not date_obj.get('year'):
            return None

        result = f"{date_obj['year']}"
        if date_obj.get('month'):
            result += f"-{date_obj['month']:02d}"
            if date_obj.get('day'):
                result += f"-{date_obj['day']:02d}"

        return result

    async def get_trending_manga(self, page: int = 1, per_page: int = 20) -> List[Dict]:
        """
        Get trending manga from Anilist

        Args:
            page: Page number
            per_page: Results per page

        Returns:
            List of trending manga
        """
        trending_query = """
        query ($page: Int, $perPage: Int) {
          Page(page: $page, perPage: $perPage) {
            media(type: MANGA, sort: TRENDING_DESC) {
              id
              idMal
              title {
                romaji
                english
                native
              }
              description(asHtml: false)
              coverImage {
                extraLarge
                large
                color
              }
              bannerImage
              format
              status
              chapters
              volumes
              genres
              averageScore
              popularity
              trending
              siteUrl
            }
          }
        }
        """

        try:
            variables = {'page': page, 'perPage': per_page}
            result = await self._execute_query(trending_query, variables)

            if not result or 'data' not in result:
                return []

            media_list = result['data']['Page']['media']
            return [self._transform_media(media) for media in media_list]

        except Exception as e:
            logger.error(f"Error fetching trending manga: {e}")
            return []

    async def get_popular_manga(self, page: int = 1, per_page: int = 20) -> List[Dict]:
        """
        Get popular manga from Anilist

        Args:
            page: Page number
            per_page: Results per page

        Returns:
            List of popular manga
        """
        popular_query = """
        query ($page: Int, $perPage: Int) {
          Page(page: $page, perPage: $perPage) {
            media(type: MANGA, sort: POPULARITY_DESC) {
              id
              idMal
              title {
                romaji
                english
                native
              }
              description(asHtml: false)
              coverImage {
                extraLarge
                large
                color
              }
              format
              status
              chapters
              volumes
              genres
              averageScore
              popularity
              siteUrl
            }
          }
        }
        """

        try:
            variables = {'page': page, 'perPage': per_page}
            result = await self._execute_query(popular_query, variables)

            if not result or 'data' not in result:
                return []

            media_list = result['data']['Page']['media']
            return [self._transform_media(media) for media in media_list]

        except Exception as e:
            logger.error(f"Error fetching popular manga: {e}")
            return []
