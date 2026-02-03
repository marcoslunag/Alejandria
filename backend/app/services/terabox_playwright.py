"""
TeraBox Playwright Service - Versión Mejorada
Descarga de TeraBox usando navegador headless con autenticación persistente
Basado en arquitectura de microservicio con sesión persistente
"""

import asyncio
import logging
import re
import os
from pathlib import Path
from typing import Optional, Dict, Callable
from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeout,
    Download
)

logger = logging.getLogger(__name__)

# Directorio de descargas temporal para Playwright
PLAYWRIGHT_DOWNLOAD_DIR = Path(os.getenv('DOWNLOAD_DIR', '/downloads'))

# Argumentos optimizados para Chromium en producción/containers
CHROMIUM_ARGS = [
    '--disable-blink-features=AutomationControlled',
    '--disable-web-security',
    '--disable-features=IsolateOrigins,site-per-process',
    '--disable-site-isolation-trials',
    '--disable-dev-shm-usage',
    '--no-sandbox',
    '--disable-setuid-sandbox',
    '--disable-gpu',
    '--disable-software-rasterizer',
    '--disable-extensions',
    '--disable-default-apps',
    '--no-first-run',
    '--no-zygote',
    '--single-process',
    '--window-size=1920,1080',
]

# Scripts de evasión de detección
STEALTH_SCRIPTS = """
// Ocultar navigator.webdriver
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined
});

// Simular plugins de navegador realista
Object.defineProperty(navigator, 'plugins', {
    get: () => [
        {name: "Chrome PDF Plugin"},
        {name: "Chrome PDF Viewer"},
        {name: "Native Client"},
        {name: "Widevine Content Decryption Module"}
    ]
});

// Simular languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en', 'es-ES', 'es']
});

// Ocultar Chrome Runtime
if (window.chrome) {
    window.chrome.runtime = undefined;
}

// Simular permisos de notificación
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
);

// Canvas fingerprinting protection
const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
HTMLCanvasElement.prototype.toDataURL = function(type) {
    return originalToDataURL.apply(this, arguments);
};

// WebGL fingerprinting protection
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    // Algunos parámetros pueden revelar fingerprint
    if (parameter === 37445) {
        return 'Intel Inc.';
    }
    if (parameter === 37446) {
        return 'Intel Iris OpenGL Engine';
    }
    return getParameter.apply(this, arguments);
};
"""


class TeraBoxPlaywright:
    """
    Servicio mejorado para descargar de TeraBox usando Playwright
    con autenticación persistente y manejo nativo de descargas.
    """

    def __init__(self):
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self._playwright = None
        self._session_manager = None

    async def _get_session_manager(self):
        """Obtiene el gestor de sesiones."""
        if self._session_manager is None:
            from app.services.terabox_session import get_session_manager
            self._session_manager = get_session_manager()
        return self._session_manager

    async def _ensure_browser(self):
        """Inicializa el navegador con contexto autenticado si disponible."""
        if self.browser is None:
            self._playwright = await async_playwright().start()
            self.browser = await self._playwright.chromium.launch(
                headless=True,
                args=CHROMIUM_ARGS
            )
            logger.info("Playwright browser initialized")

        if self.context is None:
            # Preparar opciones de contexto
            context_options = {
                'accept_downloads': True,
                'viewport': {'width': 1920, 'height': 1080},
                'screen': {'width': 1920, 'height': 1080},
                'user_agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/120.0.0.0 Safari/537.36'
                ),
                'locale': 'en-US',
                'timezone_id': 'America/New_York',
                'color_scheme': 'light',
            }

            # Cargar estado de autenticación si existe
            session_mgr = await self._get_session_manager()
            if session_mgr.has_valid_session():
                auth_path = session_mgr.get_auth_state_path()
                context_options['storage_state'] = str(auth_path)
                logger.info(f"Loading auth state from: {auth_path}")

            self.context = await self.browser.new_context(**context_options)

            # Configurar timeouts
            self.context.set_default_timeout(60000)
            self.context.set_default_navigation_timeout(30000)

            # Inyectar scripts de evasión
            await self.context.add_init_script(STEALTH_SCRIPTS)

            # Intentar aplicar playwright-stealth si está disponible
            try:
                from playwright_stealth import stealth_async
                # stealth_async se aplica a páginas, no contextos
                logger.debug("playwright-stealth available for pages")
            except ImportError:
                logger.debug("playwright-stealth not installed, using basic stealth")

    async def _create_page(self) -> Page:
        """Crea una nueva página con stealth mode."""
        await self._ensure_browser()

        page = await self.context.new_page()

        # Aplicar stealth a la página si está disponible
        try:
            from playwright_stealth import stealth_async
            await stealth_async(page)
            logger.debug("Stealth mode applied to page")
        except ImportError:
            pass

        # Manejadores de eventos para debugging
        page.on("console", lambda msg: logger.debug(f"Console [{msg.type}]: {msg.text}") if msg.type == 'error' else None)
        page.on("pageerror", lambda err: logger.warning(f"Page error: {err}"))

        return page

    async def close(self):
        """Cierra el navegador y guarda estado de sesión."""
        try:
            # Guardar estado de sesión antes de cerrar
            if self.context:
                session_mgr = await self._get_session_manager()
                try:
                    storage_state = await self.context.storage_state()
                    session_mgr.save_auth_state(storage_state, source="auto_save")
                    logger.info("Session state saved on close")
                except Exception as e:
                    logger.warning(f"Could not save session state: {e}")

                await self.context.close()
                self.context = None

            if self.browser:
                await self.browser.close()
                self.browser = None

            if self._playwright:
                await self._playwright.stop()
                self._playwright = None

            logger.info("Playwright browser closed")

        except Exception as e:
            logger.error(f"Error closing browser: {e}")

    def _normalize_terabox_url(self, url: str) -> str:
        """Normaliza la URL de TeraBox al formato correcto."""
        # Extraer el surl/código de compartición
        match = re.search(r'(?:/s/1?|surl=)([a-zA-Z0-9_-]+)', url)
        if match:
            surl = match.group(1)
            return f"https://www.terabox.com/sharing/link?surl={surl}"
        return url

    async def _check_auth_status(self, page: Page) -> bool:
        """
        Verifica si la sesión está autenticada en la página actual.

        Returns:
            True si hay sesión activa
        """
        try:
            # Indicadores de sesión activa (usuario logueado)
            auth_indicators = [
                '.user-avatar',
                '.user-name',
                '[class*="user-info"]',
                '[class*="account"]',
            ]

            for selector in auth_indicators:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        logger.debug(f"Auth indicator found: {selector}")
                        return True
                except:
                    continue

            # Verificar si hay botón de login visible (indica NO autenticado)
            login_indicators = [
                'button:has-text("Log in")',
                'button:has-text("Sign in")',
                'a:has-text("Log in")',
            ]

            for selector in login_indicators:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        logger.debug("Login button visible - not authenticated")
                        return False
                except:
                    continue

            # Si no encontramos indicadores claros, asumimos OK
            return True

        except Exception as e:
            logger.warning(f"Error checking auth status: {e}")
            return True  # Asumir OK en caso de error

    async def download_file(
        self,
        terabox_url: str,
        output_path: Path,
        on_progress: Optional[Callable[[int, int], None]] = None,
        timeout: int = 300000
    ) -> Dict:
        """
        Descarga un archivo de TeraBox directamente usando Playwright.

        Este método navega a TeraBox, hace clic en el botón de descarga,
        e intercepta la descarga usando la API nativa de Playwright.

        Args:
            terabox_url: URL de compartición de TeraBox
            output_path: Path donde guardar el archivo
            on_progress: Callback opcional para progreso
            timeout: Timeout en ms

        Returns:
            Dict con {ok, file_path, file_name, file_size} o error
        """
        page = None
        try:
            page = await self._create_page()

            # Normalizar URL
            normalized_url = self._normalize_terabox_url(terabox_url)
            logger.info(f"Navigating to TeraBox: {normalized_url}")

            # Navegar a TeraBox
            response = await page.goto(normalized_url, wait_until='networkidle', timeout=60000)

            if not response or response.status >= 400:
                return {"ok": False, "error": f"HTTP error: {response.status if response else 'No response'}"}

            # Esperar a que la página cargue completamente
            await asyncio.sleep(2)

            # Verificar estado de autenticación
            is_authed = await self._check_auth_status(page)
            if not is_authed:
                logger.warning("Not authenticated - download may fail or be limited")

            # Verificar si hay CAPTCHA o verificación
            page_content = await page.content()
            if 'captcha' in page_content.lower():
                logger.warning("CAPTCHA detected - may require manual intervention")
                # Esperar un poco más por si se resuelve
                await asyncio.sleep(5)

            # Buscar información del archivo
            file_name = "unknown"
            file_size = "unknown"

            try:
                # Selectores para nombre de archivo
                name_selectors = [
                    '.file-name',
                    '.filename',
                    '[class*="file-name"]',
                    '[class*="fileName"]',
                    '.file-info-name',
                ]
                for selector in name_selectors:
                    elem = await page.query_selector(selector)
                    if elem:
                        file_name = await elem.inner_text()
                        file_name = file_name.strip()
                        break

                # Selectores para tamaño
                size_selectors = [
                    '.file-size',
                    '.filesize',
                    '[class*="file-size"]',
                    '[class*="fileSize"]',
                ]
                for selector in size_selectors:
                    elem = await page.query_selector(selector)
                    if elem:
                        file_size = await elem.inner_text()
                        file_size = file_size.strip()
                        break

                logger.info(f"Found file: {file_name} ({file_size})")

            except Exception as e:
                logger.warning(f"Could not extract file info: {e}")

            # Buscar y hacer clic en el botón de descarga
            download_selectors = [
                '.action-bar-download',
                'div.action-bar-download',
                '[class*="action-bar-download"]',
                '[class*="download-btn"]',
                'button:has-text("Download")',
                'a:has-text("Download")',
                '.download-btn',
                '.btn-download',
                '[data-type="download"]',
            ]

            download_button = None
            for selector in download_selectors:
                try:
                    download_button = await page.wait_for_selector(selector, timeout=5000)
                    if download_button:
                        is_visible = await download_button.is_visible()
                        if is_visible:
                            logger.info(f"Found download button: {selector}")
                            break
                        download_button = None
                except PlaywrightTimeout:
                    continue

            if not download_button:
                # Intentar método alternativo: buscar enlace directo
                logger.warning("Download button not found, trying alternative methods...")

                # Buscar enlaces que parezcan de descarga
                links = await page.query_selector_all('a[href]')
                for link in links:
                    href = await link.get_attribute('href')
                    if href and any(x in href.lower() for x in ['download', 'd.terabox', 'nduserdata']):
                        # Encontramos un enlace de descarga directa
                        logger.info(f"Found direct download link: {href[:80]}...")
                        return {
                            "ok": True,
                            "download_link": href,
                            "file_name": file_name,
                            "file_size": file_size,
                            "method": "direct_link"
                        }

                return {"ok": False, "error": "Download button not found"}

            # Usar expect_download para capturar la descarga
            logger.info("Clicking download button and waiting for download...")

            try:
                async with page.expect_download(timeout=timeout) as download_info:
                    await download_button.click()

                download: Download = await download_info.value

                # Obtener información de la descarga
                suggested_filename = download.suggested_filename
                logger.info(f"Download started: {suggested_filename}")

                # Guardar el archivo
                output_path.parent.mkdir(parents=True, exist_ok=True)
                await download.save_as(str(output_path))

                # Verificar que se guardó
                if output_path.exists():
                    actual_size = output_path.stat().st_size
                    logger.info(f"Download completed: {output_path} ({actual_size} bytes)")

                    return {
                        "ok": True,
                        "file_path": str(output_path),
                        "file_name": suggested_filename or file_name,
                        "file_size": actual_size,
                        "method": "native_download"
                    }
                else:
                    return {"ok": False, "error": "File not saved after download"}

            except PlaywrightTimeout:
                # Si no hubo descarga, puede que haya abierto popup
                logger.warning("Download timeout - checking for popup or new tab...")

                # Verificar si hay páginas nuevas
                pages = self.context.pages
                if len(pages) > 1:
                    new_page = pages[-1]
                    download_url = new_page.url
                    await new_page.close()

                    if 'download' in download_url.lower() or 'd.terabox' in download_url.lower():
                        return {
                            "ok": True,
                            "download_link": download_url,
                            "file_name": file_name,
                            "file_size": file_size,
                            "method": "popup_url"
                        }

                return {"ok": False, "error": "Download did not start within timeout"}

        except PlaywrightTimeout as e:
            logger.error(f"Timeout error: {e}")
            return {"ok": False, "error": f"Timeout: {str(e)}"}
        except Exception as e:
            logger.error(f"Error downloading from TeraBox: {e}")
            return {"ok": False, "error": str(e)}
        finally:
            if page:
                try:
                    await page.close()
                except:
                    pass

    async def get_direct_link(self, terabox_url: str, timeout: int = 120000) -> Dict:
        """
        Obtiene el enlace de descarga directa de TeraBox.

        Este método intenta obtener el enlace sin descargar el archivo,
        útil cuando queremos el enlace para descargar con otra herramienta.

        Args:
            terabox_url: URL de compartición de TeraBox
            timeout: Timeout en ms

        Returns:
            Dict con {ok, download_link, file_name, file_size} o error
        """
        page = None
        try:
            page = await self._create_page()

            normalized_url = self._normalize_terabox_url(terabox_url)
            logger.info(f"Getting direct link from: {normalized_url}")

            # Interceptar respuestas que contengan enlaces de descarga
            download_link = None

            async def handle_response(response):
                nonlocal download_link
                url = response.url
                # Los enlaces de descarga de TeraBox contienen estas cadenas
                if any(x in url.lower() for x in ['nduserdata', 'd.terabox', '/file/', 'download']):
                    if response.status in [200, 302, 301]:
                        content_type = response.headers.get('content-type', '')
                        # Evitar capturar HTML o JSON
                        if 'text/html' not in content_type and 'application/json' not in content_type:
                            download_link = url
                            logger.info(f"Intercepted download URL: {url[:80]}...")

            page.on('response', handle_response)

            # Navegar a la página
            await page.goto(normalized_url, wait_until='networkidle', timeout=60000)
            await asyncio.sleep(2)

            # Extraer info del archivo
            file_name = "unknown"
            file_size = "unknown"

            try:
                for selector in ['.file-name', '.filename', '[class*="file-name"]']:
                    elem = await page.query_selector(selector)
                    if elem:
                        file_name = (await elem.inner_text()).strip()
                        break

                for selector in ['.file-size', '.filesize', '[class*="file-size"]']:
                    elem = await page.query_selector(selector)
                    if elem:
                        file_size = (await elem.inner_text()).strip()
                        break
            except:
                pass

            # Si ya capturamos un enlace, retornarlo
            if download_link:
                return {
                    "ok": True,
                    "download_link": download_link,
                    "file_name": file_name,
                    "file_size": file_size
                }

            # Buscar botón de descarga
            download_selectors = [
                '.action-bar-download',
                'div.action-bar-download',
                '[class*="action-bar-download"]',
                'button:has-text("Download")',
                'a:has-text("Download")',
            ]

            download_button = None
            for selector in download_selectors:
                try:
                    download_button = await page.wait_for_selector(selector, timeout=5000)
                    if download_button:
                        break
                except PlaywrightTimeout:
                    continue

            if download_button:
                # Hacer clic y esperar a que se intercepte el enlace
                try:
                    async with page.expect_popup(timeout=15000) as popup_info:
                        await download_button.click()
                    popup = await popup_info.value
                    download_link = popup.url
                    await popup.close()
                except PlaywrightTimeout:
                    # No hubo popup, revisar si capturamos algo
                    await download_button.click()
                    await asyncio.sleep(3)

            if download_link:
                return {
                    "ok": True,
                    "download_link": download_link,
                    "file_name": file_name,
                    "file_size": file_size
                }

            # Buscar enlaces en el DOM como último recurso
            links = await page.query_selector_all('a[href*="download"], a[href*="d.terabox"]')
            for link in links:
                href = await link.get_attribute('href')
                if href:
                    return {
                        "ok": True,
                        "download_link": href,
                        "file_name": file_name,
                        "file_size": file_size
                    }

            return {"ok": False, "error": "Could not get download link"}

        except Exception as e:
            logger.error(f"Error getting direct link: {e}")
            return {"ok": False, "error": str(e)}
        finally:
            if page:
                try:
                    await page.close()
                except:
                    pass

    # Alias para compatibilidad
    async def get_direct_link_from_terabox(self, terabox_url: str, timeout: int = 120000) -> Dict:
        """Alias para get_direct_link (compatibilidad)."""
        return await self.get_direct_link(terabox_url, timeout)

    async def get_direct_link_simple(self, terabox_url: str, timeout: int = 120000) -> Dict:
        """Alias para get_direct_link (compatibilidad)."""
        return await self.get_direct_link(terabox_url, timeout)


# Singleton instance
_playwright_instance: Optional[TeraBoxPlaywright] = None


async def get_playwright_instance() -> TeraBoxPlaywright:
    """Obtiene o crea la instancia singleton de TeraBoxPlaywright."""
    global _playwright_instance
    if _playwright_instance is None:
        _playwright_instance = TeraBoxPlaywright()
    return _playwright_instance


async def get_terabox_link_playwright(url: str) -> Optional[str]:
    """
    Función auxiliar para obtener enlace directo de TeraBox.

    Args:
        url: URL de TeraBox

    Returns:
        URL de descarga directa o None
    """
    try:
        instance = await get_playwright_instance()
        result = await instance.get_direct_link(url)

        if result.get("ok"):
            return result.get("download_link")

        logger.error(f"TeraBox error: {result.get('error')}")
        return None
    except Exception as e:
        logger.error(f"Error in get_terabox_link_playwright: {e}")
        return None
