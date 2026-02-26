"""
ZonaComics.com Comic Scraper
Scrapes Spanish comics from zonacomics.com
Uses Playwright for full page rendering and ouo.io link resolution
"""

import asyncio
import logging
import re
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from urllib.parse import quote, urljoin

from .base import ComicScraperBase, ComicScraperResult, HostType, DownloadLink
from .title_parser import extract_issue_number, extract_year, extract_file_size

logger = logging.getLogger(__name__)

# Max concurrent ouo.io resolutions
OUO_CONCURRENCY = 3
# Timeout per ouo.io resolution (seconds)
OUO_RESOLVE_TIMEOUT = 25


class ZonaComicsScraper(ComicScraperBase):
    """Scraper for zonacomics.com using Playwright"""

    name = "zonacomics"
    base_url = "https://zonacomics.com"

    async def _get_playwright_scraper(self):
        """Get the Playwright singleton instance"""
        from ..book_scrapers.playwright_scraper import get_playwright_scraper
        return await get_playwright_scraper()

    async def search(self, query: str, page: int = 1) -> List[Dict]:
        """Search for comics on zonacomics.com"""
        try:
            search_url = f"{self.base_url}/page/{page}/?s={quote(query)}"
            logger.info(f"ZonaComics: Searching page {page} for '{query}'")

            html = await self._get_page(search_url)
            if not html:
                logger.error("ZonaComics: Failed to get search page")
                return []

            soup = BeautifulSoup(html, "html.parser")
            results = []
            seen_urls = set()

            articles = soup.find_all("article", class_=re.compile(r"post-\d+"))
            logger.info(f"ZonaComics: Found {len(articles)} articles")

            for article in articles:
                try:
                    title_elem = article.find(["h2", "h3"], class_=re.compile(r"entry-title|post-title"))
                    if not title_elem:
                        continue

                    link = title_elem.find("a")
                    if not link:
                        continue

                    title = link.get_text(strip=True)
                    url = link.get("href", "")

                    if not title or not url or url in seen_urls:
                        continue
                    seen_urls.add(url)

                    cover = None
                    img_elem = article.find("img")
                    if img_elem:
                        cover = img_elem.get("src") or img_elem.get("data-src") or img_elem.get("data-lazy-src")

                    year = extract_year(title)

                    results.append({
                        "title": title,
                        "url": url,
                        "cover": cover,
                        "source": self.name,
                        "file_size": None,
                        "year": year
                    })

                except Exception as e:
                    logger.debug(f"ZonaComics: Error parsing article: {e}")
                    continue

            logger.info(f"ZonaComics: Found {len(results)} results")
            for i, r in enumerate(results[:5]):
                logger.info(f"  Result {i+1}: {r.get('title', 'No title')[:60]}")
            return results

        except Exception as e:
            logger.error(f"ZonaComics search error: {e}")
            return []

    async def get_download_links(self, url: str, resolve_ouo: bool = True) -> ComicScraperResult:
        """Get download links from a comic page using Playwright.
        resolve_ouo=False skips ouo resolution and returns shorteners immediately."""
        playwright_scraper = None
        page = None
        try:
            logger.info(f"ZonaComics: Getting download links from {url} (Playwright)")

            playwright_scraper = await self._get_playwright_scraper()
            page = await playwright_scraper._create_page()

            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(3)  # Wait for lazy-loaded content

            # Extract title
            title_elem = await page.query_selector('h1.entry-title, h1.post-title, h1')
            title = await title_elem.inner_text() if title_elem else "Unknown"

            # Extract cover
            cover = None
            cover_elem = await page.query_selector('.entry-content img, .post-content img, article img')
            if cover_elem:
                cover = await cover_elem.get_attribute('src') or await cover_elem.get_attribute('data-src')

            # Extract description
            description = None
            desc_elems = await page.query_selector_all('.entry-content p, .post-content p')
            if desc_elems:
                texts = []
                for elem in desc_elems[:2]:
                    texts.append(await elem.inner_text())
                description = " ".join(texts)[:500]

            # Extract ALL links from the content area
            all_links = await page.query_selector_all('.entry-content a[href], .post-content a[href], article a[href]')
            logger.info(f"ZonaComics: Found {len(all_links)} links on page")

            ouo_links = []
            direct_links = []

            for link in all_links:
                href = await link.get_attribute('href')
                if not href:
                    continue
                href = href.strip()

                # Get context text (the link text and parent text)
                link_text = (await link.inner_text()).strip().lower()
                parent_elem = await link.evaluate_handle('el => el.parentElement')
                parent_text = ""
                if parent_elem:
                    try:
                        parent_text = (await parent_elem.evaluate('el => el.textContent')).lower()
                    except:
                        pass

                # Check for ouo.io shorteners
                if 'ouo.io' in href or 'ouo.press' in href:
                    # Try to detect host from surrounding context
                    detected_host = self._detect_host_from_context(link_text, parent_text)

                    # Try to extract issue number from context
                    issue_num = self._extract_issue_number(link_text, parent_text)

                    ouo_links.append({
                        'url': href,
                        'detected_host': detected_host,
                        'issue_num': issue_num,
                        'context': link_text or parent_text[:100]
                    })
                    logger.info(f"ZonaComics: Found ouo.io link: {href} (host hint: {detected_host.value}, issue: {issue_num})")

                # Check for direct download host links
                elif any(host in href.lower() for host in ['mega.nz', 'mega.co', 'mediafire.com', 'drive.google.com', 'fireload', 'terabox']):
                    host = self.detect_host(href)
                    direct_links.append({
                        'url': href,
                        'host': host
                    })
                    logger.info(f"ZonaComics: Found direct {host.value} link: {href[:60]}")

            # Get full HTML before closing page (for file_size extraction)
            html_content = await page.content()

            await page.close()
            page = None

            # Build download links list
            download_links = []

            # Add direct links first (they don't need resolution)
            for dl in direct_links:
                link_obj = DownloadLink(
                    url=dl['url'],
                    host=dl['host'],
                    quality_score=self.get_quality_score(dl['host'])
                )
                if not any(existing.url == dl['url'] for existing in download_links):
                    download_links.append(link_obj)

            # Resolve ouo.io links using Playwright
            # Limit to 10 links max to avoid excessive resolution time
            if ouo_links:
                if not resolve_ouo:
                    # Skip resolution — caller will resolve progressively and commit after each
                    logger.info(f"ZonaComics: Skipping ouo resolution (resolve_ouo=False), returning {len(ouo_links)} as shorteners")
                    for ouo_info in ouo_links[:10]:
                        shortener_link = DownloadLink(
                            url=ouo_info['url'],
                            host=ouo_info['detected_host'],
                            quality_score=self.get_quality_score(ouo_info['detected_host']),
                            link_status='shortener'
                        )
                        if not any(existing.url == shortener_link.url for existing in download_links):
                            download_links.append(shortener_link)
                else:
                    links_to_resolve = ouo_links[:10]
                    if len(ouo_links) > 10:
                        logger.info(f"ZonaComics: Limiting resolution to 10 of {len(ouo_links)} ouo.io links")
                    logger.info(f"ZonaComics: Resolving {len(links_to_resolve)} ouo.io links with Playwright...")
                    resolved = await self._resolve_ouo_links_batch(links_to_resolve, playwright_scraper)
                    for resolved_link in resolved:
                        if not any(existing.url == resolved_link.url for existing in download_links):
                            download_links.append(resolved_link)

                # Add remaining unresolved links as-is (will be resolved at download time)
                for ouo_info in ouo_links[10:]:
                    fallback_link = DownloadLink(
                        url=ouo_info['url'],
                        host=ouo_info['detected_host'],
                        quality_score=self.get_quality_score(ouo_info['detected_host']),
                        link_status='shortener'
                    )
                    if not any(existing.url == fallback_link.url for existing in download_links):
                        download_links.append(fallback_link)

            # Extract file size from HTML
            file_size = extract_file_size(html_content) if html_content else None

            # Extract year
            year = extract_year(title)

            # Sort by quality
            download_links.sort(key=lambda x: x.quality_score, reverse=True)

            logger.info(f"ZonaComics: Total download links: {len(download_links)} "
                        f"(direct: {len(direct_links)}, resolved from ouo: {len(download_links) - len(direct_links)})")

            return ComicScraperResult(
                title=title, source=self.name, source_url=url,
                download_links=download_links, description=description,
                cover_image=cover, file_size=file_size, year=year,
                success=len(download_links) > 0,
                error=None if download_links else "No download links found"
            )

        except Exception as e:
            logger.error(f"ZonaComics scrape error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return ComicScraperResult(
                title="Unknown", source=self.name, source_url=url,
                success=False, error=str(e)
            )
        finally:
            if page:
                await page.close()

    async def _resolve_ouo_links_batch(self, ouo_links: List[Dict], playwright_scraper) -> List[DownloadLink]:
        """
        Resolve multiple ouo.io links in parallel with concurrency limit.

        Args:
            ouo_links: List of dicts with 'url', 'detected_host', 'issue_num', 'context'
            playwright_scraper: Playwright scraper instance for creating pages

        Returns:
            List of resolved DownloadLink objects
        """
        semaphore = asyncio.Semaphore(OUO_CONCURRENCY)
        resolved_links = []

        async def resolve_one(ouo_info: Dict) -> Optional[DownloadLink]:
            async with semaphore:
                result = await self._resolve_ouo_with_playwright(
                    ouo_info['url'], playwright_scraper
                )
                if result:
                    return result

                # Fallback: keep ouo.io link with detected host hint
                logger.warning(f"ZonaComics: Could not resolve {ouo_info['url']}, keeping as {ouo_info['detected_host'].value}")
                return DownloadLink(
                    url=ouo_info['url'],
                    host=ouo_info['detected_host'],
                    quality_score=self.get_quality_score(ouo_info['detected_host']),
                    link_status='shortener'
                )

        tasks = [resolve_one(ouo_info) for ouo_info in ouo_links]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, DownloadLink):
                resolved_links.append(result)
            elif isinstance(result, Exception):
                logger.error(f"ZonaComics: Resolution task error: {result}")

        return resolved_links

    async def _resolve_ouo_with_playwright(self, ouo_url: str, playwright_scraper) -> Optional[DownloadLink]:
        """
        Resolve a single ouo.io link using Playwright.
        Navigates to the ouo.io page, handles the bypass form, and captures the final URL.

        Args:
            ouo_url: The ouo.io shortened URL
            playwright_scraper: Playwright scraper instance

        Returns:
            DownloadLink with resolved URL, or None if failed
        """
        page = None
        try:
            page = await playwright_scraper._create_page()
            logger.info(f"ZonaComics OUO: Resolving {ouo_url}")

            # Navigate to ouo.io
            await page.goto(ouo_url, wait_until='domcontentloaded', timeout=15000)
            await asyncio.sleep(2)

            current_url = page.url

            # Check if already redirected past ouo.io
            if 'ouo.io' not in current_url and 'ouo.press' not in current_url:
                host = self.detect_host(current_url)
                logger.info(f"ZonaComics OUO: Direct redirect to {host.value}: {current_url[:80]}")
                return DownloadLink(
                    url=current_url,
                    host=host,
                    quality_score=self.get_quality_score(host)
                )

            # OUO.io has a 2-step form bypass
            # Step 1: First form page
            for step in range(2):
                form = await page.query_selector('form#form-bypass')
                if not form:
                    # Try alternative form selectors
                    form = await page.query_selector('form')

                if form:
                    # Wait for any timer (ouo.io usually has a 5s delay)
                    await asyncio.sleep(6)

                    # Find and click submit button
                    submit_btn = await page.query_selector(
                        'input[type="submit"], button[type="submit"], '
                        '#btn-main, .btn-main, a.btn'
                    )
                    if submit_btn:
                        try:
                            await submit_btn.click()
                            await asyncio.sleep(3)

                            # Wait for navigation
                            try:
                                await page.wait_for_load_state('networkidle', timeout=10000)
                            except:
                                pass

                        except Exception as e:
                            logger.debug(f"ZonaComics OUO: Click failed on step {step+1}: {e}")

                    current_url = page.url

                    # Check if we left ouo.io
                    if 'ouo.io' not in current_url and 'ouo.press' not in current_url:
                        host = self.detect_host(current_url)
                        logger.info(f"ZonaComics OUO: Resolved after step {step+1} to {host.value}: {current_url[:80]}")
                        return DownloadLink(
                            url=current_url,
                            host=host,
                            quality_score=self.get_quality_score(host)
                        )

            # Final check: look for download links in the page content
            html_content = await page.content()

            # Search for known host URLs in the HTML
            host_patterns = [
                (r'https?://(?:www\.)?mega\.nz/[^\s"\'<>]+', HostType.MEGA),
                (r'https?://(?:www\.)?mediafire\.com/[^\s"\'<>]+', HostType.MEDIAFIRE),
                (r'https?://drive\.google\.com/[^\s"\'<>]+', HostType.GOOGLE_DRIVE),
                (r'https?://(?:www\.)?fireload\.com/[^\s"\'<>]+', HostType.FIRELOAD),
                (r'https?://(?:www\.)?terabox\.com/[^\s"\'<>]+', HostType.TERABOX),
            ]

            for pattern, host_type in host_patterns:
                matches = re.findall(pattern, html_content)
                if matches:
                    resolved_url = matches[0].rstrip('"\'')
                    logger.info(f"ZonaComics OUO: Found {host_type.value} in HTML: {resolved_url[:80]}")
                    return DownloadLink(
                        url=resolved_url,
                        host=host_type,
                        quality_score=self.get_quality_score(host_type)
                    )

            # Check all links on the page
            page_links = await page.query_selector_all('a[href]')
            for link in page_links:
                href = await link.get_attribute('href')
                if href:
                    host = self.detect_host(href)
                    if host != HostType.UNKNOWN and 'ouo' not in href.lower():
                        logger.info(f"ZonaComics OUO: Found {host.value} link in page: {href[:80]}")
                        return DownloadLink(
                            url=href,
                            host=host,
                            quality_score=self.get_quality_score(host)
                        )

            logger.warning(f"ZonaComics OUO: Could not resolve {ouo_url}, final URL: {page.url[:80]}")
            return None

        except asyncio.TimeoutError:
            logger.warning(f"ZonaComics OUO: Timeout resolving {ouo_url}")
            return None
        except Exception as e:
            logger.error(f"ZonaComics OUO: Error resolving {ouo_url}: {e}")
            return None
        finally:
            if page:
                await page.close()

    def _detect_host_from_context(self, link_text: str, parent_text: str) -> HostType:
        """Detect the download host from surrounding text context"""
        combined = f"{link_text} {parent_text}".lower()

        if 'mega' in combined and 'mediafire' not in combined:
            return HostType.MEGA
        elif 'mediafire' in combined:
            return HostType.MEDIAFIRE
        elif 'google drive' in combined or 'gdrive' in combined or 'drive' in combined:
            return HostType.GOOGLE_DRIVE
        elif 'fireload' in combined:
            return HostType.FIRELOAD
        elif 'terabox' in combined:
            return HostType.TERABOX

        return HostType.UNKNOWN

    def _extract_issue_number(self, link_text: str, parent_text: str) -> Optional[str]:
        """Extract issue number from link/parent text"""
        combined = f"{link_text} {parent_text}"
        result = extract_issue_number(combined)
        return str(result) if result else None

    async def search_for_issue(self, comic_title: str, issue_number: str) -> Optional[Dict]:
        """Search for a specific issue of a comic"""
        query = f"{comic_title}"
        logger.info(f"ZonaComics: Searching for comic: '{query}'")
        results = await self.search(query)

        if not results and comic_title.lower().startswith("the "):
            query = comic_title[4:]
            logger.info(f"ZonaComics: Retrying without 'The': '{query}'")
            results = await self.search(query)

        if not results:
            logger.info(f"ZonaComics: No results found for '{comic_title}'")
            return None

        comic_title_lower = comic_title.lower().strip()

        # Look for title match (collections usually contain full series)
        for result in results:
            title_lower = result["title"].lower()

            title_matches = (
                comic_title_lower in title_lower or
                comic_title_lower.replace(" ", "") in title_lower.replace(" ", "")
            )

            if title_matches:
                if any(keyword in title_lower for keyword in ["completo", "complete", "#1-", "vol", "volumen"]):
                    logger.info(f"ZonaComics: Found collection: {result['title'][:60]}")
                    return result

        # If no collection found, return first title match
        for result in results:
            title_lower = result["title"].lower()
            title_matches = (
                comic_title_lower in title_lower or
                comic_title_lower.replace(" ", "") in title_lower.replace(" ", "")
            )
            if title_matches:
                logger.info(f"ZonaComics: Found title match: {result['title'][:60]}")
                return result

        logger.warning(f"ZonaComics: No matching results for '{comic_title}'")
        return None
