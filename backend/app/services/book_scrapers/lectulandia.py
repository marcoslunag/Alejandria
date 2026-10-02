"""
Lectulandia.com EPUB Scraper
Scrapes books from lectulandia.com
"""

import aiohttp
import base64
import logging
import re
from urllib.parse import unquote
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from .base import BookScraperBase, BookScraperResult, DownloadLink, HostType

logger = logging.getLogger(__name__)


class LectulandiaScraper(BookScraperBase):
    """Scraper for lectulandia.com"""

    name = "lectulandia"
    base_url = "https://ww3.lectulandia.com"

    _BROWSER_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    }

    async def search(self, query: str, page: int = 1) -> List[Dict]:
        """Search for books on lectulandia.com using Playwright for better results"""
        try:
            # Import Playwright scraper
            from .playwright_scraper import get_playwright_scraper
            import asyncio

            logger.info(f"Lectulandia: Searching with Playwright for '{query}'")
            playwright_scraper = await get_playwright_scraper()

            # Use Playwright to get more complete results
            search_url = f"{self.base_url}/page/{page}/?s={query}"

            page_obj = await playwright_scraper._create_page()
            try:
                try:
                    await page_obj.goto(search_url, wait_until='domcontentloaded', timeout=30000)
                except Exception:
                    pass
                await asyncio.sleep(3)

                # Get all book links
                book_links = await page_obj.query_selector_all('a[href*="/book/"]')
                logger.info(f"Found {len(book_links)} book links")

                results = []
                seen_urls = set()

                for idx, link in enumerate(book_links):
                    try:
                        href = await link.get_attribute('href')
                        if not href or '/book/' not in href:
                            continue

                        if href == '/book/' or href.endswith('/autor/') or href.endswith('/serie/'):
                            continue

                        url = href if href.startswith('http') else f"{self.base_url}{href}"

                        title = ''
                        try:
                            title = (await link.text_content()) or ''
                        except Exception:
                            pass

                        title = title.strip()

                        if not title:
                            try:
                                img = await link.query_selector('img')
                                if img:
                                    title = (await img.get_attribute('alt')) or ''
                                    title = title.strip()
                            except Exception:
                                pass

                        if not title:
                            continue

                        if url in seen_urls:
                            continue
                        seen_urls.add(url)

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

                logger.info(f"Lectulandia: Found {len(results)} unique results")
                return results
            finally:
                await page_obj.close()

        except Exception as e:
            logger.error(f"Lectulandia Playwright search error: {e}")
            return []

    async def _resolve_download_links_http(self, url: str) -> Optional[BookScraperResult]:
        """
        Resuelve los links de Lectulandia en HTTP puro (sin browser).

        Cadena verificada (2026-10-01):
          1. La página del libro enlaza a /download.php?t=1&d=<base64> (t=1 EPUB, t=2 PDF).
          2. download.php YA NO redirige: devuelve 200 + JS (uCommon.js getBookLink)
             que tras ~11s redirige a https://www.antupload.com/file/<base64_decode(d)>.
             Playwright lo rompía: el reto Cloudflare recarga la página y destruye
             el contexto de ejecución.
          3. La página /file/<code> de antupload contiene <a id="downloadB"> con el
             link final; el scheduler ya descarga de antupload vía Playwright.

        Devuelve BookScraperResult si se resuelve, o None para degradar a Playwright.
        """
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(headers=self._BROWSER_HEADERS) as session:
                async with session.get(url, timeout=timeout) as response:
                    if response.status != 200:
                        logger.warning(f"Lectulandia HTTP: página del libro HTTP {response.status}")
                        return None
                    book_html = await response.text()

            soup = BeautifulSoup(book_html, 'html.parser')

            # Título: primer h1 con texto real (el h1.site-title está vacío)
            title = "Unknown"
            for h1 in soup.find_all('h1'):
                text = h1.get_text(strip=True)
                if text:
                    title = text
                    break

            # Portada: meta og:image (la página ya no usa div.book-cover)
            og_img = soup.find('meta', attrs={'property': 'og:image'})
            cover = og_img.get('content') if og_img else None

            # Buscar el link EPUB (t=1) de download.php con parámetro d=
            d_param = None
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                if 'download.php' not in href:
                    continue
                if 't=2' in href:  # Saltar PDF
                    continue
                match = re.search(r'[?&]d=([^&]+)', href)
                if match:
                    d_param = match.group(1)
                    break

            if not d_param:
                logger.warning("Lectulandia HTTP: no hay parámetro d= en download.php")
                return None

            # linkCode = base64_decode(d)  (uCommon.js getBookLink)
            try:
                link_code = base64.b64decode(unquote(d_param)).decode('utf-8', errors='ignore').strip()
            except Exception as e:
                logger.warning(f"Lectulandia HTTP: base64 inválido d={d_param!r}: {e}")
                return None

            if not link_code:
                logger.warning("Lectulandia HTTP: linkCode vacío tras decodificar")
                return None

            antupload_url = f"https://www.antupload.com/file/{link_code}"
            logger.info(f"Lectulandia HTTP: d={d_param} -> linkCode={link_code} -> {antupload_url}")

            # Validar que la página de antupload exista y tenga el botón de descarga
            try:
                async with aiohttp.ClientSession(headers=self._BROWSER_HEADERS) as ant_session:
                    async with ant_session.get(antupload_url, timeout=timeout) as response:
                        if response.status != 200:
                            logger.warning(f"Lectulandia HTTP: antupload HTTP {response.status}")
                            return None
                        ant_html = await response.text()
            except Exception as e:
                logger.warning(f"Lectulandia HTTP: fallo obteniendo antupload: {e}")
                return None

            ant_soup = BeautifulSoup(ant_html, 'html.parser')
            if not ant_soup.find('a', id='downloadB'):
                logger.warning(f"Lectulandia HTTP: antupload sin #downloadB: {antupload_url}")
                return None

            dl_link = DownloadLink(
                url=antupload_url,
                host=HostType.ANTUPLOAD,
                quality_score=80,  # Direct download, good quality (igual que PlaywrightBookScraper)
            )

            return BookScraperResult(
                title=title,
                source=self.name,
                source_url=url,
                cover_image=cover,
                download_links=[dl_link],
                success=True,
                error=None,
            )

        except Exception as e:
            logger.warning(f"Lectulandia HTTP: resolución fallida: {e}")
            return None

    async def get_download_links(self, url: str) -> BookScraperResult:
        """Get download links from book page - HTTP puro primero, Playwright como fallback"""
        try:
            # 1) Intentar resolución HTTP pura (rápida, sin browser, inmune al reto Cloudflare)
            http_result = await self._resolve_download_links_http(url)
            if http_result is not None:
                logger.info(f"Lectulandia: resuelto por HTTP puro: {http_result.best_link.url if http_result.best_link else 'sin links'}")
                return http_result

            # 2) Fallback: Playwright (páginas con JS)
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
