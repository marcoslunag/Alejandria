"""
MegaComicsTV3 Scraper
Scrapes comics from megacomicstv3.blogspot.com

Uses Blogger theme with .card containers for search results.
Download links use ouo.io (→ MEGA) and uii.io (→ MediaFire) shorteners.
"""

import aiohttp
import asyncio
import re
import logging
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from urllib.parse import quote

from .base import (
    ComicScraperBase,
    ComicScraperResult,
    DownloadLink,
    HostType
)
from .title_parser import parse_title, extract_range, extract_file_size, extract_year, clean_title

logger = logging.getLogger(__name__)

# Max concurrent ouo.io resolutions
OUO_CONCURRENCY = 3
OUO_RESOLVE_TIMEOUT = 25


class MegaComicsScraper(ComicScraperBase):
    """
    Scraper for MegaComicsTV3 (megacomicstv3.blogspot.com)

    Features:
    - Spanish comics (Marvel, DC, Indies)
    - CBR/CBZ format
    - Links behind ouo.io (→ MEGA) and uii.io (→ MediaFire) shorteners
    - Blogger-based site with .card theme
    """

    name = "megacomics"
    base_url = "https://megacomicstv3.blogspot.com"

    async def _get_playwright_scraper(self):
        """Get the Playwright singleton instance"""
        from ..book_scrapers.playwright_scraper import get_playwright_scraper
        return await get_playwright_scraper()

    async def search(self, query: str, page: int = 1) -> List[Dict]:
        """
        Search for comics on MegaComicsTV3.
        Uses Blogger's search with .card theme containers.
        """
        results = []

        try:
            search_url = f"{self.base_url}/search?q={quote(query)}"
            if page > 1:
                start = (page - 1) * 20
                search_url += f"&start={start}"

            logger.info(f"MegaComics: Searching for '{query}' at {search_url}")

            html = await self._get_page(search_url)
            if not html:
                logger.error("MegaComics: Failed to get search page")
                return []

            soup = BeautifulSoup(html, 'html.parser')

            # MegaComicsTV3 uses .card containers
            cards = soup.select('.card')

            if not cards:
                # Fallback: try other common Blogger selectors
                cards = soup.select('article, .post, .hentry, .Blog1 .post-outer')

            for card in cards:
                try:
                    # Get title and link from .card__title a
                    title_elem = card.select_one('.card__title a, h2 a, h3 a, .post-title a, .entry-title a')
                    if not title_elem:
                        continue

                    title = title_elem.get_text(strip=True)
                    url = title_elem.get('href', '')

                    if not url or not title:
                        continue

                    # Get cover image from .card__image img
                    img_elem = card.select_one('.card__image img, img')
                    cover = None
                    if img_elem:
                        cover = img_elem.get('src', '') or img_elem.get('data-src', '')

                    # Parse title for issue info using centralized parser
                    title_info = parse_title(title)
                    issues = None
                    if title_info.range_start is not None and title_info.range_end is not None:
                        issues = f"{title_info.range_start}/{title_info.range_end}"
                    elif title_info.total_issues:
                        issues = f"1/{title_info.total_issues}"

                    # Clean title (remove brackets info)
                    cleaned_title = title_info.clean_title

                    results.append({
                        'title': cleaned_title,
                        'full_title': title,
                        'url': url,
                        'cover': cover,
                        'issues': issues,
                        'source': self.name
                    })

                except Exception as e:
                    logger.warning(f"MegaComics: Error parsing card: {e}")
                    continue

            logger.info(f"MegaComics search '{query}': found {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"MegaComics search error: {e}")
            return []

    async def get_download_links(self, url: str) -> ComicScraperResult:
        """
        Extract download links from a comic page.
        MegaComicsTV3 uses ouo.io (→ MEGA) and uii.io (→ MediaFire) shorteners.
        Resolves ouo.io links via Playwright, keeps uii.io as-is.
        """
        try:
            html = await self._get_page(url)
            if not html:
                return ComicScraperResult(
                    title="Unknown",
                    source=self.name,
                    source_url=url,
                    success=False,
                    error="Failed to fetch page"
                )

            soup = BeautifulSoup(html, 'html.parser')

            # Get title
            title_elem = soup.select_one('h1, h3.post-title, .post-title, .entry-title')
            title = title_elem.get_text(strip=True) if title_elem else "Unknown"
            title_clean = clean_title(title)

            # Get cover image
            cover = None
            post_body = soup.select_one('.post-body, .entry-content')
            if post_body:
                img_elem = post_body.select_one('img')
                if img_elem:
                    cover = img_elem.get('src', '')

            # Extract file info
            file_size = extract_file_size(html)
            year = extract_year(html)

            # Strategy: Parse download table to get issue-to-link mapping
            # MegaComics uses a <table> with rows: <td>#1 - #2</td><td>[MEGA][MF]</td>
            download_links = []
            table_rows = self._parse_download_table(soup)

            if table_rows:
                logger.info(f"MegaComics: Found download table with {len(table_rows)} rows")
                ouo_links_with_issues = []
                uii_links_with_issues = []

                for row in table_rows:
                    issue_label = row['issue_label']  # e.g. "#1 - #2", "#3"
                    for link_info in row['links']:
                        link_info['issue_label'] = issue_label

                        if 'ouo.io' in link_info['url'] or 'ouo.press' in link_info['url']:
                            ouo_links_with_issues.append(link_info)
                        elif 'uii.io' in link_info['url']:
                            uii_links_with_issues.append(link_info)
                        else:
                            host = self.detect_host(link_info['url'])
                            if host != HostType.UNKNOWN:
                                dl = self.create_download_link(link_info['url'], file_size)
                                dl.issue_range = issue_label
                                download_links.append(dl)

                logger.info(
                    f"MegaComics: Table links: {len(ouo_links_with_issues)} ouo.io, "
                    f"{len(uii_links_with_issues)} uii.io, {len(download_links)} direct"
                )

                # Resolve ouo.io links via Playwright (up to 10)
                if ouo_links_with_issues:
                    links_to_resolve = ouo_links_with_issues[:10]
                    try:
                        playwright_scraper = await self._get_playwright_scraper()
                        resolved = await self._resolve_ouo_links_batch(
                            links_to_resolve, playwright_scraper
                        )
                        # Transfer issue_range from the original ouo link info
                        for i, resolved_link in enumerate(resolved):
                            if i < len(links_to_resolve):
                                resolved_link.issue_range = links_to_resolve[i].get('issue_label')
                        download_links.extend(resolved)
                        logger.info(f"MegaComics: Resolved {len(resolved)}/{len(links_to_resolve)} ouo.io links")
                    except Exception as e:
                        logger.error(f"MegaComics: Playwright resolution failed: {e}")
                        for ouo_info in links_to_resolve:
                            host = ouo_info.get('detected_host', HostType.MEGA)
                            download_links.append(DownloadLink(
                                url=ouo_info['url'],
                                host=host,
                                quality_score=self.get_quality_score(host),
                                file_size=file_size,
                                link_status='shortener',
                                issue_range=ouo_info.get('issue_label')
                            ))

                # Save uii.io links as-is (need captcha)
                for uii_info in uii_links_with_issues:
                    host = uii_info.get('detected_host', HostType.MEDIAFIRE)
                    download_links.append(DownloadLink(
                        url=uii_info['url'],
                        host=host,
                        quality_score=40,
                        file_size=file_size,
                        link_status='needs_captcha',
                        issue_range=uii_info.get('issue_label')
                    ))

            else:
                # Fallback: no table found, extract all links without issue mapping
                logger.info("MegaComics: No download table found, extracting links without issue mapping")
                all_links = soup.find_all('a', href=True)
                ouo_links = []
                uii_links = []

                for link in all_links:
                    href = link.get('href', '').strip()
                    if not href or href.startswith('#') or 'javascript:' in href:
                        continue

                    link_text = link.get_text(strip=True)
                    img_in_link = link.select_one('img')
                    img_alt = img_in_link.get('alt', '') if img_in_link else ''
                    img_src = img_in_link.get('src', '') if img_in_link else ''
                    context = f"{link_text} {img_alt} {img_src}".lower()
                    detected_host = self._detect_host_from_context(context)

                    if 'ouo.io' in href or 'ouo.press' in href:
                        ouo_links.append({'url': href, 'detected_host': detected_host, 'context': context})
                    elif 'uii.io' in href:
                        uii_links.append({'url': href, 'detected_host': detected_host, 'context': context})
                    else:
                        host = self.detect_host(href)
                        if host in [HostType.MEGA, HostType.MEDIAFIRE, HostType.GOOGLE_DRIVE,
                                    HostType.TERABOX, HostType.FIRELOAD]:
                            if not any(dl.url == href for dl in download_links):
                                download_links.append(self.create_download_link(href, file_size))

                logger.info(
                    f"MegaComics: Fallback links: {len(ouo_links)} ouo.io, "
                    f"{len(uii_links)} uii.io, {len(download_links)} direct"
                )

                if ouo_links:
                    links_to_resolve = ouo_links[:10]
                    try:
                        playwright_scraper = await self._get_playwright_scraper()
                        resolved = await self._resolve_ouo_links_batch(links_to_resolve, playwright_scraper)
                        download_links.extend(resolved)
                    except Exception as e:
                        logger.error(f"MegaComics: Playwright resolution failed: {e}")
                        for ouo_info in links_to_resolve:
                            host = ouo_info.get('detected_host', HostType.MEGA)
                            download_links.append(DownloadLink(
                                url=ouo_info['url'], host=host,
                                quality_score=self.get_quality_score(host),
                                file_size=file_size, link_status='shortener'
                            ))

                for uii_info in uii_links:
                    host = uii_info.get('detected_host', HostType.MEDIAFIRE)
                    download_links.append(DownloadLink(
                        url=uii_info['url'], host=host,
                        quality_score=40, file_size=file_size, link_status='needs_captcha'
                    ))

            # Deduplicate by URL
            seen_urls = set()
            unique_links = []
            for dl in download_links:
                if dl.url not in seen_urls:
                    seen_urls.add(dl.url)
                    unique_links.append(dl)
            download_links = unique_links

            # Parse issues from title
            title_info = parse_title(title)
            issues = None
            if title_info.range_start is not None and title_info.range_end is not None:
                issues = f"{title_info.range_start}/{title_info.range_end}"

            result = ComicScraperResult(
                title=title_clean,
                source=self.name,
                source_url=url,
                issue_number=issues,
                language="es",
                format="cbr",
                download_links=download_links,
                description=None,
                cover_image=cover,
                file_size=file_size,
                year=year,
                success=len(download_links) > 0,
                error=None if download_links else "No download links found"
            )

            logger.info(f"MegaComics scraped '{title_clean}': {len(download_links)} links found")
            return result

        except Exception as e:
            logger.error(f"MegaComics scrape error: {e}")
            return ComicScraperResult(
                title="Unknown",
                source=self.name,
                source_url=url,
                success=False,
                error=str(e)
            )

    async def _resolve_ouo_links_batch(
        self, ouo_links: List[Dict], playwright_scraper
    ) -> List[DownloadLink]:
        """Resolve multiple ouo.io links in parallel with concurrency limit."""
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
                host = ouo_info.get('detected_host', HostType.MEGA)
                logger.warning(
                    f"MegaComics: Could not resolve {ouo_info['url']}, "
                    f"keeping as {host.value}"
                )
                return DownloadLink(
                    url=ouo_info['url'],
                    host=host,
                    quality_score=self.get_quality_score(host),
                    link_status='shortener'
                )

        tasks = [resolve_one(ouo_info) for ouo_info in ouo_links]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, DownloadLink):
                resolved_links.append(result)
            elif isinstance(result, Exception):
                logger.error(f"MegaComics: Resolution task error: {result}")

        return resolved_links

    async def _resolve_ouo_with_playwright(
        self, ouo_url: str, playwright_scraper
    ) -> Optional[DownloadLink]:
        """
        Resolve a single ouo.io link using Playwright.
        2-step form bypass: Navigate → wait 6s → submit → wait 3s → submit → capture URL.
        """
        page = None
        try:
            page = await playwright_scraper._create_page()
            logger.info(f"MegaComics OUO: Resolving {ouo_url}")

            await page.goto(ouo_url, wait_until='domcontentloaded', timeout=15000)
            await asyncio.sleep(2)

            current_url = page.url

            # Check if already redirected past ouo.io
            if 'ouo.io' not in current_url and 'ouo.press' not in current_url:
                host = self.detect_host(current_url)
                logger.info(f"MegaComics OUO: Direct redirect to {host.value}: {current_url[:80]}")
                return DownloadLink(
                    url=current_url,
                    host=host,
                    quality_score=self.get_quality_score(host)
                )

            # 2-step form bypass
            for step in range(2):
                form = await page.query_selector('form#form-bypass')
                if not form:
                    form = await page.query_selector('form')

                if form:
                    await asyncio.sleep(6)

                    submit_btn = await page.query_selector(
                        'input[type="submit"], button[type="submit"], '
                        '#btn-main, .btn-main, a.btn'
                    )
                    if submit_btn:
                        try:
                            await submit_btn.click()
                            await asyncio.sleep(3)
                            try:
                                await page.wait_for_load_state('networkidle', timeout=10000)
                            except:
                                pass
                        except Exception as e:
                            logger.debug(f"MegaComics OUO: Click failed on step {step+1}: {e}")

                    current_url = page.url

                    if 'ouo.io' not in current_url and 'ouo.press' not in current_url:
                        host = self.detect_host(current_url)
                        logger.info(
                            f"MegaComics OUO: Resolved after step {step+1} "
                            f"to {host.value}: {current_url[:80]}"
                        )
                        return DownloadLink(
                            url=current_url,
                            host=host,
                            quality_score=self.get_quality_score(host)
                        )

            # Final check: look for download links in page HTML
            html_content = await page.content()
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
                    logger.info(f"MegaComics OUO: Found {host_type.value} in HTML: {resolved_url[:80]}")
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
                        logger.info(f"MegaComics OUO: Found {host.value} link: {href[:80]}")
                        return DownloadLink(
                            url=href,
                            host=host,
                            quality_score=self.get_quality_score(host)
                        )

            logger.warning(f"MegaComics OUO: Could not resolve {ouo_url}, final URL: {page.url[:80]}")
            return None

        except asyncio.TimeoutError:
            logger.warning(f"MegaComics OUO: Timeout resolving {ouo_url}")
            return None
        except Exception as e:
            logger.error(f"MegaComics OUO: Error resolving {ouo_url}: {e}")
            return None
        finally:
            if page:
                await page.close()

    def _parse_download_table(self, soup: BeautifulSoup) -> List[Dict]:
        """
        Parse the download table from MegaComics pages.
        Structure: <table> with rows like:
          <tr><td>#1 - #2</td><td>[MEGA link][MediaFire link]</td></tr>
          <tr><td>#3</td><td>[MEGA link][MediaFire link]</td></tr>

        Returns list of: [{"issue_label": "#1 - #2", "links": [{"url": ..., "detected_host": ...}]}]
        """
        rows = []

        # Find the download table (inside .secciones or .datagrid)
        table = soup.select_one('.secciones table, .datagrid table, table')
        if not table:
            return rows

        for tr in table.find_all('tr'):
            tds = tr.find_all('td')
            if len(tds) < 2:
                continue

            # First column: issue label (e.g. "#1 - #2", "#3")
            issue_label = tds[0].get_text(strip=True)
            if not issue_label or not re.search(r'#?\d', issue_label):
                continue

            # Second column: download links
            links = []
            for a in tds[1].find_all('a', href=True):
                href = a['href'].strip()
                if not href or href.startswith('#'):
                    continue

                # Detect host from img alt or link context
                img = a.find('img')
                img_alt = img.get('alt', '') if img else ''
                context = f"{a.get_text(strip=True)} {img_alt}".lower()
                detected_host = self._detect_host_from_context(context)

                links.append({
                    'url': href,
                    'detected_host': detected_host,
                    'context': context
                })

            if links:
                rows.append({
                    'issue_label': issue_label,
                    'links': links
                })
                logger.debug(f"MegaComics table row: {issue_label} -> {len(links)} links")

        return rows

    def _detect_host_from_context(self, context: str) -> HostType:
        """Detect the download host from surrounding text/image context."""
        ctx = context.lower()

        if 'mega' in ctx and 'mediafire' not in ctx:
            return HostType.MEGA
        elif 'mediafire' in ctx:
            return HostType.MEDIAFIRE
        elif 'google drive' in ctx or 'gdrive' in ctx or 'drive' in ctx:
            return HostType.GOOGLE_DRIVE
        elif 'fireload' in ctx:
            return HostType.FIRELOAD
        elif 'terabox' in ctx:
            return HostType.TERABOX

        return HostType.UNKNOWN

    def _get_headers(self) -> dict:
        """Get request headers"""
        return {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
            'Referer': self.base_url,
        }
