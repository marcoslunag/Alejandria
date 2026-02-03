"""
TeraBox Bypass Service - Solución robusta para descargas de TeraBox
Utiliza múltiples métodos de bypass incluyendo API directa con cookies
y dominios alternativos como 1024tera.com

Método probado y funcional: 1024tera.com con cookies de sesión
"""

import asyncio
import aiohttp
import requests
import re
import json
import logging
import time
import os
from typing import Optional, Dict, List, Any, Tuple
from urllib.parse import urlparse, parse_qs
from pathlib import Path

logger = logging.getLogger(__name__)


class TeraBoxBypass:
    """
    Servicio de bypass para TeraBox con múltiples estrategias:
    1. API directa via 1024tera.com con cookies (MÉTODO PRINCIPAL - FUNCIONA)
    2. API proxy de terceros (fallback)
    3. API directa terabox.com (fallback)
    """
    
    # APIs proxy conocidas (fallback)
    PROXY_APIS = [
        {
            "name": "vercel",
            "url": "https://teraboxapi-phi.vercel.app/api",
            "method": "GET",
            "param_name": "url",
        },
    ]
    
    # Dominios de TeraBox soportados
    TERABOX_DOMAINS = [
        'terabox.com', 'www.terabox.com',
        'terabox.app', 'www.terabox.app',
        '1024terabox.com', 'www.1024terabox.com',
        '1024tera.com', 'www.1024tera.com',
        'teraboxapp.com', 'www.teraboxapp.com',
        '4funbox.com', 'www.4funbox.com',
        'mirrobox.com', 'www.mirrobox.com',
        'nephobox.com', 'www.nephobox.com',
        'freeterabox.com', 'www.freeterabox.com',
        'momerybox.com', 'www.momerybox.com',
        'tibibox.com', 'www.tibibox.com',
    ]
    
    # Dominio alternativo que funciona mejor
    PREFERRED_DOMAIN = "www.1024tera.com"
    FALLBACK_DOMAIN = "www.terabox.com"
    
    def __init__(self, cookies: List[Dict] = None, cookie_string: str = None, cookie_dict: Dict = None):
        """
        Inicializa el bypass de TeraBox.
        
        Args:
            cookies: Lista de cookies en formato dict (del navegador)
            cookie_string: String de cookies formato "name=value; name2=value2"
            cookie_dict: Dict simple de cookies {name: value}
        """
        self.cookies = cookies or []
        self.cookie_dict = cookie_dict or {}
        
        # Si se pasaron cookies como lista, convertir a dict
        if self.cookies and not self.cookie_dict:
            self.cookie_dict = {c['name']: c['value'] for c in self.cookies if c.get('name') and c.get('value')}
        
        self.cookie_string = cookie_string or self._cookies_to_string(self.cookies)
        self.session = requests.Session()
        self._setup_session()
        
    def _cookies_to_string(self, cookies: List[Dict]) -> str:
        """Convierte lista de cookies a formato string."""
        if not cookies:
            return ""
        return "; ".join(f"{c['name']}={c['value']}" for c in cookies if c.get('name') and c.get('value'))
    
    def _setup_session(self):
        """Configura la sesión HTTP con headers realistas."""
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'DNT': '1',
        })
        # Agregar cookies a la sesión
        if self.cookie_dict:
            self.session.cookies.update(self.cookie_dict)
        elif self.cookie_string:
            self.session.headers['Cookie'] = self.cookie_string
    
    @staticmethod
    def _find_between(string: str, start: str, end: str) -> str:
        """Extrae substring entre dos marcadores."""
        start_index = string.find(start)
        if start_index == -1:
            return ""
        start_index += len(start)
        end_index = string.find(end, start_index)
        if end_index == -1:
            return ""
        return string[start_index:end_index]
            
    def _extract_short_url(self, url: str) -> Optional[str]:
        """
        Extrae el identificador corto (surl) de una URL de TeraBox.
        
        Soporta formatos:
        - https://terabox.com/s/1ABC123
        - https://terabox.com/sharing/link?surl=ABC123
        - https://1024tera.com/s/ABC123
        """
        # Formato: /s/1xxx o /s/xxx
        if '/s/' in url:
            match = re.search(r'/s/(1?)([a-zA-Z0-9_-]+)', url)
            if match:
                # El '1' inicial es opcional/decorativo
                prefix = match.group(1)
                surl = match.group(2)
                return surl
        
        # Formato: ?surl=xxx
        if 'surl=' in url:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            if 'surl' in params:
                return params['surl'][0]
        
        return None
    
    @classmethod
    def is_terabox_url(cls, url: str) -> bool:
        """Verifica si una URL es de TeraBox."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            return any(d in domain for d in cls.TERABOX_DOMAINS)
        except:
            return False
    
    # ========================================
    # MÉTODO 1: API 1024tera.com (PRINCIPAL - FUNCIONA)
    # ========================================
    
    def get_info_via_1024tera(self, url: str, password: str = "") -> Dict:
        """
        Obtiene información del archivo usando 1024tera.com.
        
        Este método es el más confiable y está probado que funciona.
        Requiere cookies válidas de TeraBox.
        
        Args:
            url: URL de TeraBox
            password: Contraseña si el enlace está protegido
            
        Returns:
            Dict con información del archivo/carpeta incluyendo dlink
        """
        short_url = self._extract_short_url(url)
        if not short_url:
            return {"ok": False, "error": "No se pudo extraer short_url de la URL"}
        
        try:
            # Paso 1: Visitar la página para obtener tokens
            page_url = f"https://{self.PREFERRED_DOMAIN}/sharing/link?surl={short_url}"
            logger.info(f"Visitando: {page_url}")
            
            response = self.session.get(page_url, timeout=30)
            
            if response.status_code != 200:
                logger.warning(f"Error visitando página: HTTP {response.status_code}")
                return {"ok": False, "error": f"HTTP {response.status_code}"}
            
            html = response.text
            
            # Extraer jsToken
            js_token = self._find_between(html, 'fn%28%22', '%22%29')
            if not js_token:
                js_token = self._find_between(html, 'fn("', '")')
            
            # Extraer logId
            log_id = self._find_between(html, 'dp-logid=', '&')
            if not log_id:
                log_id = self._find_between(html, 'dp-logid=', '"')
            
            if not js_token:
                logger.warning("No se pudo extraer jsToken de la página")
                # Intentar continuar sin jsToken
            
            # Paso 2: Llamar a la API share/list
            api_url = f"https://{self.PREFERRED_DOMAIN}/share/list"
            
            params = {
                'app_id': '250528',
                'web': '1',
                'channel': 'dubox',
                'clienttype': '0',
                'jsToken': js_token or '',
                'dplogid': log_id or '',
                'page': '1',
                'num': '100',
                'order': 'time',
                'desc': '1',
                'site_referer': page_url,
                'shorturl': short_url,
                'root': '1'
            }
            
            logger.info(f"Llamando API: {api_url}")
            response = self.session.get(api_url, params=params, timeout=30)
            
            if response.status_code != 200:
                return {"ok": False, "error": f"API retornó HTTP {response.status_code}"}
            
            data = response.json()
            
            if data.get('errno') == 0:
                logger.info(f"Información obtenida correctamente via 1024tera.com")
                return {
                    "ok": True,
                    "list": data.get('list', []),
                    "shareid": data.get('shareid'),
                    "uk": data.get('uk'),
                    "sign": data.get('sign'),
                    "timestamp": data.get('timestamp'),
                    "title": data.get('title'),
                    "_method": "1024tera",
                    "_short_url": short_url,
                    "_js_token": js_token,
                    "_log_id": log_id,
                }
            else:
                error_msg = data.get('errmsg', f"errno {data.get('errno')}")
                logger.warning(f"API 1024tera error: {error_msg}")
                return {"ok": False, "error": error_msg, "errno": data.get('errno')}
                
        except requests.exceptions.Timeout:
            logger.warning("Timeout en 1024tera.com")
            return {"ok": False, "error": "Timeout"}
        except requests.exceptions.RequestException as e:
            logger.warning(f"Error de red: {e}")
            return {"ok": False, "error": str(e)}
        except json.JSONDecodeError as e:
            logger.warning(f"Respuesta no es JSON válido: {e}")
            return {"ok": False, "error": "Respuesta inválida"}
        except Exception as e:
            logger.error(f"Error inesperado: {e}")
            return {"ok": False, "error": str(e)}
    
    def get_folder_contents(self, short_url: str, path: str, js_token: str = "", log_id: str = "") -> Dict:
        """
        Obtiene el contenido de una carpeta específica.
        
        Args:
            short_url: Identificador corto del recurso
            path: Ruta de la carpeta dentro del share
            js_token: Token JS (opcional)
            log_id: Log ID (opcional)
            
        Returns:
            Dict con lista de archivos
        """
        try:
            api_url = f"https://{self.PREFERRED_DOMAIN}/share/list"
            
            params = {
                'app_id': '250528',
                'web': '1',
                'channel': 'dubox',
                'clienttype': '0',
                'jsToken': js_token,
                'dplogid': log_id,
                'page': '1',
                'num': '100',
                'order': 'asc',
                'by': 'name',
                'shorturl': short_url,
                'dir': path,
            }
            
            response = self.session.get(api_url, params=params, timeout=30)
            data = response.json()
            
            if data.get('errno') == 0:
                return {"ok": True, "list": data.get('list', [])}
            else:
                return {"ok": False, "error": data.get('errmsg')}
                
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    # ========================================
    # MÉTODO 2: API Directa terabox.com (Fallback)
    # ========================================
    
    def get_info_direct(self, url: str) -> Dict:
        """
        Intenta obtener información directamente de la API de TeraBox.
        
        Este método requiere cookies válidas y puede fallar con
        error "need verify" si TeraBox detecta automatización.
        """
        short_url = self._extract_short_url(url)
        if not short_url:
            return {"ok": False, "error": "No se pudo extraer short_url"}
        
        # Visitar página primero para obtener tokens
        page_url = f"https://www.terabox.com/sharing/link?surl={short_url}"
        
        try:
            self.session.headers['Referer'] = page_url
            page_response = self.session.get(page_url, timeout=30)
            
            html = page_response.text
            
            # Extraer jsToken
            js_token = ""
            for pattern in [r'fn%28%22([^%]+)%22%29', r'fn\("([^"]+)"\)']:
                match = re.search(pattern, html)
                if match:
                    js_token = match.group(1)
                    break
            
            # Extraer logid
            log_id = ""
            match = re.search(r'dp-logid=([^&"]+)', html)
            if match:
                log_id = match.group(1)
            
            # Llamar API
            api_url = "https://www.terabox.com/share/list"
            params = {
                'app_id': '250528',
                'web': '1',
                'channel': 'dubox',
                'clienttype': '0',
                'jsToken': js_token,
                'dplogid': log_id,
                'page': '1',
                'num': '100',
                'order': 'time',
                'desc': '1',
                'shorturl': short_url,
                'root': '1'
            }
            
            response = self.session.get(api_url, params=params, timeout=30)
            data = response.json()
            
            if data.get('errno') == 0:
                return {
                    "ok": True,
                    "list": data.get('list', []),
                    "shareid": data.get('shareid'),
                    "uk": data.get('uk'),
                    "sign": data.get('sign'),
                    "timestamp": data.get('timestamp'),
                    "_method": "direct"
                }
            else:
                return {
                    "ok": False,
                    "error": data.get('errmsg', f"errno {data.get('errno')}"),
                    "errno": data.get('errno')
                }
                
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    # ========================================
    # MÉTODO PRINCIPAL: Auto-selección
    # ========================================
    
    def get_file_info(self, url: str, password: str = "") -> Dict:
        """
        Obtiene información de archivo/carpeta usando el mejor método disponible.
        
        Orden de prioridad:
        1. API 1024tera.com (PRINCIPAL - más confiable)
        2. API directa terabox.com (fallback)
        
        Args:
            url: URL de TeraBox
            password: Contraseña si el enlace está protegido
            
        Returns:
            Dict con información del recurso
        """
        if not self.is_terabox_url(url):
            return {"ok": False, "error": "URL no es de TeraBox"}
        
        # Verificar que tenemos cookies
        if not self.cookie_dict and not self.cookie_string:
            logger.warning("No hay cookies configuradas - la descarga puede fallar")
        
        # Método 1: API 1024tera.com (PRINCIPAL - funciona mejor)
        logger.info("Intentando método 1024tera.com...")
        result = self.get_info_via_1024tera(url, password)
        if result.get('ok'):
            return result
        
        logger.info(f"1024tera falló ({result.get('error')}), intentando método directo terabox.com...")
        
        # Método 2: API Directa terabox.com (fallback)
        result = self.get_info_direct(url)
        if result.get('ok'):
            return result
        
        return {"ok": False, "error": "Todos los métodos de obtención de información fallaron"}
    
    def get_download_link(self, url: str, password: str = "", fs_id: str = None) -> Dict:
        """
        Obtiene enlace de descarga directa.
        
        El método 1024tera.com ya incluye dlink en la respuesta,
        por lo que no necesitamos hacer llamadas adicionales.
        
        Args:
            url: URL de TeraBox
            password: Contraseña si aplica
            fs_id: ID específico del archivo (opcional, usa el primero si no se especifica)
            
        Returns:
            Dict con download_link, file_name, file_size, etc.
        """
        # Primero obtener información del recurso
        info = self.get_file_info(url, password)
        
        if info.get('ok') == False:
            return info
        
        # Extraer archivos de la respuesta
        files = self._extract_files_from_info(info)
        
        if not files:
            return {"ok": False, "error": "No se encontraron archivos en el recurso"}
        
        # Seleccionar archivo objetivo
        target_file = None
        if fs_id:
            target_file = next((f for f in files if str(f.get('fs_id')) == str(fs_id)), None)
        
        if not target_file:
            # Usar el primer archivo (no carpeta)
            target_file = next((f for f in files if not f.get('is_dir')), files[0])
        
        # El método 1024tera ya incluye dlink en la respuesta
        dlink = target_file.get('dlink')
        
        if dlink:
            logger.info(f"Enlace de descarga obtenido para: {target_file.get('filename') or target_file.get('server_filename')}")
            return {
                "ok": True,
                "download_link": dlink,
                "file_name": target_file.get('filename') or target_file.get('server_filename'),
                "file_size": target_file.get('size'),
                "fs_id": target_file.get('fs_id'),
                "all_files": files,
                "_method": info.get('_method', 'direct')
            }
        
        # Si el archivo seleccionado es una carpeta, obtener su contenido
        if target_file.get('is_dir') or target_file.get('isdir') == '1':
            logger.info(f"El item seleccionado es una carpeta: {target_file.get('path')}")
            
            folder_result = self.get_folder_contents(
                short_url=info.get('_short_url', self._extract_short_url(url)),
                path=target_file.get('path'),
                js_token=info.get('_js_token', ''),
                log_id=info.get('_log_id', '')
            )
            
            if folder_result.get('ok') and folder_result.get('list'):
                # Buscar primer archivo en la carpeta
                for item in folder_result['list']:
                    if item.get('isdir') != '1' and item.get('dlink'):
                        return {
                            "ok": True,
                            "download_link": item.get('dlink'),
                            "file_name": item.get('server_filename'),
                            "file_size": item.get('size'),
                            "fs_id": item.get('fs_id'),
                            "all_files": folder_result['list'],
                            "_method": "folder_content"
                        }
        
        return {"ok": False, "error": "No se pudo obtener enlace de descarga - archivo no tiene dlink"}
    
    def _extract_files_from_info(self, info: Dict) -> List[Dict]:
        """Extrae lista de archivos de la respuesta de info."""
        files = []
        
        def extract_recursive(item: Dict, path: str = ""):
            """Extrae archivos recursivamente de carpetas."""
            # Detectar si es directorio - 1024tera usa "isdir" como string "0" o "1"
            is_dir = (
                item.get('is_dir') == 1 or 
                item.get('is_dir') == '1' or 
                item.get('isdir') == 1 or 
                item.get('isdir') == '1'
            )
            
            filename = item.get('filename') or item.get('server_filename', '')
            
            if is_dir:
                children = item.get('children', [])
                new_path = f"{path}/{filename}" if path else filename
                
                # Agregar la carpeta también (para poder navegar)
                file_info = {
                    'fs_id': item.get('fs_id'),
                    'filename': filename,
                    'server_filename': item.get('server_filename'),
                    'size': item.get('size', 0),
                    'path': item.get('path', new_path),
                    'dlink': item.get('dlink'),
                    'is_dir': True,
                    'isdir': '1',
                }
                files.append(file_info)
                
                for child in children:
                    extract_recursive(child, new_path)
            else:
                file_info = {
                    'fs_id': item.get('fs_id'),
                    'filename': filename,
                    'server_filename': item.get('server_filename'),
                    'size': item.get('size'),
                    'path': item.get('path', path),
                    'dlink': item.get('dlink'),
                    'category': item.get('category'),
                    'md5': item.get('md5'),
                    'is_dir': False,
                    'isdir': '0',
                }
                files.append(file_info)
        
        # Procesar lista de items
        items = info.get('list', [])
        for item in items:
            extract_recursive(item)
        
        return files
    
    def get_all_files(self, url: str, password: str = "") -> List[Dict]:
        """
        Obtiene información de todos los archivos en un recurso compartido.
        
        Args:
            url: URL de TeraBox
            password: Contraseña si aplica
            
        Returns:
            Lista de dicts con información de cada archivo
        """
        info = self.get_file_info(url, password)
        
        if info.get('ok') == False:
            return []
        
        files = self._extract_files_from_info(info)
        
        # Enriquecer con metadatos del share
        for f in files:
            f['shareid'] = info.get('shareid')
            f['uk'] = info.get('uk')
            f['sign'] = info.get('sign')
            f['timestamp'] = info.get('timestamp')
        
        return files
    
    def download_file(
        self,
        url: str,
        output_path: str,
        password: str = "",
        fs_id: str = None,
        callback = None
    ) -> Dict:
        """
        Descarga un archivo de TeraBox.
        
        Args:
            url: URL de TeraBox
            output_path: Directorio donde guardar el archivo
            password: Contraseña si aplica
            fs_id: ID específico del archivo (opcional)
            callback: Función callback para progreso (downloaded, total, percentage)
            
        Returns:
            Dict con file_path o error
        """
        # Obtener enlace de descarga
        result = self.get_download_link(url, password, fs_id)
        
        if not result.get('ok'):
            return result
        
        download_link = result.get('download_link')
        filename = result.get('file_name', 'terabox_download')
        
        # Preparar path de salida
        os.makedirs(output_path, exist_ok=True)
        file_path = os.path.join(output_path, filename)
        
        try:
            logger.info(f"Descargando: {filename}")
            
            # Headers para la descarga
            download_headers = {
                'User-Agent': self.session.headers['User-Agent'],
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'es-ES,es;q=0.8,en;q=0.5',
                'Referer': 'https://www.terabox.com/',
                'Connection': 'keep-alive',
            }
            
            # Stream download
            with self.session.get(download_link, headers=download_headers, stream=True, timeout=300) as response:
                response.raise_for_status()
                
                total_size = int(response.headers.get('content-length', 0))
                if total_size == 0:
                    total_size = result.get('file_size', 0)
                
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
            
            # Verificar descarga
            actual_size = os.path.getsize(file_path)
            if actual_size == 0:
                os.remove(file_path)
                return {"ok": False, "error": "Archivo descargado está vacío"}
            
            logger.info(f"✓ Descarga completada: {file_path} ({actual_size} bytes)")
            
            return {
                "ok": True,
                "file_path": file_path,
                "file_name": filename,
                "file_size": actual_size
            }
            
        except Exception as e:
            logger.error(f"Error descargando: {e}")
            return {"ok": False, "error": str(e)}


# ========================================
# Versión Async para integración con FastAPI
# ========================================

class TeraBoxBypassAsync:
    """Versión asíncrona del bypass de TeraBox."""
    
    TERABOX_DOMAINS = TeraBoxBypass.TERABOX_DOMAINS
    PREFERRED_DOMAIN = TeraBoxBypass.PREFERRED_DOMAIN
    
    def __init__(self, cookies: List[Dict] = None, cookie_string: str = None, cookie_dict: Dict = None):
        self.cookies = cookies or []
        self.cookie_dict = cookie_dict or {}
        
        if self.cookies and not self.cookie_dict:
            self.cookie_dict = {c['name']: c['value'] for c in self.cookies if c.get('name') and c.get('value')}
        
        self.cookie_string = cookie_string or self._cookies_to_string(self.cookies)
        self._session: Optional[aiohttp.ClientSession] = None
        
    def _cookies_to_string(self, cookies: List[Dict]) -> str:
        if not cookies:
            return ""
        return "; ".join(f"{c['name']}={c['value']}" for c in cookies if c.get('name') and c.get('value'))
    
    @staticmethod
    def _find_between(string: str, start: str, end: str) -> str:
        start_index = string.find(start)
        if start_index == -1:
            return ""
        start_index += len(start)
        end_index = string.find(end, start_index)
        if end_index == -1:
            return ""
        return string[start_index:end_index]
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': '*/*',
                'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
            }
            
            # Crear jar de cookies
            cookie_jar = aiohttp.CookieJar()
            
            self._session = aiohttp.ClientSession(headers=headers, cookie_jar=cookie_jar)
            
            # Agregar cookies
            if self.cookie_dict:
                for name, value in self.cookie_dict.items():
                    self._session.cookie_jar.update_cookies({name: value})
                    
        return self._session
    
    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
    
    def _extract_short_url(self, url: str) -> Optional[str]:
        if '/s/' in url:
            match = re.search(r'/s/(1?)([a-zA-Z0-9_-]+)', url)
            if match:
                return match.group(2)
        if 'surl=' in url:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            if 'surl' in params:
                return params['surl'][0]
        return None
    
    @classmethod
    def is_terabox_url(cls, url: str) -> bool:
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            return any(d in domain for d in cls.TERABOX_DOMAINS)
        except:
            return False
    
    async def get_info_via_1024tera(self, url: str, password: str = "") -> Dict:
        """Obtiene información del archivo usando 1024tera.com (async)."""
        short_url = self._extract_short_url(url)
        if not short_url:
            return {"ok": False, "error": "No se pudo extraer short_url"}
        
        session = await self._get_session()
        
        try:
            # Paso 1: Visitar la página para obtener tokens
            page_url = f"https://{self.PREFERRED_DOMAIN}/sharing/link?surl={short_url}"
            
            async with session.get(page_url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status != 200:
                    return {"ok": False, "error": f"HTTP {response.status}"}
                
                html = await response.text()
            
            # Extraer tokens
            js_token = self._find_between(html, 'fn%28%22', '%22%29')
            log_id = self._find_between(html, 'dp-logid=', '&')
            
            # Paso 2: Llamar a la API
            api_url = f"https://{self.PREFERRED_DOMAIN}/share/list"
            
            params = {
                'app_id': '250528',
                'web': '1',
                'channel': 'dubox',
                'clienttype': '0',
                'jsToken': js_token or '',
                'dplogid': log_id or '',
                'page': '1',
                'num': '100',
                'order': 'time',
                'desc': '1',
                'site_referer': page_url,
                'shorturl': short_url,
                'root': '1'
            }
            
            async with session.get(api_url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status != 200:
                    return {"ok": False, "error": f"API HTTP {response.status}"}
                
                data = await response.json()
            
            if data.get('errno') == 0:
                return {
                    "ok": True,
                    "list": data.get('list', []),
                    "shareid": data.get('shareid'),
                    "uk": data.get('uk'),
                    "sign": data.get('sign'),
                    "timestamp": data.get('timestamp'),
                    "_method": "1024tera",
                    "_short_url": short_url,
                }
            else:
                return {"ok": False, "error": data.get('errmsg', f"errno {data.get('errno')}")}
                
        except Exception as e:
            logger.error(f"Error en 1024tera async: {e}")
            return {"ok": False, "error": str(e)}
    
    async def get_file_info(self, url: str, password: str = "") -> Dict:
        """Obtiene información del recurso (async)."""
        if not self.is_terabox_url(url):
            return {"ok": False, "error": "URL no es de TeraBox"}
        
        return await self.get_info_via_1024tera(url, password)
    
    async def get_download_link(self, url: str, password: str = "", fs_id: str = None) -> Dict:
        """Obtiene enlace de descarga directa (async)."""
        info = await self.get_file_info(url, password)
        
        if info.get('ok') == False:
            return info
        
        files = self._extract_files_from_info(info)
        
        if not files:
            return {"ok": False, "error": "No se encontraron archivos"}
        
        target_file = None
        if fs_id:
            target_file = next((f for f in files if str(f.get('fs_id')) == str(fs_id)), None)
        if not target_file:
            target_file = next((f for f in files if not f.get('is_dir')), files[0])
        
        dlink = target_file.get('dlink')
        if dlink:
            return {
                "ok": True,
                "download_link": dlink,
                "file_name": target_file.get('filename') or target_file.get('server_filename'),
                "file_size": target_file.get('size'),
                "fs_id": target_file.get('fs_id'),
                "all_files": files
            }
        
        return {"ok": False, "error": "No se pudo obtener enlace de descarga"}
    
    def _extract_files_from_info(self, info: Dict) -> List[Dict]:
        """Extrae lista de archivos de la respuesta de info."""
        files = []
        
        def extract_recursive(item: Dict, path: str = ""):
            is_dir = (
                item.get('is_dir') == 1 or 
                item.get('is_dir') == '1' or 
                item.get('isdir') == 1 or 
                item.get('isdir') == '1'
            )
            
            filename = item.get('filename') or item.get('server_filename', '')
            
            file_info = {
                'fs_id': item.get('fs_id'),
                'filename': filename,
                'server_filename': item.get('server_filename'),
                'size': item.get('size'),
                'path': item.get('path', path),
                'dlink': item.get('dlink'),
                'is_dir': is_dir,
            }
            files.append(file_info)
            
            if is_dir:
                children = item.get('children', [])
                new_path = f"{path}/{filename}" if path else filename
                for child in children:
                    extract_recursive(child, new_path)
        
        items = info.get('list', [])
        for item in items:
            extract_recursive(item)
        
        return files
    
    async def get_all_files(self, url: str, password: str = "") -> List[Dict]:
        """Obtiene todos los archivos (async)."""
        info = await self.get_file_info(url, password)
        
        if info.get('ok') == False:
            return []
        
        files = self._extract_files_from_info(info)
        
        for f in files:
            f['shareid'] = info.get('shareid')
            f['uk'] = info.get('uk')
            f['sign'] = info.get('sign')
            f['timestamp'] = info.get('timestamp')
        
        return files


# ========================================
# Funciones de utilidad
# ========================================

def get_terabox_download_link(url: str, cookies: List[Dict] = None) -> Optional[str]:
    """
    Función de utilidad para obtener enlace de descarga de TeraBox.
    
    Args:
        url: URL de TeraBox
        cookies: Cookies opcionales
        
    Returns:
        URL de descarga directa o None
    """
    bypass = TeraBoxBypass(cookies=cookies)
    result = bypass.get_download_link(url)
    
    if result.get('ok'):
        return result.get('download_link')
    
    logger.error(f"Error obteniendo enlace: {result.get('error')}")
    return None


def get_terabox_file_info(url: str, cookies: List[Dict] = None) -> Dict:
    """
    Función de utilidad para obtener información de archivo de TeraBox.
    
    Args:
        url: URL de TeraBox
        cookies: Cookies opcionales
        
    Returns:
        Dict con información del archivo
    """
    bypass = TeraBoxBypass(cookies=cookies)
    return bypass.get_file_info(url)


async def get_terabox_download_link_async(url: str, cookies: List[Dict] = None) -> Optional[str]:
    """Versión async de get_terabox_download_link."""
    bypass = TeraBoxBypassAsync(cookies=cookies)
    try:
        result = await bypass.get_download_link(url)
        if result.get('ok'):
            return result.get('download_link')
        return None
    finally:
        await bypass.close()
