"""
TuMangaOnline Scraper - Second manga scraper as fallback
Uses requests + BeautifulSoup (no Playwright needed for search)
"""

import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from urllib.parse import quote
import logging
import time

logger = logging.getLogger(__name__)


class TuMangaScraper:
    """
    Fallback scraper for Spanish manga downloads.
    Targets tumangaonline.me as an alternative to MangayComics.

    Interface matches MangayComicsScraper:
    - search_manga(title) → [{title, url, cover, slug}]
    - get_download_links(url) → [{url, host, quality}]
    """

    BASE_URL = "https://tumangaonline.me"
    SOURCE_NAME = "TuMangaOnline"

    def __init__(self, rate_limit: float = 1.5):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        })
        self.rate_limit = rate_limit
        self.last_request = 0

    def _rate_limit_wait(self):
        elapsed = time.time() - self.last_request
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self.last_request = time.time()

    def search_manga(self, query: str) -> List[Dict]:
        """
        Search for manga on TuMangaOnline.

        Returns:
            List[Dict]: [{'title': str, 'url': str, 'cover': Optional[str], 'slug': str, 'source': str}]
        """
        try:
            self._rate_limit_wait()
            # TuMangaOnline search URL pattern
            search_url = f"{self.BASE_URL}/library?title={quote(query)}"
            logger.info(f"[TuMangaScraper] Searching: {search_url}")

            response = self.session.get(search_url, timeout=12)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')
            results = []

            # Try multiple selectors for different site layouts
            cards = soup.select('.card, .manga-card, article.post, .book-item, .list-item')
            if not cards:
                cards = soup.select('article')

            for card in cards[:15]:
                try:
                    link = card.select_one('a[href*="/library/"], a[href*="/manga/"], h2 a, h3 a, .title a, .card-title a')
                    if not link:
                        link = card.select_one('a')
                    if not link:
                        continue

                    title = link.get_text(strip=True) or card.select_one('.title, h2, h3, .card-title')
                    if not title:
                        continue
                    if hasattr(title, 'get_text'):
                        title = title.get_text(strip=True)

                    url = link.get('href', '')
                    if url and not url.startswith('http'):
                        url = self.BASE_URL + url

                    cover = None
                    img = card.select_one('img')
                    if img:
                        cover = img.get('src') or img.get('data-src') or img.get('data-lazy-src')

                    if title and url:
                        slug = url.split('/')[-1].split('?')[0] or query.lower().replace(' ', '-')
                        results.append({
                            'title': title,
                            'url': url,
                            'cover': cover,
                            'slug': slug,
                            'source': self.SOURCE_NAME,
                        })
                except Exception as e:
                    logger.debug(f"[TuMangaScraper] Card parse error: {e}")
                    continue

            logger.info(f"[TuMangaScraper] Found {len(results)} results for '{query}'")
            return results

        except requests.exceptions.Timeout:
            logger.warning(f"[TuMangaScraper] Timeout searching for '{query}'")
            return []
        except Exception as e:
            logger.warning(f"[TuMangaScraper] Error searching '{query}': {e}")
            return []

    def get_download_links(self, manga_url: str) -> List[Dict]:
        """
        Get download links from a manga page.

        Returns:
            List[Dict]: [{'url': str, 'host': str, 'quality': int}]
        """
        try:
            self._rate_limit_wait()
            response = self.session.get(manga_url, timeout=12)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')
            links = []

            KNOWN_HOSTS = {
                'mega.nz': ('mega', 70),
                'mega.co.nz': ('mega', 70),
                'mediafire.com': ('mediafire', 90),
                'drive.google.com': ('google_drive', 95),
                'dropbox.com': ('dropbox', 65),
                'sendspace.com': ('sendspace', 50),
                'zippyshare.com': ('zippyshare', 55),
            }

            for a in soup.select('a[href]'):
                href = a.get('href', '')
                for domain, (host, quality) in KNOWN_HOSTS.items():
                    if domain in href:
                        links.append({'url': href, 'host': host, 'quality': quality})
                        break

            logger.info(f"[TuMangaScraper] Found {len(links)} download links at {manga_url}")
            return links

        except Exception as e:
            logger.warning(f"[TuMangaScraper] Error getting links from {manga_url}: {e}")
            return []


def get_tumanga_scraper() -> TuMangaScraper:
    return TuMangaScraper()
