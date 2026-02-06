"""
Playwright Book Scraper - Scraper con browser headless para sitios con JavaScript
Basado en generic_downloader.py pero enfocado en scraping de libros
"""

import asyncio
import logging
import re
from typing import Optional, List, Dict
from playwright.async_api import async_playwright, Browser, Page, TimeoutError as PlaywrightTimeout
from .base import BookScraperBase, BookScraperResult, DownloadLink, HostType

logger = logging.getLogger(__name__)


class PlaywrightBookScraper(BookScraperBase):
    """
    Scraper que usa Playwright para extraer información de libros
    desde sitios con JavaScript pesado
    """

    def __init__(self):
        super().__init__()
        self.browser: Optional[Browser] = None
        self._playwright = None

    async def _ensure_browser(self):
        """Inicializa el navegador si no está activo"""
        if self.browser is None:
            self._playwright = await async_playwright().start()
            self.browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-blink-features=AutomationControlled',
                ]
            )
            logger.info("Playwright book scraper browser initialized")

    async def _create_page(self) -> Page:
        """Crea una nueva página con configuración stealth"""
        await self._ensure_browser()
        context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        )
        page = await context.new_page()

        # Stealth básico
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = {runtime: {}};
        """)

        return page

    async def close(self):
        """Cierra el navegador"""
        if self.browser:
            await self.browser.close()
            self.browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def scrape_lectulandia(self, url: str) -> BookScraperResult:
        """
        Scrape Lectulandia.co usando Playwright para resolver los download.php links

        Args:
            url: URL del libro en Lectulandia

        Returns:
            BookScraperResult con links de descarga resueltos
        """
        page = None
        try:
            page = await self._create_page()
            logger.info(f"Lectulandia: Accediendo a {url}")

            await page.goto(url, wait_until='networkidle', timeout=60000)
            await asyncio.sleep(3)  # Extra wait for JS execution

            # Extraer título
            title_elem = await page.query_selector('h1.title, h1')
            title = await title_elem.inner_text() if title_elem else "Unknown"
            logger.info(f"Lectulandia: Title = {title}")

            # Extraer portada
            cover_elem = await page.query_selector('.book-cover img, article img')
            cover = await cover_elem.get_attribute('src') if cover_elem else None

            # Buscar enlaces de descarga (/download.php)
            download_links = []

            # Primero, buscar todos los enlaces en la página
            all_links = await page.query_selector_all('a[href]')
            logger.info(f"Lectulandia: Total links on page: {len(all_links)}")

            # Filtrar los que contienen download.php Y son EPUB (t=1)
            download_php_links = []
            for link in all_links:
                href = await link.get_attribute('href')
                if href and 'download.php' in href:
                    # Solo EPUB (t=1), no PDF (t=2)
                    if 't=1' in href or ('t=' not in href and 'download.php' in href):
                        download_php_links.append(link)
                        logger.info(f"Lectulandia: Found EPUB download.php link: {href}")
                    else:
                        logger.debug(f"Lectulandia: Skipping non-EPUB link: {href}")

            logger.info(f"Lectulandia: Found {len(download_php_links)} EPUB download.php links")

            for link in download_php_links[:10]:  # Limitar a 10 links
                try:
                    href = await link.get_attribute('href')
                    if not href:
                        continue

                    # Hacer absoluto si es relativo
                    if href.startswith('/'):
                        href = f"https://ww3.lectulandia.co{href}"

                    logger.info(f"Lectulandia: Resolviendo {href}")

                    # Navegar al link de download.php para resolver el redirect
                    resolved_url = await self._resolve_lectulandia_download(href)

                    if resolved_url:
                        # Identificar el host
                        host_type = self._identify_host_type(resolved_url)
                        if host_type != HostType.UNKNOWN:
                            dl_link = DownloadLink(
                                url=resolved_url,
                                host=host_type,
                                quality_score=self._get_host_quality(host_type)
                            )
                            download_links.append(dl_link)
                            logger.info(f"Lectulandia: Resuelto a {host_type.value}")

                except Exception as e:
                    logger.warning(f"Lectulandia: Error resolviendo link: {e}")
                    continue

            return BookScraperResult(
                title=title.strip(),
                source="lectulandia",
                source_url=url,
                cover_image=cover,
                download_links=download_links,
                success=len(download_links) > 0,
                error=None if download_links else "No se encontraron links de descarga"
            )

        except Exception as e:
            logger.error(f"Lectulandia scrape error: {e}")
            return BookScraperResult(
                title="Unknown",
                source="lectulandia",
                source_url=url,
                success=False,
                error=str(e)
            )
        finally:
            if page:
                await page.close()

    async def _resolve_lectulandia_download(self, download_php_url: str) -> Optional[str]:
        """
        Resuelve un link de download.php de Lectulandia al link real del file host

        Args:
            download_php_url: URL del download.php

        Returns:
            URL real del archivo o None
        """
        page = None
        try:
            page = await self._create_page()

            # Navegar al download.php
            logger.info(f"Navigating to {download_php_url}")
            await page.goto(download_php_url, wait_until='domcontentloaded', timeout=30000)

            # Lectulandia dice "En un momento seras redirigido"
            # Esperar hasta que la URL cambie (máximo 15 segundos)
            try:
                logger.info("Waiting for redirect...")
                await page.wait_for_url(lambda url: url != download_php_url, timeout=15000)
                logger.info(f"Redirect detected!")
            except:
                logger.warning("No redirect within timeout, checking current page...")

            current_url = page.url
            logger.info(f"Current URL after redirect: {current_url}")

            # Si la URL cambió, probablemente redirigió al file host
            if current_url != download_php_url:
                # Verificar si es un host directo conocido
                for host in ['mega.nz', 'mediafire.com', 'drive.google.com', 'terabox.com', '1fichier.com']:
                    if host in current_url.lower():
                        logger.info(f"Redirected to direct host {host}: {current_url}")
                        return current_url

                # Verificar si es un host intermedio (antupload, beeupload, etc.)
                intermediate_hosts = ['antupload.com', 'beeupload.net', 'beeupload.com']
                for host in intermediate_hosts:
                    if host in current_url.lower():
                        logger.info(f"Redirected to intermediate host {host}, resolving...")
                        # Intentar resolver el host intermedio
                        final_url = await self._resolve_intermediate_host(page, current_url)
                        if final_url:
                            return final_url
                        break

            # Buscar enlaces a hosts conocidos en la página
            all_links = await page.query_selector_all('a[href]')
            logger.info(f"Found {len(all_links)} links on download page")

            for link in all_links:
                href = await link.get_attribute('href')
                if href:
                    for host in ['mega.nz', 'mediafire.com', 'drive.google.com', 'terabox.com', '1fichier.com']:
                        if host in href.lower():
                            logger.info(f"Found {host} link in page: {href}")
                            return href

            # Buscar en el contenido JavaScript de la página
            html_content = await page.content()
            logger.info(f"HTML content length: {len(html_content)}")

            # Buscar patrones de URLs en el HTML/JS
            url_patterns = [
                r'https?://(?:www\.)?mega\.nz/[^\s"\'<>]+',
                r'https?://(?:www\.)?mediafire\.com/[^\s"\'<>]+',
                r'https?://drive\.google\.com/[^\s"\'<>]+',
                r'https?://(?:www\.)?terabox\.com/[^\s"\'<>]+',
                r'https?://1fichier\.com/[^\s"\'<>]+',
            ]

            for pattern in url_patterns:
                matches = re.findall(pattern, html_content)
                if matches:
                    logger.info(f"Found URL in HTML via regex: {matches[0]}")
                    # Retornar el primer match válido
                    return matches[0].rstrip('"\'')

            logger.warning(f"No download URL found in page for {download_php_url}")
            return None

        except Exception as e:
            logger.error(f"Error resolving download.php: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
        finally:
            if page:
                await page.close()

    async def _resolve_intermediate_host(self, page: Page, url: str) -> Optional[str]:
        """
        Resuelve un host intermedio (antupload, beeupload, etc.) al link final de descarga

        Args:
            page: Página de Playwright ya cargada en el host intermedio
            url: URL del host intermedio

        Returns:
            URL final de descarga o None
        """
        try:
            logger.info(f"Resolving intermediate host: {url}")

            # Esperar a que la página cargue completamente
            await asyncio.sleep(3)

            # Estrategia 0: Buscar el botón #downloadB específico de antupload/beeupload
            try:
                download_btn = await page.query_selector('#downloadB')
                if download_btn and await download_btn.is_visible():
                    href = await download_btn.get_attribute('href')
                    logger.info(f"Found #downloadB button with href: {href}")

                    # Intentar capturar la descarga directa
                    try:
                        logger.info("Attempting to capture download...")
                        async with page.expect_download(timeout=15000) as download_info:
                            await download_btn.click()

                        download = await download_info.value
                        download_url = download.url
                        filename = download.suggested_filename

                        logger.info(f"✅ Download captured! URL: {download_url}, file: {filename}")

                        # Cancelar la descarga (no queremos descargar ahora, solo obtener el URL)
                        await download.cancel()

                        # El download_url de antupload es válido - retornarlo
                        return download_url

                    except Exception as e:
                        logger.debug(f"Download capture failed: {e}")
                        # Si falla, intentar usar el href directamente
                        if href and href.startswith('/'):
                            full_href = f"{url.split('/')[0]}//{url.split('/')[2]}{href}"
                            logger.info(f"Using href as fallback: {full_href}")
                            return full_href

            except Exception as e:
                logger.debug(f"No #downloadB button found: {e}")

            # Estrategia 1: Buscar enlaces con texto de descarga
            download_texts = ['DOWNLOAD NOW', 'Download', 'Descargar', 'Download File', 'Free Download']

            for text in download_texts:
                try:
                    # Buscar enlaces con ese texto
                    all_links = await page.query_selector_all('a')
                    for link in all_links:
                        try:
                            link_text = await link.inner_text()
                            if not link_text or text.lower() not in link_text.lower():
                                continue

                            if not await link.is_visible():
                                continue

                            href = await link.get_attribute('href')
                            if not href or href == '#':
                                continue

                            logger.info(f"Found download link with text '{link_text}': {href}")

                            # Hacer href absoluto
                            if href.startswith('/'):
                                base = f"{url.split('/')[0]}//{url.split('/')[2]}"
                                href = f"{base}{href}"

                            # Si contiene /filed/ o /file/d/, navegar a esa página
                            if '/filed/' in href or '/file/d/' in href:
                                logger.info(f"Navigating to intermediate download page: {href}")

                                try:
                                    await page.goto(href, wait_until='networkidle', timeout=15000)
                                    await asyncio.sleep(3)

                                    new_url = page.url
                                    logger.info(f"After navigation, URL: {new_url}")

                                    # Verificar si navegó a un host conocido
                                    for host in ['mega.nz', 'mediafire.com', 'drive.google.com', 'terabox.com', '1fichier.com']:
                                        if host in new_url.lower():
                                            logger.info(f"Final URL is {host}")
                                            return new_url

                                    # Buscar links de descarga en la nueva página
                                    final_links = await page.query_selector_all('a[href]')
                                    for final_link in final_links:
                                        final_href = await final_link.get_attribute('href')
                                        if final_href:
                                            for host in ['mega.nz', 'mediafire.com', 'drive.google.com', 'terabox.com', '1fichier.com']:
                                                if host in final_href.lower():
                                                    logger.info(f"Found {host} link in final page: {final_href}")
                                                    return final_href

                                except Exception as e:
                                    logger.warning(f"Error navigating to {href}: {e}")
                                    continue

                            # Verificar si el href apunta directamente a un host conocido
                            for host in ['mega.nz', 'mediafire.com', 'drive.google.com', 'terabox.com', '1fichier.com']:
                                if host in href.lower():
                                    logger.info(f"Link points directly to {host}")
                                    return href

                        except Exception as e:
                            continue

                except Exception as e:
                    logger.debug(f"Error searching for text '{text}': {e}")
                    continue

            # Estrategia 2: Buscar enlaces directos en la página
            all_links = await page.query_selector_all('a[href]')
            logger.info(f"Found {len(all_links)} links on intermediate page")

            for link in all_links:
                try:
                    href = await link.get_attribute('href')
                    if href:
                        for host in ['mega.nz', 'mediafire.com', 'drive.google.com', 'terabox.com', '1fichier.com']:
                            if host in href.lower():
                                logger.info(f"Found {host} link: {href}")
                                return href
                except:
                    continue

            # Estrategia 3: Buscar en el HTML/JavaScript
            html_content = await page.content()
            url_patterns = [
                r'https?://(?:www\.)?mega\.nz/[^\s"\'<>]+',
                r'https?://(?:www\.)?mediafire\.com/[^\s"\'<>]+',
                r'https?://drive\.google\.com/[^\s"\'<>]+',
                r'https?://(?:www\.)?terabox\.com/[^\s"\'<>]+',
                r'https?://1fichier\.com/[^\s"\'<>]+',
            ]

            for pattern in url_patterns:
                matches = re.findall(pattern, html_content)
                if matches:
                    logger.info(f"Found URL in HTML: {matches[0]}")
                    return matches[0].rstrip('"\'')

            logger.warning(f"Could not resolve intermediate host: {url}")
            return None

        except Exception as e:
            logger.error(f"Error resolving intermediate host: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def _identify_host_type(self, url: str) -> HostType:
        """Identifica el tipo de host desde la URL"""
        url_lower = url.lower()

        if 'mega.nz' in url_lower or 'mega.io' in url_lower:
            return HostType.MEGA
        elif 'mediafire.com' in url_lower:
            return HostType.MEDIAFIRE
        elif 'drive.google.com' in url_lower:
            return HostType.GOOGLE_DRIVE
        elif 'terabox.com' in url_lower or '1024terabox.com' in url_lower:
            return HostType.TERABOX
        elif 'fireload.com' in url_lower:
            return HostType.FIRELOAD
        elif '1fichier.com' in url_lower:
            return HostType.ONEFICHIER
        elif 'antupload.com' in url_lower or 'beeupload' in url_lower:
            return HostType.ANTUPLOAD

        return HostType.UNKNOWN

    def _get_host_quality(self, host_type: HostType) -> int:
        """Retorna el quality score para un tipo de host"""
        quality_map = {
            HostType.MEDIAFIRE: 95,
            HostType.MEGA: 90,
            HostType.GOOGLE_DRIVE: 85,
            HostType.ANTUPLOAD: 80,  # Direct download, good quality
            HostType.FIRELOAD: 75,
            HostType.TERABOX: 60,
            HostType.ONEFICHIER: 50,
            HostType.UNKNOWN: 30,
        }
        return quality_map.get(host_type, 30)

    # Métodos requeridos por la clase base (no usados con Playwright)
    async def search(self, query: str, page: int = 1) -> List[Dict]:
        """No implementado - usar scrapers normales para búsqueda"""
        return []

    async def get_download_links(self, url: str) -> BookScraperResult:
        """Redirige al método específico de Lectulandia"""
        if 'lectulandia' in url.lower():
            return await self.scrape_lectulandia(url)
        else:
            return BookScraperResult(
                title="Unknown",
                source="unknown",
                source_url=url,
                success=False,
                error="URL no soportada por PlaywrightBookScraper"
            )


# Singleton
_playwright_scraper_instance: Optional[PlaywrightBookScraper] = None


async def get_playwright_scraper() -> PlaywrightBookScraper:
    """Obtiene la instancia singleton del scraper Playwright"""
    global _playwright_scraper_instance
    if _playwright_scraper_instance is None:
        _playwright_scraper_instance = PlaywrightBookScraper()
    return _playwright_scraper_instance
