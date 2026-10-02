"""
Libronera EPUB Scraper (antes Epubera.com)
Scrapes books from libronera.com — el sitio cambió de dominio epubera.com →
libronera.com (verificado 2026-10-02). Se mantiene el nombre interno "epubera"
por consistencia con la DB (source='epubera') y el frontend.

Mecanismo de desbloqueo (2026-10-02):
- La página tiene un formulario POST (action=misma URL) con <input id="epubera_pass">
- La contraseña se muestra en la propia página: <p class="dl-pass">Contraseña:
  <strong>libronera.com</strong></p> — se lee dinámicamente, con fallback al
  constante EPUBERA_PASSWORD.
- IMPORTANTE: el formulario incluye un nonce por página (<input id="epubera_unlock_nonce">)
  que el navegador POSTea automáticamente al enviar el form. Por eso el flujo
  Playwright (fill + click submit) funciona sin extraer el nonce a mano; un POST
  HTTP plano SÍ necesita leerlo del DOM primero.
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

# Fallback — la contraseña real se lee de la página (p.dl-pass strong).
# 2026-10-02: cambió de "epubera.com" a "libronera.com" con el rename.
EPUBERA_PASSWORD = "libronera.com"

KNOWN_HOSTS = [
    "mega.nz", "mega.io", "mediafire.com", "drive.google.com",
    "terabox.com", "1024tera", "1fichier.com", "krakenfiles.com",
    "upload.ee", "megaup.net", "fireload.com", "send.now",
]


class EpuberaScraper(BookScraperBase):
    """Scraper for epubera.com"""

    name = "epubera"
    # 2026-10-02: el sitio se renombró de epubera.com a libronera.com
    # (epubera.com 301 → epubera1.com caído). Nuevo dominio verificado:
    # HTTP 200 con User-Agent de navegador (Cloudflare bloquea curl sin UA).
    base_url = "https://libronera.com"
    ENABLED = True

    async def search(self, query: str, page: int = 1) -> List[Dict]:
        """Search for books on libronera.com (antes epubera.com)"""
        if not self.ENABLED:
            logger.info("Epubera/Libronera desactivado; omitiendo búsqueda")
            return []
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
        if not self.ENABLED:
            return BookScraperResult(
                title="Unknown",
                source=self.name,
                source_url=url,
                success=False,
                error="Epubera/Libronera desactivado (ENABLED=False en epubera.py)",
            )
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
                # La contraseña se muestra en la página (p.dl-pass strong) —
                # leerla dinámicamente por si la cambian; fallback al constante.
                password = EPUBERA_PASSWORD
                try:
                    pass_elem = await page.query_selector("p.dl-pass strong")
                    if pass_elem:
                        dyn = (await pass_elem.inner_text()).strip()
                        if dyn:
                            password = dyn
                            logger.info(f"Epubera: password from page: {password}")
                except Exception:
                    pass
                await password_input.fill(password)

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
