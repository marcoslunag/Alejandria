"""
Lectulandia.co EPUB Scraper
Scrapes books from lectulandia.co
"""

import aiohttp
import logging
from bs4 import BeautifulSoup
from typing import List, Dict
from .base import BookScraperBase, BookScraperResult

logger = logging.getLogger(__name__)


class LectulandiaScraper(BookScraperBase):
    """Scraper for lectulandia.co"""

    name = "lectulandia"
    base_url = "https://ww3.lectulandia.co"

    async def search(self, query: str, page: int = 1) -> List[Dict]:
        """Search for books on lectulandia.co using Playwright for better results"""
        try:
            # Import Playwright scraper
            from .playwright_scraper import get_playwright_scraper
            import asyncio

            logger.info(f"Lectulandia: Searching with Playwright for '{query}'")
            playwright_scraper = await get_playwright_scraper()

            # Use Playwright to get more complete results
            search_url = f"{self.base_url}/page/{page}/?s={query}"

            page_obj = await playwright_scraper._create_page()
            await page_obj.goto(search_url, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(2)  # Wait for JS to load

            # Get all book links
            book_links = await page_obj.query_selector_all('a[href*="/book/"]')
            logger.info(f"Found {len(book_links)} book links")

            results = []
            seen_urls = set()

            for idx, link in enumerate(book_links):
                try:
                    href = await link.get_attribute('href')
                    if not href or '/book/' not in href:
                        logger.debug(f"Link {idx}: Skipped - no href or '/book/' not in href")
                        continue

                    # Skip non-book links
                    if href == '/book/' or href.endswith('/autor/') or href.endswith('/serie/'):
                        logger.debug(f"Link {idx}: Skipped - non-book link ({href})")
                        continue

                    # Make URL absolute
                    url = href if href.startswith('http') else f"{self.base_url}{href}"

                    # Get title FIRST (before checking duplicates)
                    # Lectulandia has duplicate links: one without text (image link), one with text (title link)
                    # We want to keep the one WITH text, so we get title first and skip if empty
                    title = ''
                    try:
                        title = (await link.text_content()) or ''
                    except Exception as e:
                        logger.debug(f"Link {idx}: Error getting text_content: {e}")

                    title = title.strip()

                    # If no text, try to get from img alt attribute
                    if not title:
                        try:
                            img = await link.query_selector('img')
                            if img:
                                title = (await img.get_attribute('alt')) or ''
                                title = title.strip()
                        except Exception as e:
                            logger.debug(f"Link {idx}: Error getting img alt: {e}")

                    # Skip if no title (these are usually image links that will have a duplicate title link)
                    if not title:
                        logger.debug(f"Link {idx}: Skipped - no title found for URL: {url}")
                        continue

                    # NOW check for duplicates (after we know this link has a title)
                    if url in seen_urls:
                        logger.debug(f"Link {idx}: Skipped - duplicate URL ({url})")
                        continue
                    seen_urls.add(url)

                    # Get cover
                    img = await link.query_selector('img')
                    cover = await img.get_attribute('src') if img else None

                    logger.info(f"Link {idx}: Added - {title}")

                    results.append({
                        'title': title,
                        'url': url,
                        'cover': cover,
                        'source': self.name
                    })

                except Exception as e:
                    logger.debug(f"Link {idx}: Error parsing link: {e}")
                    continue

            await page_obj.close()
            logger.info(f"Lectulandia: Found {len(results)} unique results")
            return results

        except Exception as e:
            logger.error(f"Lectulandia Playwright search error: {e}")
            return []

    async def get_download_links(self, url: str) -> BookScraperResult:
        """Get download links from book page - uses Playwright to resolve JS-heavy pages"""
        try:
            # Import here to avoid circular dependency
            from .playwright_scraper import get_playwright_scraper

            # Use Playwright scraper for Lectulandia since it requires JS execution
            logger.info(f"Lectulandia: Using Playwright scraper for {url}")
            playwright_scraper = await get_playwright_scraper()
            result = await playwright_scraper.scrape_lectulandia(url)

            # If Playwright succeeded, return its result
            if result.success:
                return result

            # Fallback: Try basic scraping if Playwright fails
            logger.warning("Lectulandia: Playwright failed, trying fallback...")

            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    if response.status != 200:
                        return BookScraperResult(
                            title="Unknown", source=self.name, source_url=url,
                            success=False, error=f"HTTP {response.status}"
                        )
                    html = await response.text()

            soup = BeautifulSoup(html, 'html.parser')

            title_elem = soup.find('h1', class_='title')
            title = title_elem.get_text(strip=True) if title_elem else "Unknown"

            cover_elem = soup.find('div', class_='book-cover').find('img') if soup.find('div', class_='book-cover') else None
            cover = cover_elem.get('src') if cover_elem else None

            download_links = []

            # Look for direct download host links only (fallback mode)
            for link in soup.find_all('a', href=True):
                href = link.get('href', '').strip()

                if not href or href == '#':
                    continue

                if href.startswith('/'):
                    href = f"{self.base_url}{href}"

                # Only direct links
                if any(host in href.lower() for host in ['mega.nz', 'mega.io', 'mediafire.com', 'drive.google.com', 'terabox.com', '1fichier.com']):
                    dl_link = self.create_download_link(href)
                    download_links.append(dl_link)

            return BookScraperResult(
                title=title,
                source=self.name,
                source_url=url,
                cover_image=cover,
                download_links=download_links,
                success=len(download_links) > 0,
                error="Playwright failed, fallback used" if not download_links else None
            )

        except Exception as e:
            logger.error(f"Lectulandia scrape error: {e}")
            return BookScraperResult(
                title="Unknown", source=self.name, source_url=url,
                success=False, error=str(e)
            )
