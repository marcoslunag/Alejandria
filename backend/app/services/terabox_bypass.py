"""
TeraBox Bypass Service - Solución robusta para descargas de TeraBox
Utiliza múltiples métodos de bypass incluyendo APIs proxy de terceros
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
    1. API proxy de terceros (qtcloud workers)
    2. API directa con cookies (fallback)
    3. Dominio alternativo 1024tera.com
    """
    
    # APIs proxy conocidas que funcionan
    PROXY_APIS = [
        {
            "name": "qtcloud",
            "info_url": "https://terabox-dl.qtcloud.workers.dev/api/get-info",
            "download_url": "https://terabox-dl.qtcloud.workers.dev/api/get-download",
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
    
    def __init__(self, cookies: List[Dict] = None, cookie_string: str = None):
        """
        Inicializa el bypass de TeraBox.
        
        Args:
            cookies: Lista de cookies en formato dict (del navegador)
            cookie_string: String de cookies formato "name=value; name2=value2"
        """
        self.cookies = cookies or []
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
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'DNT': '1',
        })
        if self.cookie_string:
            self.session.headers['Cookie'] = self.cookie_string
            
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
    # MÉTODO 1: API Proxy (Recomendado)
    # ========================================
    
    def get_info_via_proxy(self, url: str, password: str = "") -> Dict:
        """
        Obtiene información del archivo usando API proxy.
        
        Este método es el más confiable ya que usa servidores proxy
        que mantienen sesiones válidas de TeraBox.
        
        Args:
            url: URL de TeraBox
            password: Contraseña si el enlace está protegido
            
        Returns:
            Dict con información del archivo/carpeta
        """
        short_url = self._extract_short_url(url)
        if not short_url:
            return {"ok": False, "error": "No se pudo extraer short_url de la URL"}
        
        for api in self.PROXY_APIS:
            try:
                logger.info(f"Intentando API proxy: {api['name']}")
                
                params = {
                    'shorturl': short_url,
                    'pwd': password
                }
                
                response = self.session.get(
                    api['info_url'],
                    params=params,
                    timeout=30
                )
                
                if not response.ok:
                    logger.warning(f"API {api['name']} retornó status {response.status_code}")
                    continue
                
                data = response.json()
                
                if data.get('ok') == False:
                    logger.warning(f"API {api['name']} error: {data.get('message')}")
                    continue
                
                # Éxito - agregar metadata de la API usada
                data['_api_used'] = api['name']
                data['_short_url'] = short_url
                
                logger.info(f"✓ Información obtenida via {api['name']}")
                return data
                
            except requests.exceptions.Timeout:
                logger.warning(f"Timeout en API {api['name']}")
                continue
            except requests.exceptions.RequestException as e:
                logger.warning(f"Error de red en API {api['name']}: {e}")
                continue
            except json.JSONDecodeError:
                logger.warning(f"Respuesta inválida de API {api['name']}")
                continue
        
        return {"ok": False, "error": "Todas las APIs proxy fallaron"}
    
    def get_download_link_via_proxy(
        self,
        short_url: str,
        shareid: str,
        uk: str,
        sign: str,
        timestamp: str,
        fs_id: str,
        password: str = ""
    ) -> Optional[str]:
        """
        Obtiene enlace de descarga directa usando API proxy.
        
        Args:
            short_url: Identificador corto del recurso
            shareid: ID del share (de get_info)
            uk: User key (de get_info)
            sign: Firma (de get_info)
            timestamp: Timestamp (de get_info)
            fs_id: File system ID del archivo específico
            password: Contraseña si aplica
            
        Returns:
            URL de descarga directa o None
        """
        for api in self.PROXY_APIS:
            try:
                logger.info(f"Obteniendo enlace de descarga via {api['name']}")
                
                body = {
                    'shareid': str(shareid),
                    'uk': str(uk),
                    'sign': sign,
                    'timestamp': str(timestamp),
                    'fs_id': str(fs_id),
                }
                
                response = self.session.post(
                    api['download_url'],
                    json=body,
                    timeout=30
                )
                
                if not response.ok:
                    logger.warning(f"API {api['name']} retornó status {response.status_code}")
                    continue
                
                data = response.json()
                
                if data.get('ok') == False:
                    logger.warning(f"API {api['name']} error: {data.get('message')}")
                    continue
                
                download_link = data.get('downloadLink')
                if download_link:
                    logger.info(f"✓ Enlace de descarga obtenido via {api['name']}")
                    return download_link
                    
            except Exception as e:
                logger.warning(f"Error en API {api['name']}: {e}")
                continue
        
        return None
    
    # ========================================
    # MÉTODO 2: API Directa (Fallback)
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
        
        Intenta primero API proxy (más confiable), luego API directa.
        
        Args:
            url: URL de TeraBox
            password: Contraseña si el enlace está protegido
            
        Returns:
            Dict con información del recurso
        """
        if not self.is_terabox_url(url):
            return {"ok": False, "error": "URL no es de TeraBox"}
        
        # Método 1: API Proxy (recomendado)
        result = self.get_info_via_proxy(url, password)
        if result.get('ok') != False:
            return result
        
        logger.info("API proxy falló, intentando método directo...")
        
        # Método 2: API Directa (requiere cookies)
        if self.cookie_string:
            result = self.get_info_direct(url)
            if result.get('ok'):
                return result
        
        return {"ok": False, "error": "Todos los métodos de obtención de información fallaron"}
    
    def get_download_link(self, url: str, password: str = "", fs_id: str = None) -> Dict:
        """
        Obtiene enlace de descarga directa.
        
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
            target_file = files[0]  # Usar el primero
        
        # Obtener enlace de descarga
        short_url = self._extract_short_url(url)
        
        download_link = self.get_download_link_via_proxy(
            short_url=short_url,
            shareid=info.get('shareid'),
            uk=info.get('uk'),
            sign=info.get('sign'),
            timestamp=info.get('timestamp'),
            fs_id=target_file.get('fs_id'),
            password=password
        )
        
        if download_link:
            return {
                "ok": True,
                "download_link": download_link,
                "file_name": target_file.get('filename') or target_file.get('server_filename'),
                "file_size": target_file.get('size'),
                "fs_id": target_file.get('fs_id'),
                "all_files": files
            }
        
        # Fallback: intentar obtener dlink directo si está en la info
        if target_file.get('dlink'):
            return {
                "ok": True,
                "download_link": target_file.get('dlink'),
                "file_name": target_file.get('filename') or target_file.get('server_filename'),
                "file_size": target_file.get('size'),
                "fs_id": target_file.get('fs_id'),
                "all_files": files,
                "_method": "dlink_direct"
            }
        
        return {"ok": False, "error": "No se pudo obtener enlace de descarga"}
    
    def _extract_files_from_info(self, info: Dict) -> List[Dict]:
        """Extrae lista de archivos de la respuesta de info."""
        files = []
        
        def extract_recursive(item: Dict, path: str = ""):
            """Extrae archivos recursivamente de carpetas."""
            is_dir = item.get('is_dir') == 1 or item.get('is_dir') == '1' or item.get('isdir') == 1
            
            if is_dir:
                children = item.get('children', [])
                folder_name = item.get('filename') or item.get('server_filename', '')
                new_path = f"{path}/{folder_name}" if path else folder_name
                
                for child in children:
                    extract_recursive(child, new_path)
            else:
                file_info = {
                    'fs_id': item.get('fs_id'),
                    'filename': item.get('filename') or item.get('server_filename'),
                    'size': item.get('size'),
                    'path': path,
                    'dlink': item.get('dlink'),
                    'category': item.get('category'),
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
    
    PROXY_APIS = TeraBoxBypass.PROXY_APIS
    TERABOX_DOMAINS = TeraBoxBypass.TERABOX_DOMAINS
    
    def __init__(self, cookies: List[Dict] = None, cookie_string: str = None):
        self.cookies = cookies or []
        self.cookie_string = cookie_string or self._cookies_to_string(self.cookies)
        self._session: Optional[aiohttp.ClientSession] = None
        
    def _cookies_to_string(self, cookies: List[Dict]) -> str:
        if not cookies:
            return ""
        return "; ".join(f"{c['name']}={c['value']}" for c in cookies if c.get('name') and c.get('value'))
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
            }
            if self.cookie_string:
                headers['Cookie'] = self.cookie_string
                
            self._session = aiohttp.ClientSession(headers=headers)
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
    
    async def get_info_via_proxy(self, url: str, password: str = "") -> Dict:
        """Obtiene información del archivo usando API proxy (async)."""
        short_url = self._extract_short_url(url)
        if not short_url:
            return {"ok": False, "error": "No se pudo extraer short_url"}
        
        session = await self._get_session()
        
        for api in self.PROXY_APIS:
            try:
                params = {'shorturl': short_url, 'pwd': password}
                
                async with session.get(api['info_url'], params=params, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status != 200:
                        continue
                    
                    data = await response.json()
                    
                    if data.get('ok') == False:
                        continue
                    
                    data['_api_used'] = api['name']
                    data['_short_url'] = short_url
                    return data
                    
            except Exception as e:
                logger.warning(f"Error en API {api['name']}: {e}")
                continue
        
        return {"ok": False, "error": "Todas las APIs proxy fallaron"}
    
    async def get_download_link_via_proxy(
        self,
        short_url: str,
        shareid: str,
        uk: str,
        sign: str,
        timestamp: str,
        fs_id: str,
        password: str = ""
    ) -> Optional[str]:
        """Obtiene enlace de descarga directa usando API proxy (async)."""
        session = await self._get_session()
        
        for api in self.PROXY_APIS:
            try:
                body = {
                    'shareid': str(shareid),
                    'uk': str(uk),
                    'sign': sign,
                    'timestamp': str(timestamp),
                    'fs_id': str(fs_id),
                }
                
                async with session.post(api['download_url'], json=body, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status != 200:
                        continue
                    
                    data = await response.json()
                    
                    if data.get('ok') == False:
                        continue
                    
                    return data.get('downloadLink')
                    
            except Exception as e:
                logger.warning(f"Error en API {api['name']}: {e}")
                continue
        
        return None
    
    async def get_file_info(self, url: str, password: str = "") -> Dict:
        """Obtiene información del recurso (async)."""
        if not self.is_terabox_url(url):
            return {"ok": False, "error": "URL no es de TeraBox"}
        
        return await self.get_info_via_proxy(url, password)
    
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
            target_file = files[0]
        
        short_url = self._extract_short_url(url)
        
        download_link = await self.get_download_link_via_proxy(
            short_url=short_url,
            shareid=info.get('shareid'),
            uk=info.get('uk'),
            sign=info.get('sign'),
            timestamp=info.get('timestamp'),
            fs_id=target_file.get('fs_id'),
            password=password
        )
        
        if download_link:
            return {
                "ok": True,
                "download_link": download_link,
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
            is_dir = item.get('is_dir') == 1 or item.get('is_dir') == '1' or item.get('isdir') == 1
            
            if is_dir:
                children = item.get('children', [])
                folder_name = item.get('filename') or item.get('server_filename', '')
                new_path = f"{path}/{folder_name}" if path else folder_name
                
                for child in children:
                    extract_recursive(child, new_path)
            else:
                file_info = {
                    'fs_id': item.get('fs_id'),
                    'filename': item.get('filename') or item.get('server_filename'),
                    'size': item.get('size'),
                    'path': path,
                    'dlink': item.get('dlink'),
                }
                files.append(file_info)
        
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
