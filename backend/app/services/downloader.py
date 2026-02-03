"""
Manga Downloader Service
Async downloader for DDL services (MEGA, MediaFire, Google Drive, TeraBox, etc.)
Con sistema de fallback y priorización de hosts
"""

import aiohttp
import asyncio
import os
import zipfile
from pathlib import Path
from typing import Optional, Callable, List, Dict
import logging
import re
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)

# TeraBox cookie from environment variable
TERABOX_COOKIE = os.environ.get('TERABOX_COOKIE', '')

# TeraBox bypass service URL
TERABOX_BYPASS_URL = "https://terabox.hnn.workers.dev/"


class MangaDownloader:
    """
    Descargador asíncrono para archivos DDL
    Soporta: Enlaces directos, MEGA (con mega.py), MediaFire, Google Drive
    """

    def __init__(self, download_dir: str = "/downloads"):
        """
        Initialize downloader

        Args:
            download_dir: Directory to save downloaded files
        """
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)

        # Configure session headers
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive'
        }

    async def download_chapter(
        self,
        url: str,
        filename: str,
        on_progress: Optional[Callable[[int, int], None]] = None,
        backup_urls: Optional[List[str]] = None
    ) -> Optional[Path]:
        """
        Descarga un capítulo desde URL DDL con sistema de fallback

        Args:
            url: URL de descarga principal
            filename: Nombre del archivo de salida
            on_progress: Callback para progreso (bytes_downloaded, total_bytes)
            backup_urls: Lista de URLs de backup ordenadas por prioridad

        Returns:
            Path al archivo descargado o None si falla
        """
        # Construir lista de URLs a intentar
        urls_to_try = [url]
        if backup_urls:
            urls_to_try.extend(backup_urls)

        # Importar host manager para priorizar
        try:
            from app.services.host_manager import sort_download_links, identify_host, get_host_priority, HostPriority

            # Convertir a formato de links y ordenar por prioridad
            links = [{'url': u} for u in urls_to_try]
            sorted_links = sort_download_links(links)
            urls_to_try = [link['url'] for link in sorted_links]

            logger.info(f"Download order for {filename}:")
            for i, u in enumerate(urls_to_try):
                host = identify_host(u) or 'unknown'
                priority = get_host_priority(u)
                logger.info(f"  {i+1}. [{priority}] {host}: {u[:60]}...")
        except ImportError:
            logger.warning("Host manager not available, using original order")

        last_error = None

        for attempt, current_url in enumerate(urls_to_try):
            try:
                logger.info(f"Download attempt {attempt + 1}/{len(urls_to_try)}: {filename}")
                result = await self._download_single_url(current_url, filename, on_progress)
                if result:
                    logger.info(f"Download successful from attempt {attempt + 1}")
                    return result
            except Exception as e:
                last_error = e
                logger.warning(f"Attempt {attempt + 1} failed: {e}")
                continue

        # Todos los intentos fallaron
        if last_error:
            logger.error(f"All download attempts failed for {filename}: {last_error}")
        return None

    async def _download_single_url(
        self,
        url: str,
        filename: str,
        on_progress: Optional[Callable[[int, int], None]] = None
    ) -> Optional[Path]:
        """
        Descarga desde una única URL

        Args:
            url: URL de descarga
            filename: Nombre del archivo de salida
            on_progress: Callback para progreso

        Returns:
            Path al archivo descargado o None si falla
        """
        logger.info(f"Starting download: {filename} from {url}")

        url_lower = url.lower()

        # Resolver enlaces acortados de OUO.io primero
        if 'ouo.io' in url_lower or 'ouo.press' in url_lower:
            logger.info(f"OUO.io link detected, resolving...")
            resolved_url = await self._resolve_ouo_link(url)
            if resolved_url:
                logger.info(f"OUO.io resolved to: {resolved_url[:60]}...")
                # Llamar recursivamente con el enlace resuelto
                return await self._download_single_url(resolved_url, filename, on_progress)
            else:
                raise ValueError("Could not resolve OUO.io link")

        # Otros acortadores no soportados
        if 'shrinkme' in url_lower:
            logger.warning(f"Unsupported URL shortener: {url}")
            raise ValueError("Unsupported URL shortener (ShrinkMe)")

        # Determinar tipo de enlace y usar el método apropiado
        if 'terabox' in url_lower or '1024terabox' in url_lower or 'teraboxapp' in url_lower:
            return await self._download_terabox(url, filename, on_progress)
        elif 'fireload' in url_lower:
            return await self._download_with_playwright(url, filename, on_progress, 'fireload')
        elif 'mediafire' in url_lower:
            return await self._download_with_playwright(url, filename, on_progress, 'mediafire')
        elif '1fichier' in url_lower:
            return await self._download_with_playwright(url, filename, on_progress, '1fichier')
        elif 'mega.nz' in url_lower or 'mega.co' in url_lower:
            return await self._download_mega(url, filename, on_progress)
        elif 'drive.google' in url_lower:
            return await self._download_gdrive(url, filename, on_progress)
        else:
            # Asumimos enlace directo
            return await self._download_direct(url, filename, on_progress)

    async def _download_with_playwright(
        self,
        url: str,
        filename: str,
        on_progress: Optional[Callable[[int, int], None]] = None,
        host_type: str = 'generic'
    ) -> Optional[Path]:
        """
        Descarga usando Playwright para extraer enlace directo

        Args:
            url: URL del host
            filename: Nombre del archivo
            on_progress: Callback de progreso
            host_type: Tipo de host (fireload, mediafire, etc.)

        Returns:
            Path al archivo descargado o None
        """
        try:
            from app.services.generic_downloader import get_direct_download_link

            logger.info(f"{host_type.upper()}: Extracting direct link from {url}")

            result = await get_direct_download_link(url)

            if result.get("ok") and result.get("download_link"):
                download_link = result["download_link"]
                actual_filename = result.get("file_name", filename)

                logger.info(f"{host_type.upper()}: Got direct link for {actual_filename}")

                # Descargar el archivo
                return await self._download_direct(download_link, filename, on_progress)
            else:
                error = result.get("error", "Unknown error")
                raise ValueError(f"{host_type.upper()} extraction failed: {error}")

        except ImportError as e:
            logger.warning(f"Generic downloader not available: {e}")
            raise ValueError(f"Playwright not available for {host_type}")
        except Exception as e:
            logger.error(f"{host_type.upper()} download error: {e}")
            raise

    async def _download_direct(
        self,
        url: str,
        filename: str,
        on_progress: Optional[Callable[[int, int], None]] = None
    ) -> Optional[Path]:
        """
        Descarga desde enlace directo con sistema de lock files

        Args:
            url: Direct download URL
            filename: Output filename
            on_progress: Progress callback

        Returns:
            Path to downloaded file or None
        """
        output_path = self.download_dir / filename
        lock_file = self.download_dir / f"{filename}.downloading"

        try:
            # Crear lock file para indicar descarga en progreso
            lock_file.touch()
            logger.info(f"Created lock file: {lock_file.name}")

            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=3600), allow_redirects=True) as response:
                    if response.status != 200:
                        logger.error(f"HTTP {response.status} for {url}")
                        lock_file.unlink(missing_ok=True)
                        return None

                    # Verificar Content-Type para evitar guardar HTML
                    content_type = response.headers.get('content-type', '').lower()
                    if 'text/html' in content_type:
                        logger.error(f"Download failed: Server returned HTML instead of file. URL: {url[:100]}")
                        # Leer primeros bytes para verificar
                        first_bytes = await response.content.read(500)
                        if b'<!DOCTYPE' in first_bytes or b'<html' in first_bytes:
                            logger.error(f"Confirmed HTML content. This usually means the download link expired or requires authentication.")
                            lock_file.unlink(missing_ok=True)
                            return None

                    total_size = int(response.headers.get('content-length', 0))

                    # Verificar tamaño mínimo (archivos CBZ/ZIP deben ser > 1KB)
                    if total_size > 0 and total_size < 1024:
                        logger.warning(f"Suspicious file size: {total_size} bytes. May not be a valid archive.")

                    downloaded = 0

                    logger.info(f"Downloading {filename}: {total_size / 1024 / 1024:.2f} MB (Content-Type: {content_type})")

                    with open(output_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            f.write(chunk)
                            downloaded += len(chunk)

                            if on_progress and total_size:
                                await self._call_progress(on_progress, downloaded, total_size)

                    # Verificar archivo descargado no es HTML
                    if output_path.exists():
                        with open(output_path, 'rb') as f:
                            header = f.read(100)
                            if b'<!DOCTYPE' in header or b'<html' in header:
                                logger.error(f"Downloaded file is HTML, not a valid archive. Deleting.")
                                output_path.unlink()
                                lock_file.unlink(missing_ok=True)
                                return None

                    # Verificar integridad del archivo ZIP/CBZ
                    if not self._verify_archive_integrity(output_path):
                        logger.error(f"Archive integrity check failed: {filename}")
                        output_path.unlink(missing_ok=True)
                        lock_file.unlink(missing_ok=True)
                        return None

                    # Eliminar lock file - descarga completa y verificada
                    lock_file.unlink(missing_ok=True)
                    logger.info(f"Download completed and verified: {filename}")
                    return output_path

        except asyncio.TimeoutError:
            logger.error(f"Download timeout for {url}")
            return None
        except Exception as e:
            logger.error(f"Direct download error: {e}")
            return None

    async def _download_mega(
        self,
        url: str,
        filename: str,
        on_progress: Optional[Callable[[int, int], None]] = None
    ) -> Optional[Path]:
        """
        Descarga desde MEGA usando mega.py

        Args:
            url: MEGA URL
            filename: Output filename
            on_progress: Progress callback

        Returns:
            Path to downloaded file or None
        """
        try:
            from mega import Mega

            output_path = self.download_dir / filename

            logger.info(f"Downloading from MEGA: {filename}")

            mega = Mega()
            m = mega.login()  # Anonymous login

            # mega.py es síncrono, ejecutar en thread pool
            loop = asyncio.get_event_loop()

            # Download to temp location
            downloaded_file = await loop.run_in_executor(
                None,
                lambda: m.download_url(url, str(self.download_dir))
            )

            # Rename to correct filename if needed
            if downloaded_file and Path(downloaded_file).exists():
                downloaded_path = Path(downloaded_file)
                if downloaded_path != output_path:
                    downloaded_path.rename(output_path)

                logger.info(f"MEGA download completed: {filename}")
                return output_path
            else:
                logger.error(f"MEGA download failed: file not found")
                return None

        except ImportError:
            logger.error("mega.py not installed. Install with: pip install mega.py")
            return None
        except Exception as e:
            logger.error(f"MEGA download error: {e}")
            return None

    async def _download_mediafire(
        self,
        url: str,
        filename: str,
        on_progress: Optional[Callable[[int, int], None]] = None
    ) -> Optional[Path]:
        """
        Descarga desde MediaFire

        MediaFire requiere parsear la página para obtener el enlace directo

        Args:
            url: MediaFire URL
            filename: Output filename
            on_progress: Progress callback

        Returns:
            Path to downloaded file or None
        """
        try:
            from bs4 import BeautifulSoup

            logger.info(f"Downloading from MediaFire: {filename}")

            # 1. Obtener página de descarga
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"MediaFire page error: HTTP {response.status}")
                        return None

                    html = await response.text()

            # 2. Extraer enlace directo
            soup = BeautifulSoup(html, 'html.parser')

            # MediaFire tiene el enlace en el botón de descarga
            download_button = soup.select_one('a#downloadButton, a.input[href*="download"]')

            if not download_button:
                # Intento alternativo: buscar en scripts
                scripts = soup.find_all('script')
                direct_url = None

                for script in scripts:
                    if script.string and 'download_url' in script.string:
                        match = re.search(r'"(https?://download\d+\.mediafire\.com/[^"]+)"', script.string)
                        if match:
                            direct_url = match.group(1)
                            break

                if not direct_url:
                    logger.error("MediaFire download link not found")
                    return None
            else:
                direct_url = download_button.get('href')

            if not direct_url:
                logger.error("MediaFire direct URL is empty")
                return None

            logger.debug(f"MediaFire direct URL: {direct_url}")

            # 3. Descargar desde enlace directo
            return await self._download_direct(direct_url, filename, on_progress)

        except ImportError:
            logger.error("BeautifulSoup4 not installed")
            return None
        except Exception as e:
            logger.error(f"MediaFire download error: {e}")
            return None

    async def _download_gdrive(
        self,
        url: str,
        filename: str,
        on_progress: Optional[Callable[[int, int], None]] = None
    ) -> Optional[Path]:
        """
        Descarga desde Google Drive

        Args:
            url: Google Drive URL
            filename: Output filename
            on_progress: Progress callback

        Returns:
            Path to downloaded file or None
        """
        try:
            logger.info(f"Downloading from Google Drive: {filename}")

            # Extraer file ID de la URL
            file_id = self._extract_gdrive_id(url)

            if not file_id:
                logger.error("Could not extract Google Drive file ID")
                return None

            # Construir URL de descarga directa
            download_url = f"https://drive.google.com/uc?export=download&id={file_id}"

            output_path = self.download_dir / filename

            async with aiohttp.ClientSession(headers=self.headers) as session:
                # Primera petición para obtener token si es necesario
                async with session.get(download_url, allow_redirects=True) as response:
                    if response.status != 200:
                        logger.error(f"Google Drive error: HTTP {response.status}")
                        return None

                    # Si el archivo es grande, Google Drive muestra una página de confirmación
                    content = await response.text()

                    if 'virus scan warning' in content.lower() or 'download anyway' in content.lower():
                        # Buscar token de confirmación
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(content, 'html.parser')

                        form = soup.find('form', {'id': 'download-form'})
                        if form:
                            confirm_url = form.get('action')
                            # Descargar con confirmación
                            async with session.get(confirm_url, allow_redirects=True) as confirm_response:
                                if confirm_response.status == 200:
                                    total_size = int(confirm_response.headers.get('content-length', 0))
                                    downloaded = 0

                                    with open(output_path, 'wb') as f:
                                        async for chunk in confirm_response.content.iter_chunked(8192):
                                            f.write(chunk)
                                            downloaded += len(chunk)

                                            if on_progress and total_size:
                                                await self._call_progress(on_progress, downloaded, total_size)

                                    logger.info(f"Google Drive download completed: {filename}")
                                    return output_path
                    else:
                        # Descarga directa
                        total_size = int(response.headers.get('content-length', 0))
                        downloaded = 0

                        with open(output_path, 'wb') as f:
                            async for chunk in response.content.iter_chunked(8192):
                                f.write(chunk)
                                downloaded += len(chunk)

                                if on_progress and total_size:
                                    await self._call_progress(on_progress, downloaded, total_size)

                        logger.info(f"Google Drive download completed: {filename}")
                        return output_path

            return None

        except Exception as e:
            logger.error(f"Google Drive download error: {e}")
            return None

    def _extract_gdrive_id(self, url: str) -> Optional[str]:
        """
        Extrae file ID de URL de Google Drive

        Args:
            url: Google Drive URL

        Returns:
            File ID or None
        """
        patterns = [
            r'/d/([a-zA-Z0-9_-]+)',
            r'id=([a-zA-Z0-9_-]+)',
            r'/file/d/([a-zA-Z0-9_-]+)'
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        return None

    async def _call_progress(self, callback: Callable, downloaded: int, total: int):
        """
        Calls progress callback safely

        Args:
            callback: Progress callback function
            downloaded: Bytes downloaded
            total: Total bytes
        """
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(downloaded, total)
            else:
                callback(downloaded, total)
        except Exception as e:
            logger.warning(f"Progress callback error: {e}")

    async def _download_terabox(
        self,
        url: str,
        filename: str,
        on_progress: Optional[Callable[[int, int], None]] = None
    ) -> Optional[Path]:
        """
        Descarga desde TeraBox usando el bypass via 1024tera.com.

        Utiliza TeraBoxBypass que obtiene enlaces directos de descarga
        usando el dominio alternativo 1024tera.com con cookies de sesión.

        Args:
            url: TeraBox URL
            filename: Output filename
            on_progress: Progress callback

        Returns:
            Path to downloaded file or None
        """
        output_path = self.download_dir / filename
        lock_file = self.download_dir / f"{filename}.downloading"

        download_link = None
        file_info = {}

        # Usar TeraBoxBypass (método probado y funcional)
        try:
            from app.services.terabox_bypass import TeraBoxBypass

            logger.info(f"TeraBox: Using TeraBoxBypass via 1024tera.com")

            # Construir cookies desde variables de entorno
            cookie_dict = {}
            if TERABOX_COOKIE:
                # Parsear cookie string a dict
                for part in TERABOX_COOKIE.split(';'):
                    if '=' in part:
                        key, value = part.strip().split('=', 1)
                        cookie_dict[key.strip()] = value.strip()

            bypass = TeraBoxBypass(cookie_dict=cookie_dict if cookie_dict else None)
            result = bypass.get_download_link(url)

            if result.get("ok"):
                download_link = result.get("download_link")
                file_info = {
                    "file_name": result.get("file_name", filename),
                    "file_size": int(result.get("file_size", 0) or 0)
                }
                logger.info(f"TeraBox Bypass: Got direct link for {file_info.get('file_name')}")
            else:
                logger.warning(f"TeraBox Bypass error: {result.get('error')}")

        except ImportError as e:
            logger.warning(f"TeraBox Bypass not available: {e}")
        except Exception as e:
            logger.warning(f"TeraBox Bypass failed: {e}")

        # Si no tenemos enlace de descarga, fallar
        if not download_link:
            raise ValueError(
                f"Could not get TeraBox download link. "
                f"All methods failed. Consider running terabox_auth.py for authentication."
            )

        # Descargar usando el enlace obtenido
        return await self._download_terabox_link(
            download_link, output_path, lock_file, on_progress
        )

    async def _download_terabox_link(
        self,
        download_link: str,
        output_path: Path,
        lock_file: Path,
        on_progress: Optional[Callable[[int, int], None]] = None
    ) -> Optional[Path]:
        """
        Descarga un archivo desde un enlace de TeraBox.

        Args:
            download_link: URL de descarga directa
            output_path: Path de destino
            lock_file: Path del lock file
            on_progress: Callback de progreso

        Returns:
            Path al archivo descargado o None
        """
        terabox_headers = {
            **self.headers,
            'Referer': 'https://www.terabox.com/',
        }

        try:
            # Crear lock file
            lock_file.touch()
            logger.info(f"Created lock file: {lock_file.name}")

            async with aiohttp.ClientSession(headers=terabox_headers) as session:
                async with session.get(download_link, timeout=aiohttp.ClientTimeout(total=7200)) as response:
                    if response.status != 200:
                        logger.error(f"TeraBox download HTTP {response.status}")
                        lock_file.unlink(missing_ok=True)
                        return None

                    # Verificar que no sea HTML
                    content_type = response.headers.get('content-type', '').lower()
                    if 'text/html' in content_type:
                        logger.error("TeraBox returned HTML instead of file - link may be expired")
                        lock_file.unlink(missing_ok=True)
                        return None

                    total_size = int(response.headers.get('content-length', 0))
                    downloaded = 0

                    logger.info(f"Downloading TeraBox file: {total_size / 1024 / 1024:.2f} MB")

                    with open(output_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(65536):
                            f.write(chunk)
                            downloaded += len(chunk)

                            if on_progress and total_size:
                                await self._call_progress(on_progress, downloaded, total_size)

                    # Verificar integridad
                    if not self._verify_archive_integrity(output_path):
                        logger.error(f"TeraBox archive integrity check failed: {output_path.name}")
                        output_path.unlink(missing_ok=True)
                        lock_file.unlink(missing_ok=True)
                        return None

                    # Eliminar lock file - descarga completa
                    lock_file.unlink(missing_ok=True)
                    logger.info(f"TeraBox download completed and verified: {output_path.name}")
                    return output_path

        except Exception as e:
            lock_file.unlink(missing_ok=True)
            logger.error(f"TeraBox download error: {e}")
            raise ValueError(f"Download failed: {str(e)}")

    async def _resolve_ouo_link(self, ouo_url: str) -> Optional[str]:
        """
        Resuelve un enlace de OUO.io para obtener la URL final

        Args:
            ouo_url: URL de OUO.io

        Returns:
            URL final resuelta o None si falla
        """
        try:
            from app.services.ouo_resolver import resolve_ouo_link

            logger.info(f"Resolving OUO.io link: {ouo_url}")
            final_url = await resolve_ouo_link(ouo_url)

            if final_url:
                logger.info(f"OUO.io resolved successfully to: {final_url[:60]}...")
                return final_url
            else:
                logger.error("OUO.io resolution failed - no URL returned")
                return None

        except ImportError as e:
            logger.error(f"OUO resolver not available: {e}")
            return None
        except Exception as e:
            logger.error(f"Error resolving OUO.io link: {e}")
            return None

    def _verify_archive_integrity(self, file_path: Path) -> bool:
        """
        Verifica la integridad de un archivo ZIP/CBZ/RAR/CBR
        Detecta el formato real por magic bytes, no por extensión

        Args:
            file_path: Path al archivo

        Returns:
            True si el archivo es válido
        """
        import zipfile

        if not file_path.exists():
            return False

        # Verificar tamaño mínimo
        if file_path.stat().st_size < 1024:
            logger.warning(f"File too small to be valid archive: {file_path.name}")
            return False

        # Detectar formato real por magic bytes
        actual_format = self._detect_archive_format(file_path)

        if actual_format == 'zip':
            try:
                with zipfile.ZipFile(file_path, 'r') as zf:
                    # Verificar CRC de todos los archivos
                    bad_file = zf.testzip()
                    if bad_file:
                        logger.error(f"Corrupted file in archive: {bad_file}")
                        return False

                    # Verificar que hay contenido
                    if len(zf.namelist()) == 0:
                        logger.error(f"Empty archive: {file_path.name}")
                        return False

                logger.debug(f"ZIP archive integrity verified: {file_path.name}")
                return True
            except zipfile.BadZipFile:
                logger.error(f"Invalid ZIP file: {file_path.name}")
                return False
            except Exception as e:
                logger.error(f"Error verifying ZIP archive: {e}")
                return False

        elif actual_format == 'rar':
            # RAR file - accept as valid, KCC Worker can handle RAR files
            logger.info(f"RAR archive detected (saved as {file_path.suffix}), accepting as valid: {file_path.name}")
            return True

        else:
            # Unknown format but file exists with decent size - accept it
            logger.warning(f"Unknown archive format for {file_path.name}, accepting based on size")
            return file_path.stat().st_size > 10240  # At least 10KB

    def _detect_archive_format(self, file_path: Path) -> str:
        """
        Detecta el formato de archivo por magic bytes

        Returns:
            'zip', 'rar', o 'unknown'
        """
        try:
            with open(file_path, 'rb') as f:
                header = f.read(8)

            # ZIP: PK\x03\x04 or PK\x05\x06 (empty) or PK\x07\x08 (spanned)
            if header[:4] in [b'PK\x03\x04', b'PK\x05\x06', b'PK\x07\x08']:
                return 'zip'

            # RAR: Rar!\x1a\x07 (RAR 4.x) or Rar!\x1a\x07\x01 (RAR 5.x)
            if header[:7] == b'Rar!\x1a\x07\x00' or header[:7] == b'Rar!\x1a\x07\x01':
                return 'rar'
            if header[:6] == b'Rar!\x1a\x07':
                return 'rar'

            return 'unknown'
        except Exception as e:
            logger.warning(f"Error detecting archive format: {e}")
            return 'unknown'

    def get_filename_from_url(self, url: str) -> str:
        """
        Extrae nombre de archivo sugerido desde URL

        Args:
            url: Download URL

        Returns:
            Suggested filename
        """
        try:
            parsed = urlparse(url)
            path = parsed.path

            if path:
                filename = Path(path).name
                if filename:
                    return filename

            # Si no hay nombre de archivo, generar uno
            return f"chapter_{hash(url) % 100000}.cbz"

        except Exception:
            return f"chapter_{hash(url) % 100000}.cbz"
