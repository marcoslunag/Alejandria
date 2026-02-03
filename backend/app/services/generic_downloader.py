"""
Generic Downloader - Descarga de múltiples hosts usando Playwright
Soporta: Fireload, MediaFire, 1fichier, MEGA, Google Drive, etc.
"""

import asyncio
import logging
import re
from typing import Optional, Dict
from playwright.async_api import async_playwright, Browser, Page, TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)


class GenericDownloader:
    """
    Downloader genérico que usa Playwright para extraer enlaces directos
    de varios servicios de hosting
    """

    def __init__(self):
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
            logger.info("Generic downloader browser initialized")

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

    async def get_direct_link(self, url: str) -> Dict:
        """
        Obtiene el enlace de descarga directa de una URL

        Args:
            url: URL del archivo a descargar

        Returns:
            Dict con {ok, download_link, file_name, file_size} o error
        """
        url_lower = url.lower()

        # Determinar qué método usar según el host
        if 'fireload' in url_lower:
            return await self._download_fireload(url)
        elif 'mediafire' in url_lower:
            return await self._download_mediafire(url)
        elif '1fichier' in url_lower:
            return await self._download_1fichier(url)
        elif 'mega.nz' in url_lower or 'mega.co' in url_lower:
            return await self._download_mega(url)
        elif 'drive.google' in url_lower:
            return await self._download_gdrive(url)
        else:
            return {"ok": False, "error": f"Host no soportado: {url}"}

    async def _download_fireload(self, url: str) -> Dict:
        """Descarga de Fireload.com - Maneja countdowns y diferentes protecciones"""
        page = None
        try:
            page = await self._create_page()
            logger.info(f"Fireload: Accediendo a {url}")

            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            await asyncio.sleep(2)

            # Obtener nombre del archivo del título o de la página
            title = await page.title()
            file_name = title.split(' - ')[0].strip() if title else "unknown"

            # Intentar obtener nombre desde elemento específico
            try:
                name_elem = await page.query_selector('.file-name, h1, .filename')
                if name_elem:
                    name_text = await name_elem.inner_text()
                    if name_text and len(name_text) > 3:
                        file_name = name_text.strip()
            except:
                pass

            logger.info(f"Fireload: Archivo detectado: {file_name}")

            # Estrategia 1: Buscar enlace directo con /d/ inmediatamente
            direct_link = await self._fireload_find_direct_link(page)
            if direct_link:
                logger.info(f"Fireload: Enlace directo encontrado inmediatamente")
                return {
                    "ok": True,
                    "download_link": direct_link,
                    "file_name": file_name,
                    "file_size": "unknown"
                }

            # Estrategia 2: Esperar countdown si existe
            countdown_waited = await self._fireload_wait_countdown(page)
            if countdown_waited:
                logger.info(f"Fireload: Countdown completado, buscando enlace...")
                # Buscar enlace después del countdown
                direct_link = await self._fireload_find_direct_link(page)
                if direct_link:
                    return {
                        "ok": True,
                        "download_link": direct_link,
                        "file_name": file_name,
                        "file_size": "unknown"
                    }

            # Estrategia 3: Hacer clic en botones de descarga y capturar
            result = await self._fireload_click_and_capture(page, file_name)
            if result.get("ok"):
                return result

            # Estrategia 4: Buscar cualquier enlace útil en la página
            all_links = await page.query_selector_all('a')
            for link in all_links:
                try:
                    href = await link.get_attribute('href')
                    if href:
                        # Buscar enlaces de descarga directa
                        if '/d/' in href or '/download/' in href:
                            if href.startswith('/'):
                                href = f"https://www.fireload.com{href}"
                            if href.startswith('http'):
                                logger.info(f"Fireload: Enlace alternativo encontrado")
                                return {
                                    "ok": True,
                                    "download_link": href,
                                    "file_name": file_name,
                                    "file_size": "unknown"
                                }
                except:
                    continue

            # Debug: guardar HTML para diagnóstico
            try:
                html_content = await page.content()
                logger.debug(f"Fireload HTML (primeros 2000 chars): {html_content[:2000]}")
            except:
                pass

            return {"ok": False, "error": "No se encontró enlace de descarga en Fireload"}

        except Exception as e:
            logger.error(f"Fireload error: {e}")
            return {"ok": False, "error": str(e)}
        finally:
            if page:
                await page.close()

    async def _fireload_find_direct_link(self, page: Page) -> Optional[str]:
        """Busca enlace directo de descarga en Fireload"""
        selectors = [
            'a[href*="/d/"]',
            'a.download-btn[href*="/d/"]',
            '#download-btn a[href]',
            'a.btn-download[href]',
            '.download-link a[href]',
            'a[download]',
        ]

        for selector in selectors:
            try:
                elem = await page.query_selector(selector)
                if elem:
                    href = await elem.get_attribute('href')
                    if href:
                        if href.startswith('/'):
                            href = f"https://www.fireload.com{href}"
                        if href.startswith('http') and ('fireload' in href or '/d/' in href):
                            return href
            except:
                continue

        return None

    async def _fireload_wait_countdown(self, page: Page) -> bool:
        """Espera el countdown de Fireload si existe"""
        countdown_selectors = [
            '#countdown',
            '.countdown',
            '.timer',
            '#timer',
            '[id*="count"]',
            '[class*="count"]',
        ]

        countdown_found = False
        for selector in countdown_selectors:
            try:
                elem = await page.query_selector(selector)
                if elem:
                    countdown_found = True
                    logger.info(f"Fireload: Countdown detectado ({selector}), esperando...")
                    break
            except:
                continue

        if countdown_found:
            # Esperar hasta 30 segundos para que el countdown termine
            for i in range(30):
                await asyncio.sleep(1)

                # Verificar si apareció el botón de descarga
                download_btn = await page.query_selector('a[href*="/d/"]:not([style*="display: none"]), .download-ready a, #downloadButton:not([disabled])')
                if download_btn:
                    logger.info(f"Fireload: Botón de descarga disponible después de {i+1}s")
                    return True

                # Verificar si el countdown desapareció
                try:
                    for selector in countdown_selectors:
                        elem = await page.query_selector(selector)
                        if elem:
                            text = await elem.inner_text()
                            if text and text.strip() == '0':
                                logger.info(f"Fireload: Countdown llegó a 0")
                                await asyncio.sleep(1)
                                return True
                except:
                    pass

            logger.info(f"Fireload: Timeout esperando countdown")
            return True  # Retornar True de todas formas para intentar continuar

        return False

    async def _fireload_click_and_capture(self, page: Page, file_name: str) -> Dict:
        """Intenta hacer clic en botones y capturar la descarga"""
        click_selectors = [
            'a.download-btn',
            '#download-btn',
            '.download-button a',
            'a:has-text("Download")',
            'a:has-text("Descargar")',
            'button:has-text("Download")',
            'input[type="submit"][value*="Download"]',
            '.btn-success:has-text("Download")',
            'a.btn[href*="/d/"]',
        ]

        for selector in click_selectors:
            try:
                btn = await page.query_selector(selector)
                if btn:
                    # Verificar si está visible y habilitado
                    is_visible = await btn.is_visible()
                    if not is_visible:
                        continue

                    logger.info(f"Fireload: Intentando clic en {selector}")

                    # Opción 1: Intentar capturar descarga
                    try:
                        async with page.expect_download(timeout=30000) as download_info:
                            await btn.click()

                        download = await download_info.value
                        download_link = download.url
                        suggested_name = download.suggested_filename or file_name

                        logger.info(f"Fireload: Descarga capturada via clic - {suggested_name}")
                        return {
                            "ok": True,
                            "download_link": download_link,
                            "file_name": suggested_name,
                            "file_size": "unknown"
                        }
                    except PlaywrightTimeout:
                        # El clic no inició descarga directa, verificar si hay redirección
                        pass

                    # Opción 2: Verificar si el clic reveló un enlace
                    await asyncio.sleep(1)
                    direct_link = await self._fireload_find_direct_link(page)
                    if direct_link:
                        return {
                            "ok": True,
                            "download_link": direct_link,
                            "file_name": file_name,
                            "file_size": "unknown"
                        }

            except Exception as e:
                logger.debug(f"Fireload: Error con {selector}: {e}")
                continue

        return {"ok": False, "error": "No se pudo iniciar descarga"}

    async def _download_mediafire(self, url: str) -> Dict:
        """Descarga de MediaFire.com"""
        page = None
        try:
            page = await self._create_page()
            logger.info(f"MediaFire: Accediendo a {url}")

            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            await asyncio.sleep(2)

            # MediaFire tiene un botón de descarga con id específico
            download_btn = await page.wait_for_selector('#downloadButton, a.download_link, a[aria-label="Download"]', timeout=15000)

            if download_btn:
                download_link = await download_btn.get_attribute('href')

                # Obtener nombre del archivo
                file_name_elem = await page.query_selector('.filename, .dl-btn-label')
                file_name = await file_name_elem.inner_text() if file_name_elem else "unknown"

                # Obtener tamaño
                file_size_elem = await page.query_selector('.details li:first-child, .dl-info')
                file_size = await file_size_elem.inner_text() if file_size_elem else "unknown"

                if download_link:
                    logger.info(f"MediaFire: Enlace obtenido para {file_name}")
                    return {
                        "ok": True,
                        "download_link": download_link,
                        "file_name": file_name.strip(),
                        "file_size": file_size.strip()
                    }

            return {"ok": False, "error": "No se encontró botón de descarga en MediaFire"}

        except Exception as e:
            logger.error(f"MediaFire error: {e}")
            return {"ok": False, "error": str(e)}
        finally:
            if page:
                await page.close()

    async def _download_1fichier(self, url: str) -> Dict:
        """Descarga de 1fichier.com"""
        page = None
        try:
            page = await self._create_page()
            logger.info(f"1fichier: Accediendo a {url}")

            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            await asyncio.sleep(2)

            # Obtener info del archivo
            file_name_elem = await page.query_selector('.file_name, td.normal')
            file_name = await file_name_elem.inner_text() if file_name_elem else "unknown"

            # 1fichier puede mostrar un formulario para descargar
            # Primero, intentar encontrar el enlace directo
            download_link = None

            # Buscar botón de descarga
            download_btn = await page.query_selector('a.ok, input[type="submit"][value*="Download"], button:has-text("Download")')

            if download_btn:
                # Puede ser un formulario - hacer clic y esperar
                try:
                    async with page.expect_navigation(timeout=30000):
                        await download_btn.click()

                    # Después de la navegación, buscar el enlace final
                    final_link = await page.query_selector('a.ok[href*="1fichier"], a[href*="download"]')
                    if final_link:
                        download_link = await final_link.get_attribute('href')
                except:
                    pass

            if download_link:
                return {
                    "ok": True,
                    "download_link": download_link,
                    "file_name": file_name.strip(),
                    "file_size": "unknown"
                }
            else:
                return {"ok": False, "error": "1fichier requiere espera o captcha"}

        except Exception as e:
            logger.error(f"1fichier error: {e}")
            return {"ok": False, "error": str(e)}
        finally:
            if page:
                await page.close()

    async def _download_mega(self, url: str) -> Dict:
        """
        MEGA.nz - Los enlaces de MEGA requieren el cliente de MEGA o megatools
        Devolvemos el enlace original ya que MEGA tiene su propio sistema
        """
        logger.info(f"MEGA: Enlace detectado - {url}")
        # MEGA tiene encriptación end-to-end, no podemos obtener enlace directo
        # Se necesita megatools o megadl para descargar
        return {
            "ok": True,
            "download_link": url,  # El enlace original funciona con megatools
            "file_name": "mega_file",
            "file_size": "unknown",
            "requires_tool": "megatools"
        }

    async def _download_gdrive(self, url: str) -> Dict:
        """Descarga de Google Drive"""
        page = None
        try:
            page = await self._create_page()
            logger.info(f"GDrive: Accediendo a {url}")

            # Extraer ID del archivo
            file_id = None
            patterns = [
                r'/d/([a-zA-Z0-9_-]+)',
                r'id=([a-zA-Z0-9_-]+)',
            ]
            for pattern in patterns:
                match = re.search(pattern, url)
                if match:
                    file_id = match.group(1)
                    break

            if not file_id:
                return {"ok": False, "error": "No se pudo extraer ID de Google Drive"}

            # Construir enlace de descarga directa
            download_link = f"https://drive.google.com/uc?export=download&id={file_id}"

            await page.goto(url, wait_until='domcontentloaded', timeout=60000)

            # Obtener nombre del archivo
            file_name_elem = await page.query_selector('[data-target="doc-title"], .uc-name-size a')
            file_name = await file_name_elem.inner_text() if file_name_elem else "gdrive_file"

            # Verificar si hay advertencia de virus (archivos grandes)
            virus_warning = await page.query_selector('#uc-download-link, form#download-form')
            if virus_warning:
                # Archivo grande - necesita confirmación
                confirm_link = await page.query_selector('#uc-download-link')
                if confirm_link:
                    download_link = await confirm_link.get_attribute('href')
                    if download_link and not download_link.startswith('http'):
                        download_link = 'https://drive.google.com' + download_link

            return {
                "ok": True,
                "download_link": download_link,
                "file_name": file_name.strip() if isinstance(file_name, str) else "gdrive_file",
                "file_size": "unknown"
            }

        except Exception as e:
            logger.error(f"GDrive error: {e}")
            return {"ok": False, "error": str(e)}
        finally:
            if page:
                await page.close()


# Singleton
_downloader_instance: Optional[GenericDownloader] = None


async def get_generic_downloader() -> GenericDownloader:
    """Obtiene la instancia singleton del downloader genérico"""
    global _downloader_instance
    if _downloader_instance is None:
        _downloader_instance = GenericDownloader()
    return _downloader_instance


async def get_direct_download_link(url: str) -> Dict:
    """
    Función auxiliar para obtener enlace de descarga directa

    Args:
        url: URL del archivo

    Returns:
        Dict con resultado
    """
    downloader = await get_generic_downloader()
    return await downloader.get_direct_link(url)
