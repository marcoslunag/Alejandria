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
        Get download links from a comic page.
        Resolves cbrcomicsweb.space redirect pages to actual MEGA/MediaFire URLs.

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

        # Collect all hrefs from the page (deduplicated)
        all_hrefs = set()
        # From content area
        if desc_elem:
            for link in desc_elem.find_all('a', href=True):
                all_hrefs.add(link['href'].strip())
        # From all page links (buttons, image links, etc.)
        for link in soup.find_all('a', href=True):
            all_hrefs.add(link['href'].strip())

        # Classify links: direct download hosts vs cbrcomicsweb.space redirects
        download_links = []
        redirect_urls = []

        for href in all_hrefs:
            href_lower = href.lower()

            # Direct hosting links (MEGA, MediaFire, Google Drive, etc.)
            if any(host in href_lower for host in ['mega.nz', 'mega.co', 'mediafire.com', 'drive.google.com', 'gdrive']):
                host = self.detect_host(href)
                dl = DownloadLink(
                    url=href,
                    host=host,
                    quality_score=self.get_quality_score(host)
                )
                if not any(existing.url == href for existing in download_links):
                    download_links.append(dl)
                    logger.info(f"CBRComics: Found direct {host.value} link")

            # cbrcomicsweb.space redirect pages — need to resolve
            elif 'cbrcomicsweb.space' in href_lower:
                redirect_urls.append(href)

        # Resolve cbrcomicsweb.space redirects to get actual download URLs
        if redirect_urls:
            logger.info(f"CBRComics: Resolving {len(redirect_urls)} cbrcomicsweb.space redirect(s)...")
            resolved = await self._resolve_redirect_pages(redirect_urls)
            for dl in resolved:
                if not any(existing.url == dl.url for existing in download_links):
                    download_links.append(dl)

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

    async def _resolve_redirect_pages(self, redirect_urls: List[str]) -> List[DownloadLink]:
        """
        Resolve cbrcomicsweb.space redirect pages to actual download URLs.
        These pages contain direct links to MEGA, MediaFire, etc.

        Args:
            redirect_urls: List of cbrcomicsweb.space URLs to resolve

        Returns:
            List of resolved DownloadLink objects with actual host URLs
        """
        import base64
        from urllib.parse import unquote
        import asyncio

        resolved_links = []
        seen_urls = set()

        async def resolve_one(redirect_url: str) -> List[DownloadLink]:
            links = []
            try:
                html = await self._get_page(redirect_url, timeout=15)
                if not html:
                    logger.warning(f"CBRComics: Failed to fetch redirect page: {redirect_url}")
                    return links

                soup = BeautifulSoup(html, 'html.parser')

                # Method 1: Direct host links in href attributes
                for a in soup.find_all('a', href=True):
                    href = a['href'].strip()
                    if any(host in href.lower() for host in [
                        'mega.nz', 'mega.co', 'mediafire.com',
                        'drive.google.com', 'fireload', 'terabox',
                        'krakenfiles.com', 'upload.ee', 'megaup.net'
                    ]):
                        host = self.detect_host(href)
                        dl = DownloadLink(
                            url=href,
                            host=host,
                            quality_score=self.get_quality_score(host)
                        )
                        links.append(dl)
                        logger.info(f"CBRComics: Resolved redirect -> {host.value}: {href[:80]}")

                # Method 2: data-link base64 attributes (LinkContainer plugin)
                for el in soup.find_all(attrs={'data-link': True}):
                    encoded = el.get('data-link')
                    if encoded:
                        try:
                            decoded = unquote(base64.b64decode(encoded).decode())
                            if any(host in decoded.lower() for host in [
                                'mega.nz', 'mediafire.com', 'drive.google.com'
                            ]):
                                host = self.detect_host(decoded)
                                dl = DownloadLink(
                                    url=decoded,
                                    host=host,
                                    quality_score=self.get_quality_score(host)
                                )
                                links.append(dl)
                                logger.info(f"CBRComics: Decoded data-link -> {host.value}: {decoded[:80]}")
                        except Exception as e:
                            logger.debug(f"CBRComics: data-link decode error: {e}")

            except Exception as e:
                logger.warning(f"CBRComics: Error resolving redirect {redirect_url}: {e}")

            return links

        # Resolve all redirect URLs (limit concurrency to 3)
        semaphore = asyncio.Semaphore(3)

        async def resolve_with_limit(url):
            async with semaphore:
                return await resolve_one(url)

        tasks = [resolve_with_limit(url) for url in redirect_urls[:10]]  # Max 10 redirects
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"CBRComics: Redirect resolution error: {result}")
                continue
            for dl in result:
                if dl.url not in seen_urls:
                    seen_urls.add(dl.url)
                    resolved_links.append(dl)

        logger.info(f"CBRComics: Resolved {len(resolved_links)} links from {len(redirect_urls)} redirect(s)")
        return resolved_links

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
