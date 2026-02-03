"""
TeraBox API Service
Bypass para descargar de TeraBox usando tokens de cuenta
Basado en: https://github.com/maiquocthinh/Terabox-DL
"""

import requests
import re
import os
import logging
from typing import Optional, Dict, List
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)

# Configuración desde variables de entorno
TERABOX_COOKIE = os.environ.get('TERABOX_COOKIE', '')
TERABOX_JS_TOKEN = os.environ.get('TERABOX_JS_TOKEN', '')
TERABOX_DP_LOGID = os.environ.get('TERABOX_DP_LOGID', '')


class TeraBoxAPI:
    """
    Servicio para descargar archivos de TeraBox
    Requiere tokens de una cuenta de TeraBox configurados en variables de entorno
    """

    BASE_URL = "https://www.terabox.com"
    APP_ID = "250528"

    SUPPORTED_DOMAINS = [
        'terabox.com', 'www.terabox.com',
        'terabox.app', 'www.terabox.app',
        '1024terabox.com', 'www.1024terabox.com',
        'teraboxapp.com', 'www.teraboxapp.com',
        '4funbox.com', 'mirrobox.com',
        'nephobox.com', 'terasharelink.com'
    ]

    def __init__(self, cookie: str = None, js_token: str = None, dp_logid: str = None):
        """
        Inicializa el servicio de TeraBox

        Args:
            cookie: Cookie de sesión (ndus=xxx). Si no se proporciona, usa variable de entorno
            js_token: Token JS de la página. Si no se proporciona, usa variable de entorno
            dp_logid: Log ID. Si no se proporciona, usa variable de entorno
        """
        self.cookie = cookie or TERABOX_COOKIE
        self.js_token = js_token or TERABOX_JS_TOKEN
        self.dp_logid = dp_logid or TERABOX_DP_LOGID

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': f'{self.BASE_URL}/',
        })

        if self.cookie:
            self.session.headers['Cookie'] = self.cookie

    def _extract_shorturl(self, url: str) -> Optional[str]:
        """Extrae el shorturl de la URL de TeraBox"""
        # Formato: /s/1xxx o /s/xxx
        if '/s/' in url:
            match = re.search(r'/s/(1?[a-zA-Z0-9_-]+)', url)
            if match:
                surl = match.group(1)
                # Quitar el "1" inicial si existe
                if surl.startswith('1') and len(surl) > 20:
                    return surl[1:]
                return surl

        # Formato: ?surl=xxx
        if 'surl=' in url:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            if 'surl' in params:
                return params['surl'][0]

        return None

    def get_file_info(self, url: str, password: str = "") -> Dict:
        """
        Obtiene información del archivo compartido

        Args:
            url: URL de TeraBox
            password: Contraseña si el enlace está protegido

        Returns:
            Dict con shareid, uk, sign, timestamp, y lista de archivos
        """
        try:
            shorturl = self._extract_shorturl(url)
            if not shorturl:
                return {"ok": False, "error": "No se pudo extraer shorturl de la URL"}

            logger.info(f"TeraBox: Getting info for shorturl={shorturl}")

            # Si hay contraseña, obtener cookie de verificación
            extra_cookie = ""
            if password:
                extra_cookie = self._verify_password(shorturl, password)
                if not extra_cookie:
                    return {"ok": False, "error": "Contraseña incorrecta"}

            # Llamar al API share/list
            params = {
                'app_id': self.APP_ID,
                'shorturl': shorturl,
                'root': '1'
            }

            headers = dict(self.session.headers)
            if extra_cookie:
                headers['Cookie'] = (headers.get('Cookie', '') + '; ' + extra_cookie).strip('; ')

            response = self.session.get(
                f"{self.BASE_URL}/share/list",
                params=params,
                headers=headers,
                timeout=30
            )

            if not response.ok:
                return {"ok": False, "error": f"HTTP {response.status_code}"}

            data = response.json()

            if data.get('errno') != 0:
                error_msg = data.get('errmsg', f"errno {data.get('errno')}")
                logger.error(f"TeraBox API error: {error_msg}")
                return {"ok": False, "error": error_msg}

            # Extraer información de archivos
            files = []
            for file in data.get('list', []):
                files.append({
                    'filename': file.get('server_filename'),
                    'fs_id': file.get('fs_id'),
                    'size': file.get('size'),
                    'is_dir': file.get('isdir', 0) == 1,
                    'category': file.get('category'),
                    'path': file.get('path', '')
                })

            return {
                "ok": True,
                "shareid": data.get('shareid'),
                "uk": data.get('uk'),
                "sign": data.get('sign'),
                "timestamp": data.get('timestamp'),
                "list": files,
                "file_name": files[0]['filename'] if files else 'unknown',
                "file_size": files[0]['size'] if files else 0,
                "fs_id": files[0]['fs_id'] if files else None
            }

        except Exception as e:
            logger.error(f"TeraBox get_file_info error: {e}")
            return {"ok": False, "error": str(e)}

    def _verify_password(self, shorturl: str, password: str) -> Optional[str]:
        """Verifica la contraseña y obtiene la cookie de sesión"""
        try:
            params = {'app_id': self.APP_ID, 'surl': shorturl}
            response = self.session.post(
                f"{self.BASE_URL}/share/verify",
                params=params,
                data={'pwd': password},
                timeout=30
            )

            data = response.json()
            if data.get('errno') != 0:
                return None

            # Extraer cookie de la respuesta
            cookies = response.headers.get('Set-Cookie', '')
            return cookies.split(';')[0] if cookies else ''

        except Exception as e:
            logger.error(f"TeraBox verify password error: {e}")
            return None

    def get_download_link(self, url: str, fs_id: int = None, password: str = "") -> Dict:
        """
        Obtiene el enlace de descarga directa

        Args:
            url: URL de TeraBox
            fs_id: ID del archivo (opcional, se obtiene automáticamente)
            password: Contraseña si el enlace está protegido

        Returns:
            Dict con download_link o error
        """
        try:
            # Verificar que tenemos los tokens necesarios
            if not self.cookie or not self.js_token:
                return {
                    "ok": False,
                    "error": "TeraBox requiere configurar TERABOX_COOKIE y TERABOX_JS_TOKEN"
                }

            # Obtener info del archivo
            file_info = self.get_file_info(url, password)
            if not file_info.get('ok'):
                return file_info

            target_fs_id = fs_id or file_info.get('fs_id')
            if not target_fs_id:
                return {"ok": False, "error": "No se pudo obtener fs_id"}

            logger.info(f"TeraBox: Getting download link for fs_id={target_fs_id}")

            # Paso 1: Obtener dlink
            params = {
                'app_id': self.APP_ID,
                'web': '1',
                'channel': 'dubox',
                'clienttype': '0',
                'jsToken': self.js_token,
                'dp-logid': self.dp_logid,
                'shareid': file_info.get('shareid'),
                'uk': file_info.get('uk'),
                'sign': file_info.get('sign'),
                'timestamp': file_info.get('timestamp'),
                'primaryid': file_info.get('shareid'),
                'product': 'share',
                'nozip': '0',
                'fid_list': f'[{target_fs_id}]'
            }

            response = self.session.get(
                f"{self.BASE_URL}/share/download",
                params=params,
                timeout=30
            )

            if not response.ok:
                return {"ok": False, "error": f"HTTP {response.status_code}"}

            data = response.json()

            if data.get('errno') != 0:
                error_msg = data.get('errmsg', f"errno {data.get('errno')}")
                logger.error(f"TeraBox download API error: {error_msg}")
                return {"ok": False, "error": error_msg}

            dlink = data.get('dlink')
            if not dlink:
                return {"ok": False, "error": "No se obtuvo dlink"}

            # Paso 2: Resolver dlink para obtener URL final
            logger.info("TeraBox: Resolving dlink to final URL")

            download_response = self.session.get(
                dlink,
                allow_redirects=False,
                timeout=30
            )

            # El dlink redirige a la URL de descarga real
            if download_response.status_code in [301, 302, 303, 307, 308]:
                final_url = download_response.headers.get('Location', dlink)
            else:
                final_url = dlink

            logger.info(f"TeraBox: Got download link successfully")

            return {
                "ok": True,
                "download_link": final_url,
                "file_name": file_info.get('file_name'),
                "file_size": file_info.get('file_size')
            }

        except Exception as e:
            logger.error(f"TeraBox get_download_link error: {e}")
            return {"ok": False, "error": str(e)}

    def download_file(self, url: str, save_path: str, callback=None) -> Dict:
        """
        Descarga un archivo de TeraBox

        Args:
            url: URL de TeraBox
            save_path: Directorio donde guardar el archivo
            callback: Función callback para progreso (downloaded, total, percentage)

        Returns:
            Dict con file_path o error
        """
        try:
            # Obtener enlace de descarga
            link_info = self.get_download_link(url)

            if not link_info.get('ok'):
                return link_info

            download_link = link_info.get('download_link')
            filename = link_info.get('file_name', 'terabox_download')

            # Crear directorio si no existe
            os.makedirs(save_path, exist_ok=True)
            file_path = os.path.join(save_path, filename)

            logger.info(f"TeraBox: Downloading {filename}")

            # Descargar archivo
            with self.session.get(download_link, stream=True, timeout=300) as response:
                response.raise_for_status()

                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                block_size = 65536  # 64KB

                with open(file_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=block_size):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)

                            if callback and total_size > 0:
                                percentage = (downloaded / total_size) * 100
                                callback(downloaded, total_size, percentage)

            logger.info(f"TeraBox: Download complete: {file_path}")
            return {"ok": True, "file_path": file_path}

        except Exception as e:
            logger.error(f"TeraBox download error: {e}")
            return {"ok": False, "error": str(e)}

    @classmethod
    def is_terabox_url(cls, url: str) -> bool:
        """Verifica si una URL es de TeraBox"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            return any(d in domain for d in cls.SUPPORTED_DOMAINS)
        except:
            return False

    @classmethod
    def is_configured(cls) -> bool:
        """Verifica si TeraBox está configurado con los tokens necesarios"""
        return bool(TERABOX_COOKIE and TERABOX_JS_TOKEN)


# Funciones auxiliares
def get_terabox_download_link(url: str) -> Optional[str]:
    """Obtiene enlace de descarga directa de TeraBox"""
    if not TeraBoxAPI.is_configured():
        logger.warning("TeraBox not configured - missing TERABOX_COOKIE or TERABOX_JS_TOKEN")
        return None

    api = TeraBoxAPI()
    result = api.get_download_link(url)

    if result.get("ok"):
        return result.get("download_link")

    logger.error(f"TeraBox error: {result.get('error')}")
    return None


def get_terabox_file_info(url: str) -> Dict:
    """Obtiene información de archivo de TeraBox"""
    api = TeraBoxAPI()
    return api.get_file_info(url)
