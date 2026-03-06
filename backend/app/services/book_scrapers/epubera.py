"""
Epubera.com EPUB Scraper
Scrapes books from epubera.com

Mecanismo de desbloqueo:
- La página tiene un formulario POST (action=misma URL) con <input id="epubera_pass">
- Al enviar el formulario con la contraseña "epubera.com", la página se recarga
  mostrando los enlaces de descarga directamente en el DOM.
- NO es AJAX — es un POST HTML clásico que recarga la página.
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

KNOWN_HOSTS = [
    "mega.nz", "mega.io", "mediafire.com", "drive.google.com",
    "terabox.com", "1024tera", "1fichier.com", "krakenfiles.com",
    "upload.ee", "megaup.net", "fireload.com", "send.now",
]


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

        Epubera usa un formulario POST clásico protegido con contraseña.
        Al enviar el formulario la página se recarga mostrando los links directamente.
        """
        page = None
        try:
            from .playwright_scraper import get_playwright_scraper

            playwright_scraper = await get_playwright_scraper()
            page = await playwright_scraper._create_page()

            logger.info(f"Epubera: Accessing {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(1)

            title_elem = await page.query_selector("h1, .entry-title")
            title = (await title_elem.inner_text()).strip() if title_elem else "Unknown"

            cover_elem = await page.query_selector("article img, .entry-content img")
            cover = await cover_elem.get_attribute("src") if cover_elem else None

            # Desbloquear enlaces: formulario con id="epubera_pass"
            password_input = await page.query_selector("#epubera_pass")
            if not password_input:
                # Fallback: cualquier input de contraseña que no sea de comentarios
                password_input = await page.query_selector(
                    'form:not([action*="wp-comments"]) input[type="password"]'
                )

            if password_input:
                logger.info("Epubera: Found password field, unlocking links...")
                await password_input.fill(EPUBERA_PASSWORD)

                # Obtener el botón submit del formulario correcto (no del de comentarios)
                submit_btn = await page.evaluate_handle(
                    'document.querySelector("#epubera_pass").closest("form").querySelector("button[type=submit], input[type=submit]")'
                )

                if submit_btn:
                    try:
                        # El form POST recarga la página — esperar navegación
                        async with page.expect_navigation(wait_until="domcontentloaded", timeout=20000):
                            await submit_btn.click()
                        logger.info("Epubera: Page reloaded after unlock")
                        await asyncio.sleep(1)
                    except Exception as nav_err:
                        logger.warning(f"Epubera: Navigation wait failed ({nav_err}), sleeping...")
                        await asyncio.sleep(3)
                else:
                    await password_input.press("Enter")
                    await asyncio.sleep(3)
            else:
                logger.info("Epubera: No password field found, scanning page directly")

            # Recoger links de descarga del DOM
            download_links = []
            all_a = await page.query_selector_all("a[href]")

            for link in all_a:
                try:
                    href = await link.get_attribute("href")
                    if not href or href == "#":
                        continue
                    if any(host in href.lower() for host in KNOWN_HOSTS):
                        if not any(existing.url == href for existing in download_links):
                            dl_link = self.create_download_link(href)
                            download_links.append(dl_link)
                            logger.info(f"Epubera: Found link -> {dl_link.host.value}: {href[:80]}")
                except Exception:
                    continue

            # Fallback: regex en HTML por si algún link está en texto/JS
            if not download_links:
                html_content = await page.content()
                for host in KNOWN_HOSTS:
                    pattern = rf'https?://(?:www\.)?{re.escape(host)}[^\s"\'<>]+'
                    for match in re.findall(pattern, html_content, re.IGNORECASE):
                        clean = match.rstrip("\"'")
                        if not any(existing.url == clean for existing in download_links):
                            dl_link = self.create_download_link(clean)
                            download_links.append(dl_link)
                            logger.info(f"Epubera: Found link in HTML -> {dl_link.host.value}: {clean[:80]}")

            logger.info(f"Epubera: Total links found: {len(download_links)}")
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
