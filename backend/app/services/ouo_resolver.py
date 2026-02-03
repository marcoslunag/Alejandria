"""
OUO.io Link Resolver
Resuelve enlaces acortados de OUO.io para obtener el enlace final (generalmente Fireload)
Usa la librería bypass-ouo para el bypass
"""

import asyncio
import logging
from typing import Optional, Dict
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# Thread pool para ejecutar bypass síncrono
_executor = ThreadPoolExecutor(max_workers=2)


def _bypass_ouo_sync(ouo_url: str) -> Optional[str]:
    """
    Bypass de OUO.io usando la librería bypass-ouo
    Ejecutado en thread pool porque es síncrono

    La función devuelve un diccionario:
    {
        'original_link': 'https://ouo.io/go/XXX',
        'bypassed_link': 'https://final-url.com'
    }
    """
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

        logger.warning(f"OUO: Bypass returned invalid result: {result}")
        return None

    except Exception as e:
        logger.error(f"OUO: Bypass error: {e}")
        return None


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
