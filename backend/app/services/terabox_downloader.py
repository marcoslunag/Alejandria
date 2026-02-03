"""
TeraBox Downloader Service
Bypass para obtener enlaces directos de descarga de TeraBox
Basado en el análisis del paquete terabox-downloader
"""

import requests
import re
import json
import logging
import time
import os
from typing import Optional, Dict, Tuple, List
from urllib.parse import urlparse, parse_qs, unquote, quote

logger = logging.getLogger(__name__)


class TeraBoxDownloader:
    """
    Servicio para descargar archivos de TeraBox
    Implementa bypass de la API de TeraBox para obtener enlaces directos
    """

    # Dominios soportados de TeraBox
    SUPPORTED_DOMAINS = [
        'terabox.com', 'www.terabox.com',
        'terabox.app', 'www.terabox.app',
        '1024terabox.com', 'www.1024terabox.com',
        'teraboxapp.com', 'www.teraboxapp.com',
        '4funbox.com', 'www.4funbox.com',
        'mirrobox.com', 'www.mirrobox.com',
        'nephobox.com', 'www.nephobox.com',
        'terasharelink.com', 'www.terasharelink.com'
    ]

    def __init__(self, cookie: str = None):
        """
        Inicializa el downloader de TeraBox

        Args:
            cookie: Cookie opcional para autenticación (formato: "lang=en; ndus=xxx")
        """
        self.session = requests.Session()
        self.cookie = cookie or "lang=en"
        self.base_domain = "www.terabox.app"  # Dominio que mejor funciona

        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
            'DNT': '1',
            'sec-ch-ua': '"Microsoft Edge";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'Cookie': self.cookie
        })

        self.app_id = "250528"
        self.js_token = None
        self.logid = None
        self.bdstoken = None

    def _normalize_url(self, url: str) -> str:
        """
        Normaliza la URL de TeraBox a un formato consistente

        Args:
            url: URL original de TeraBox

        Returns:
            URL normalizada usando el dominio base
        """
        surl = self._extract_surl(url)
        if surl:
            return f"https://{self.base_domain}/sharing/link?surl={surl}"
        return url

    def _extract_surl(self, url: str) -> Optional[str]:
        """
        Extrae el surl (short URL ID) de la URL de TeraBox

        Args:
            url: URL completa de TeraBox

        Returns:
            surl ID o None
        """
        # Formato: https://terabox.com/s/1xfGpSALsyX5pvWKvwDyeTg
        if '/s/' in url:
            match = re.search(r'/s/1?([a-zA-Z0-9_-]+)', url)
            if match:
                return match.group(1)

        # Formato: ?surl=xxxx
        if 'surl=' in url:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            if 'surl' in params:
                return params['surl'][0]

        return None

    @staticmethod
    def _find_between(s: str, start: str, end: str) -> str:
        """
        Extrae una subcadena entre dos marcadores
        """
        start_index = s.find(start)
        if start_index == -1:
            return ""
        start_index += len(start)
        end_index = s.find(end, start_index)
        if end_index == -1:
            return ""
        return s[start_index:end_index]

    def _get_tokens_from_page(self, url: str) -> bool:
        """
        Visita la página de TeraBox para obtener los tokens necesarios

        Args:
            url: URL de TeraBox

        Returns:
            True si se obtuvieron los tokens correctamente
        """
        try:
            normalized_url = self._normalize_url(url)
            logger.info(f"Fetching TeraBox page: {normalized_url}")

            self.session.headers['Host'] = self.base_domain
            self.session.headers['Referer'] = normalized_url

            # Primera petición para obtener la página
            response = self.session.get(normalized_url, timeout=30, allow_redirects=True)

            if not response.ok:
                logger.error(f"Failed to fetch page: {response.status_code}")
                return False

            # Verificar que tenemos el parámetro surl en la URL final
            final_url = response.url
            parsed = urlparse(final_url)
            query_params = parse_qs(parsed.query)

            if "surl" not in query_params:
                logger.error("Invalid link - no surl in final URL")
                return False

            html = response.text

            # Extraer jsToken - patrón URL-encoded: fn%28%22xxx%22%29
            self.js_token = self._find_between(html, 'fn%28%22', '%22%29')
            if not self.js_token:
                # Intentar patrón sin encoding
                self.js_token = self._find_between(html, 'fn("', '")')

            # Extraer logid
            self.logid = self._find_between(html, 'dp-logid=', '&')
            if not self.logid:
                self.logid = self._find_between(html, 'dp-logid=', '"')

            # Extraer bdstoken
            self.bdstoken = self._find_between(html, 'bdstoken":"', '"')

            logger.debug(f"Extracted tokens - jsToken: {self.js_token[:20] if self.js_token else 'None'}..., logid: {self.logid}, bdstoken: {self.bdstoken}")

            return bool(self.js_token)

        except Exception as e:
            logger.error(f"Error getting tokens from page: {e}")
            return False

    def get_file_info(self, url: str) -> Dict:
        """
        Obtiene información del archivo desde TeraBox

        Args:
            url: URL de TeraBox

        Returns:
            Dict con información del archivo o error
        """
        try:
            if not url:
                return {"error": "Link cannot be empty"}

            # Obtener tokens de la página
            if not self._get_tokens_from_page(url):
                logger.warning("Could not get tokens, trying anyway...")

            surl = self._extract_surl(url)
            if not surl:
                return {"error": "Could not extract surl from URL"}

            # Construir parámetros para la API
            params = {
                "app_id": self.app_id,
                "web": "1",
                "channel": "dubox",
                "clienttype": "0",
                "page": "1",
                "num": "20",
                "by": "name",
                "order": "asc",
                "shorturl": surl,
                "root": "1",
            }

            if self.js_token:
                params["jsToken"] = self.js_token
            if self.logid:
                params["dp-logid"] = self.logid

            # Llamar a la API de share/list
            api_url = f"https://{self.base_domain}/share/list"

            logger.info(f"Calling share/list API: {api_url}")

            response = self.session.get(api_url, params=params, timeout=30)
            data = response.json()

            if data.get("errno"):
                error_msg = data.get("errmsg", f"API error: errno {data.get('errno')}")
                logger.error(f"TeraBox API error: {error_msg}")
                return {"error": error_msg}

            if "list" not in data or not data["list"]:
                return {"error": "No files found in share"}

            # Extraer información del primer archivo
            file_info = data["list"][0]

            return {
                "file_name": file_info.get("server_filename", "unknown"),
                "download_link": file_info.get("dlink", ""),
                "thumbnail": file_info.get("thumbs", {}).get("url3", ""),
                "file_size": self._format_size(int(file_info.get("size", 0))),
                "size_bytes": int(file_info.get("size", 0)),
                "fs_id": file_info.get("fs_id"),
                "share_id": data.get("share_id"),
                "uk": data.get("uk"),
                "is_dir": file_info.get("isdir", 0) == 1
            }

        except requests.RequestException as e:
            return {"error": f"Request error: {str(e)}"}
        except Exception as e:
            return {"error": f"Error getting file info: {str(e)}"}

    def get_direct_link(self, url: str) -> Optional[str]:
        """
        Obtiene el enlace de descarga directa de una URL de TeraBox

        Args:
            url: URL de TeraBox

        Returns:
            URL de descarga directa o None
        """
        file_info = self.get_file_info(url)

        if "error" in file_info:
            logger.error(f"Error getting file info: {file_info['error']}")
            return None

        dlink = file_info.get("download_link")
        if dlink:
            logger.info(f"Got direct link: {dlink[:80]}...")
            return dlink

        logger.error("No download link in file info")
        return None

    def get_all_files(self, url: str) -> List[Dict]:
        """
        Obtiene información de todos los archivos en un share

        Args:
            url: URL de TeraBox

        Returns:
            Lista de diccionarios con información de archivos
        """
        try:
            if not self._get_tokens_from_page(url):
                logger.warning("Could not get tokens, trying anyway...")

            surl = self._extract_surl(url)
            if not surl:
                return []

            params = {
                "app_id": self.app_id,
                "web": "1",
                "channel": "dubox",
                "clienttype": "0",
                "page": "1",
                "num": "1000",  # Obtener muchos archivos
                "by": "name",
                "order": "asc",
                "shorturl": surl,
                "root": "1",
            }

            if self.js_token:
                params["jsToken"] = self.js_token
            if self.logid:
                params["dp-logid"] = self.logid

            api_url = f"https://{self.base_domain}/share/list"
            response = self.session.get(api_url, params=params, timeout=30)
            data = response.json()

            if data.get("errno") or "list" not in data:
                return []

            files = []
            for file_info in data["list"]:
                files.append({
                    "file_name": file_info.get("server_filename", "unknown"),
                    "download_link": file_info.get("dlink", ""),
                    "file_size": self._format_size(int(file_info.get("size", 0))),
                    "size_bytes": int(file_info.get("size", 0)),
                    "fs_id": file_info.get("fs_id"),
                    "is_dir": file_info.get("isdir", 0) == 1
                })

            return files

        except Exception as e:
            logger.error(f"Error getting all files: {e}")
            return []

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Convierte tamaño en bytes a formato legible"""
        if size_bytes >= 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
        elif size_bytes >= 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.2f} MB"
        elif size_bytes >= 1024:
            return f"{size_bytes / 1024:.2f} KB"
        return f"{size_bytes} bytes"

    def download_file(self, url: str, save_path: str = None, callback=None) -> Dict:
        """
        Descarga un archivo de TeraBox

        Args:
            url: URL de TeraBox
            save_path: Directorio donde guardar el archivo
            callback: Función callback para progreso (downloaded_bytes, total_bytes, percentage)

        Returns:
            Dict con file_path o error
        """
        try:
            file_info = self.get_file_info(url)

            if "error" in file_info:
                return file_info

            if not file_info.get("download_link"):
                return {"error": "No download link available"}

            # Preparar path de destino
            filename = file_info["file_name"]
            if save_path:
                os.makedirs(save_path, exist_ok=True)
                file_path = os.path.join(save_path, filename)
            else:
                file_path = filename

            # Headers para descarga
            download_headers = {
                'User-Agent': self.session.headers['User-Agent'],
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Referer': f'https://{self.base_domain}/',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Cookie': self.cookie
            }

            # Descargar archivo
            logger.info(f"Downloading: {filename} ({file_info['file_size']})")

            with self.session.get(
                file_info["download_link"],
                headers=download_headers,
                stream=True,
                timeout=60
            ) as response:
                response.raise_for_status()

                total_size = int(response.headers.get('content-length', 0))
                if total_size == 0:
                    total_size = file_info.get("size_bytes", 0)

                downloaded = 0
                block_size = 8192 * 8  # 64 KB

                with open(file_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=block_size):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)

                            if callback and total_size > 0:
                                percentage = (downloaded / total_size) * 100
                                callback(downloaded, total_size, percentage)

            logger.info(f"Download complete: {file_path}")
            return {"file_path": file_path}

        except Exception as e:
            return {"error": f"Download error: {str(e)}"}

    @classmethod
    def is_terabox_url(cls, url: str) -> bool:
        """
        Verifica si una URL es de TeraBox

        Args:
            url: URL a verificar

        Returns:
            True si es una URL de TeraBox
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            return any(d in domain for d in cls.SUPPORTED_DOMAINS)
        except:
            return False


# Función auxiliar para uso rápido
def get_terabox_direct_link(url: str, cookie: str = None) -> Optional[str]:
    """
    Función auxiliar para obtener enlace directo de TeraBox

    Args:
        url: URL de TeraBox
        cookie: Cookie opcional para autenticación

    Returns:
        URL de descarga directa o None
    """
    downloader = TeraBoxDownloader(cookie)
    return downloader.get_direct_link(url)


def get_terabox_file_info(url: str, cookie: str = None) -> Dict:
    """
    Función auxiliar para obtener información de archivo

    Args:
        url: URL de TeraBox
        cookie: Cookie opcional para autenticación

    Returns:
        Dict con información del archivo
    """
    downloader = TeraBoxDownloader(cookie)
    return downloader.get_file_info(url)
