"""
CBRComics.net Scraper
Spanish comic download site
"""

import logging
import re
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from .base import ComicScraperBase, ComicScraperResult, DownloadLink, HostType
from .title_parser import extract_year, extract_volume_number, extract_issue_number, extract_range

logger = logging.getLogger(__name__)


class CBRComicsScraper(ComicScraperBase):
    """Scraper for cbrcomics.net (Spanish comics)"""

    name = "cbrcomics"
    base_url = "https://cbrcomics.net"

    async def search(self, query: str, page: int = 1) -> List[Dict]:
        """
        Search for comics on CBRComics.net

        Args:
            query: Search term
            page: Page number

        Returns:
            List of search results with title, url, cover, etc.
        """
        search_url = f"{self.base_url}/?s={query}&paged={page}"
        logger.info(f"CBRComics: Searching page {page} for '{query}'")

        html = await self._get_page(search_url)
        if not html:
            logger.warning(f"CBRComics: Failed to fetch search results for '{query}'")
            return []

        soup = BeautifulSoup(html, 'html.parser')
        results = []

        # CBRComics uses WordPress Newsmag theme
        # Articles are in <article> tags or similar structure
        articles = soup.find_all('article') or soup.find_all('div', class_=re.compile(r'post|entry|item'))

        if not articles:
            # Try alternative selector
            articles = soup.select('.td-module-container') or soup.select('.td-block-span12')

        logger.info(f"CBRComics: Found {len(articles)} articles")

        for article in articles[:20]:  # Limit to 20 results
            try:
                # Find title and URL
                title_elem = article.find('h3') or article.find('h2') or article.find('h1')
                if not title_elem:
                    title_elem = article.find('a', class_=re.compile(r'title|entry-title'))

                if not title_elem:
                    continue

                # Get link
                link = title_elem.find('a') if title_elem.name != 'a' else title_elem
                if not link or not link.get('href'):
                    continue

                url = link['href']
                if not url.startswith('http'):
                    url = self.base_url + url

                title = link.get_text(strip=True)
                if not title:
                    continue

                # Get cover image
                img = article.find('img')
                cover = img.get('src') or img.get('data-src') if img else None

                # Get description/excerpt
                desc_elem = article.find('div', class_=re.compile(r'excerpt|description|summary'))
                description = desc_elem.get_text(strip=True) if desc_elem else ""

                results.append({
                    'title': title,
                    'url': url,
                    'cover': cover,
                    'description': description[:200] if description else ""
                })

            except Exception as e:
                logger.debug(f"CBRComics: Error parsing article: {e}")
                continue

        logger.info(f"CBRComics: Found {len(results)} results")
        return results

    async def get_download_links(self, url: str) -> ComicScraperResult:
        """
        Get download links from a comic page

        Args:
            url: URL of the comic page

        Returns:
            ComicScraperResult with download links
        """
        logger.info(f"CBRComics: Getting download links from {url}")

        html = await self._get_page(url)
        if not html:
            return ComicScraperResult(
                title="",
                source=self.name,
                source_url=url,
                success=False,
                error="Failed to fetch page"
            )

        soup = BeautifulSoup(html, 'html.parser')

        # Get title
        title_elem = soup.find('h1', class_=re.compile(r'title|entry-title')) or soup.find('h1')
        title = title_elem.get_text(strip=True) if title_elem else "Unknown"

        # Get description
        desc_elem = soup.find('div', class_=re.compile(r'content|entry-content'))
        description = desc_elem.get_text(strip=True)[:300] if desc_elem else ""

        # Find download links
        download_links = []

        # Method 1: Look for direct links in content
        if desc_elem:
            # Find all links in content area
            links = desc_elem.find_all('a', href=True)

            for link in links:
                href = link['href']

                # Check if this is a download link (direct host or redirect domain)
                is_download_link = False

                # Direct hosting links
                if any(host in href.lower() for host in ['mega.nz', 'mega.co', 'mediafire', 'drive.google', 'gdrive']):
                    is_download_link = True
                    host = self.detect_host(href)

                # CBRComics intermediate redirect domain
                elif 'cbrcomicsweb.space' in href.lower():
                    is_download_link = True
                    # Assume MEGA as default (most common for CBRComics)
                    host = HostType.MEGA
                    logger.info(f"CBRComics: Found redirect link: {href}")

                if is_download_link:
                    dl = DownloadLink(
                        url=href,
                        host=host,
                        quality_score=self.get_quality_score(host)
                    )
                    if not any(existing.url == href for existing in download_links):
                        download_links.append(dl)
                        logger.info(f"CBRComics: Found {host.value} link")

        # Method 2: Look for download buttons
        buttons = soup.find_all('a', href=True)
        for button in buttons:
            href = button.get('href')
            if href:
                # Check for download links or redirect domains
                is_download = any(host in href.lower() for host in ['mega', 'mediafire', 'drive.google', 'cbrcomicsweb.space'])

                if is_download:
                    if 'cbrcomicsweb.space' in href.lower():
                        host = HostType.MEGA  # Assume MEGA
                    else:
                        host = self.detect_host(href)

                    dl = DownloadLink(
                        url=href,
                        host=host,
                        quality_score=self.get_quality_score(host)
                    )
                    if not any(existing.url == href for existing in download_links):
                        download_links.append(dl)
                        logger.info(f"CBRComics: Found {host.value} link in button/link")

        # Method 3: Look specifically for images wrapped in links (common pattern)
        img_links = soup.find_all('a', href=True)
        for link in img_links:
            if link.find('img'):  # Has an image inside
                href = link['href']
                if 'cbrcomicsweb.space' in href.lower() or any(h in href.lower() for h in ['mega', 'mediafire', 'drive.google']):
                    if 'cbrcomicsweb.space' in href.lower():
                        host = HostType.MEGA
                    else:
                        host = self.detect_host(href)

                    dl = DownloadLink(
                        url=href,
                        host=host,
                        quality_score=self.get_quality_score(host)
                    )
                    if not any(existing.url == href for existing in download_links):
                        download_links.append(dl)
                        logger.info(f"CBRComics: Found {host.value} link with image")

        # Sort by quality
        download_links.sort(key=lambda x: x.quality_score, reverse=True)

        # Extract metadata using centralized parser
        file_size = None
        year = extract_year(title)

        result = ComicScraperResult(
            title=title,
            source=self.name,
            source_url=url,
            download_links=download_links,
            description=description,
            year=year,
            success=len(download_links) > 0,
            error=None if download_links else "No download links found"
        )

        logger.info(f"CBRComics: Found {len(download_links)} download links for '{title}'")
        return result

    async def search_for_issue(self, comic_title: str, issue_number: str) -> Optional[Dict]:
        """
        Search for a specific comic issue

        Args:
            comic_title: Comic title
            issue_number: Issue number (e.g., "#1", "1")

        Returns:
            Dict with title and url, or None if not found
        """
        # CBRComics typically has collections, not individual issues
        # Search for the comic title and return first match
        query = f"{comic_title} {issue_number}"
        results = await self.search(query)

        if not results:
            # Try without issue number
            results = await self.search(comic_title)

        if results:
            # Return first match
            return {
                'title': results[0]['title'],
                'url': results[0]['url']
            }

        return None
