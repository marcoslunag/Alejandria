"""
Epubera.com EPUB Scraper
Scrapes books from epubera.com
Password-protected links use the fixed password "epubera.com"
"""

import aiohttp
import asyncio
import logging
import re
from bs4 import BeautifulSoup
from typing import List, Dict
from .base import BookScraperBase, BookScraperResult, DownloadLink

logger = logging.getLogger(__name__)

EPUBERA_PASSWORD = "epubera.com"


class EpuberaScraper(BookScraperBase):
    """Scraper for epubera.com"""

    name = "epubera"
    base_url = "https://epubera.com"

    async def search(self, query: str, page: int = 1) -> List[Dict]:
        """Search for books on epubera.com"""
        try:
            search_url = f"{self.base_url}/page/{page}/" if page > 1 else self.base_url
            params = {"s": query}

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }

            logger.info(f"Epubera: Searching for '{query}' at {search_url}")
            async with aiohttp.ClientSession() as session:
                async with session.get(search_url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=25), allow_redirects=True) as response:
                    if response.status != 200:
                        logger.warning(f"Epubera search returned {response.status} for '{query}'")
                        return []
                    html = await response.text()
                    logger.info(f"Epubera: Got {len(html)} chars response")

            soup = BeautifulSoup(html, "html.parser")
            results = []
            seen_urls = set()

            articles = soup.select("article")
            if not articles:
                articles = soup.select(".post, .entry, .book-item")

            for article in articles:
                try:
                    title_elem = article.select_one("h2 a, h3 a, .entry-title a")
                    if not title_elem:
                        continue

                    title = title_elem.get_text(strip=True)
                    url = title_elem.get("href", "")

                    if not url or not title:
                        continue
                    if url in seen_urls:
                        continue
                    if not url.startswith("http"):
                        url = f"{self.base_url}{url}"

                    seen_urls.add(url)

                    cover = None
                    img = article.select_one("img")
                    if img:
                        cover = img.get("src") or img.get("data-src") or img.get("data-lazy-src")

                    # Extract author from title pattern "Title | Author"
                    author = None
                    if " | " in title:
                        parts = title.rsplit(" | ", 1)
                        title = parts[0].strip()
                        author = parts[1].strip()

                    results.append({
                        "title": title,
                        "url": url,
                        "cover": cover,
                        "author": author,
                        "source": self.name,
                    })
                except Exception as e:
                    logger.debug(f"Epubera: Error parsing article: {e}")
                    continue

            logger.info(f"Epubera: Found {len(results)} results for '{query}'")
            return results

        except asyncio.TimeoutError:
            logger.warning("Epubera search timed out")
            return []
        except Exception as e:
            logger.error(f"Epubera search error: {e}")
            return []

    async def get_download_links(self, url: str) -> BookScraperResult:
        """
        Get download links from an epubera.com book page.
        Uses Playwright to unlock password-protected links.
        """
        page = None
        try:
            from .playwright_scraper import get_playwright_scraper

            playwright_scraper = await get_playwright_scraper()
            page = await playwright_scraper._create_page()

            logger.info(f"Epubera: Accessing {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)

            title_elem = await page.query_selector("h1, .entry-title")
            title = (await title_elem.inner_text()).strip() if title_elem else "Unknown"

            cover_elem = await page.query_selector("article img, .entry-content img")
            cover = await cover_elem.get_attribute("src") if cover_elem else None

            # Unlock password-protected links
            password_input = await page.query_selector('input[type="password"]')
            if password_input:
                logger.info("Epubera: Found password field, unlocking links...")
                await password_input.fill(EPUBERA_PASSWORD)

                submit_btn = await page.query_selector(
                    'input[type="submit"], button[type="submit"], '
                    'button:has-text("Desbloquear"), button:has-text("OK"), '
                    'input[value*="Desbloquear"], input[value*="desbloquear"]'
                )
                if submit_btn:
                    await submit_btn.click()
                    await asyncio.sleep(2)
                else:
                    await password_input.press("Enter")
                    await asyncio.sleep(2)

            # Collect download links
            download_links = []
            all_links = await page.query_selector_all("a[href]")

            known_hosts = [
                "mega.nz", "mega.io", "mediafire.com", "drive.google.com",
                "terabox.com", "1024tera", "1fichier.com", "krakenfiles.com",
                "upload.ee", "megaup.net", "fireload.com",
            ]

            for link in all_links:
                try:
                    href = await link.get_attribute("href")
                    if not href or href == "#":
                        continue
                    href_lower = href.lower()
                    if any(host in href_lower for host in known_hosts):
                        dl_link = self.create_download_link(href)
                        if not any(existing.url == href for existing in download_links):
                            download_links.append(dl_link)
                            logger.info(f"Epubera: Found link -> {dl_link.host.value}: {href[:80]}")
                except Exception:
                    continue

            # Also scan raw HTML for links that JS might have injected
            if not download_links:
                html_content = await page.content()
                for host in known_hosts:
                    pattern = rf'https?://(?:www\.)?{re.escape(host)}[^\s"\'<>]+'
                    matches = re.findall(pattern, html_content, re.IGNORECASE)
                    for match in matches:
                        clean = match.rstrip("\"'")
                        if not any(existing.url == clean for existing in download_links):
                            dl_link = self.create_download_link(clean)
                            download_links.append(dl_link)
                            logger.info(f"Epubera: Found link in HTML -> {dl_link.host.value}")

            return BookScraperResult(
                title=title,
                source=self.name,
                source_url=url,
                cover_image=cover,
                download_links=download_links,
                success=len(download_links) > 0,
                error=None if download_links else "No download links found",
            )

        except Exception as e:
            logger.error(f"Epubera scrape error: {e}")
            return BookScraperResult(
                title="Unknown",
                source=self.name,
                source_url=url,
                success=False,
                error=str(e),
            )
        finally:
            if page:
                await page.close()
