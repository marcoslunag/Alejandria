"""
OUO.io Link Resolver
Resuelve enlaces acortados de OUO.io para obtener el enlace final (generalmente Fireload)
Usa la librería bypass-ouo para el bypass, con fallback manual
"""

import asyncio
import logging
import re
import time
from typing import Optional, Dict
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# Thread pool para ejecutar bypass síncrono
_executor = ThreadPoolExecutor(max_workers=2)


def _bypass_ouo_manual(ouo_url: str) -> Optional[str]:
    """
    Bypass manual de OUO.io usando requests y curl_cffi
    Fallback cuando la librería bypass-ouo falla
    """
    try:
        from curl_cffi import requests as cffi_requests
        from bs4 import BeautifulSoup
        import re
        
        logger.info(f"OUO: Trying manual bypass for {ouo_url}")
        
        session = cffi_requests.Session(impersonate="chrome110")
        
        # Primera petición para obtener el formulario
        resp1 = session.get(ouo_url, timeout=30)
        
        if resp1.status_code != 200:
            logger.warning(f"OUO: First request failed with {resp1.status_code}")
            return None
        
        # Buscar el enlace final directamente en la respuesta
        # A veces OUO.io tiene el enlace en un meta refresh o redirect
        html = resp1.text
        
        # Buscar patrones comunes de redirección
        patterns = [
            r'href=["\']?(https?://(?:www\.)?fireload\.com[^"\'>\s]+)',
            r'href=["\']?(https?://(?:www\.)?mediafire\.com[^"\'>\s]+)',
            r'href=["\']?(https?://(?:www\.)?mega\.nz[^"\'>\s]+)',
            r'href=["\']?(https?://[^"\'>\s]+\.rar[^"\'>\s]*)',
            r'href=["\']?(https?://[^"\'>\s]+\.zip[^"\'>\s]*)',
            r'action=["\']?(https?://[^"\'>\s]+)',
            r'window\.location\s*=\s*["\']?(https?://[^"\'>\s]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                url = match.group(1)
                if 'ouo.io' not in url.lower() and 'ouo.press' not in url.lower():
                    logger.info(f"OUO: Found direct link via pattern: {url[:60]}...")
                    return url
        
        # Si no encontramos el enlace directo, intentar el flujo normal
        soup = BeautifulSoup(html, 'html.parser')
        
        # Buscar el formulario de bypass
        form = soup.find('form', {'id': 'form-bypass'}) or soup.find('form')
        
        if form:
            action = form.get('action', '')
            if action and action.startswith('http') and 'ouo' not in action.lower():
                logger.info(f"OUO: Found form action: {action[:60]}...")
                return action
            
            # Intentar enviar el formulario
            form_data = {}
            for inp in form.find_all('input'):
                name = inp.get('name')
                value = inp.get('value', '')
                if name:
                    form_data[name] = value
            
            if form_data:
                # Esperar un poco (OUO tiene un timer)
                time.sleep(2)
                
                post_url = action if action.startswith('http') else ouo_url
                resp2 = session.post(post_url, data=form_data, timeout=30, allow_redirects=True)
                
                if resp2.status_code == 200:
                    # Buscar el enlace final en la respuesta
                    final_html = resp2.text
                    for pattern in patterns:
                        match = re.search(pattern, final_html, re.IGNORECASE)
                        if match:
                            url = match.group(1)
                            if 'ouo.io' not in url.lower():
                                logger.info(f"OUO: Found link after form submit: {url[:60]}...")
                                return url
        
        logger.warning(f"OUO: Manual bypass could not find final URL")
        return None
        
    except Exception as e:
        logger.error(f"OUO: Manual bypass error: {e}")
        return None


def _bypass_ouo_sync(ouo_url: str) -> Optional[str]:
    """
    Bypass de OUO.io usando la librería bypass-ouo
    Ejecutado en thread pool porque es síncrono
    Con fallback a método manual si la librería falla
    """
    # Primero intentar con la librería
    try:
        from bypass_ouo import bypass_ouo

        logger.info(f"OUO: Bypassing {ouo_url}")
        result = bypass_ouo(ouo_url)

        logger.debug(f"OUO: Raw result: {result}")

        # El resultado es un diccionario con 'bypassed_link'
        if isinstance(result, dict):
            bypassed = result.get('bypassed_link')
            if bypassed and 'http' in bypassed:
                logger.info(f"OUO: Bypass successful: {bypassed[:60]}...")
                return bypassed
        elif isinstance(result, str) and 'http' in result:
            logger.info(f"OUO: Bypass successful (string): {result[:60]}...")
            return result

        logger.warning(f"OUO: Library returned invalid result: {result}")

    except Exception as e:
        logger.error(f"OUO: Library bypass error: {e}")
    
    # Fallback a método manual
    logger.info(f"OUO: Trying manual fallback...")
    return _bypass_ouo_manual(ouo_url)


class OUOResolver:
    """
    Resolver para enlaces de OUO.io usando bypass-ouo
    """

    def __init__(self):
        pass

    async def resolve(self, ouo_url: str, timeout: int = 60000) -> Dict:
        """
        Resuelve un enlace de OUO.io de forma asíncrona

        Args:
            ouo_url: URL de OUO.io
            timeout: Tiempo máximo en ms

        Returns:
            Dict con {ok, final_url, host} o {ok: False, error}
        """
        logger.info(f"OUO: Resolving {ouo_url}")

        loop = asyncio.get_event_loop()

        try:
            # Ejecutar el bypass síncrono en un thread pool
            result = await loop.run_in_executor(
                _executor,
                _bypass_ouo_sync,
                ouo_url
            )

            if result:
                # Identificar el host
                final_host = 'unknown'
                result_lower = result.lower()
                if 'fireload' in result_lower:
                    final_host = 'fireload'
                elif 'mediafire' in result_lower:
                    final_host = 'mediafire'
                elif 'mega.nz' in result_lower:
                    final_host = 'mega'
                elif '1fichier' in result_lower:
                    final_host = '1fichier'
                elif 'drive.google' in result_lower:
                    final_host = 'google_drive'

                logger.info(f"OUO: Successfully resolved to {final_host}: {result}")
                return {
                    "ok": True,
                    "final_url": result,
                    "host": final_host
                }

            return {"ok": False, "error": "No se pudo resolver el enlace de OUO.io"}

        except Exception as e:
            logger.error(f"OUO: Error: {e}")
            return {"ok": False, "error": str(e)}

    async def close(self):
        """Cleanup"""
        pass


# Singleton instance
_resolver_instance: Optional[OUOResolver] = None


async def get_ouo_resolver() -> OUOResolver:
    """Obtiene o crea la instancia singleton del resolver"""
    global _resolver_instance
    if _resolver_instance is None:
        _resolver_instance = OUOResolver()
    return _resolver_instance


async def resolve_ouo_link(ouo_url: str) -> Optional[str]:
    """
    Función auxiliar para resolver un enlace de OUO.io

    Args:
        ouo_url: URL de OUO.io

    Returns:
        URL final o None si falla
    """
    try:
        resolver = await get_ouo_resolver()
        result = await resolver.resolve(ouo_url)

        if result.get("ok"):
            return result.get("final_url")

        logger.error(f"OUO resolve error: {result.get('error')}")
        return None
    except Exception as e:
        logger.error(f"Error in resolve_ouo_link: {e}")
        return None
