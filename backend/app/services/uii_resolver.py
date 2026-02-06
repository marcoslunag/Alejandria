"""
UII.io Link Resolver
Resuelve enlaces acortados de uii.io/wordcount.im para obtener el enlace final
Soporta múltiples métodos de bypass incluyendo 2captcha
"""

import asyncio
import logging
import os
import re
import time
from typing import Optional, Dict
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# Thread pool para operaciones síncronas
_executor = ThreadPoolExecutor(max_workers=2)

# API key para 2captcha (opcional)
CAPTCHA_API_KEY = os.environ.get('CAPTCHA_API_KEY', '')

# FlareSolverr URL (opcional) - para resolver desafíos de Cloudflare
FLARESOLVERR_URL = os.environ.get('FLARESOLVERR_URL', '')


def _resolve_with_curl_cffi(uii_url: str) -> Optional[str]:
    """
    Intenta resolver uii.io usando curl_cffi con impersonación de navegador

    Args:
        uii_url: URL de uii.io

    Returns:
        URL final o None
    """
    try:
        from curl_cffi import requests as cffi_requests
        from bs4 import BeautifulSoup

        logger.info(f"UII: Trying curl_cffi bypass for {uii_url}")

        session = cffi_requests.Session(impersonate="chrome110")

        # Primera petición
        resp1 = session.get(uii_url, timeout=30, allow_redirects=True)

        if resp1.status_code != 200:
            logger.warning(f"UII: First request failed with {resp1.status_code}")
            return None

        current_url = str(resp1.url)
        html = resp1.text

        logger.info(f"UII: Redirected to {current_url}")

        # Buscar enlaces directos de descarga en la página
        download_patterns = [
            r'(https?://(?:www\.)?terabox\.com[^\s"<>\']+)',
            r'(https?://(?:www\.)?1024terabox\.com[^\s"<>\']+)',
            r'(https?://(?:www\.)?mega\.nz[^\s"<>\']+)',
            r'(https?://(?:www\.)?mediafire\.com[^\s"<>\']+)',
            r'(https?://(?:www\.)?drive\.google\.com[^\s"<>\']+)',
            r'(https?://(?:www\.)?fireload\.com[^\s"<>\']+)',
        ]

        for pattern in download_patterns:
            match = re.search(pattern, html)
            if match:
                found_url = match.group(1)
                logger.info(f"UII: Found direct download link: {found_url[:60]}...")
                return found_url

        # Buscar el formulario link-view
        soup = BeautifulSoup(html, 'html.parser')
        form = soup.find('form', {'id': 'link-view'})

        if not form:
            logger.warning("UII: No link-view form found")
            return None

        # Extraer datos del formulario
        action = form.get('action', '')
        form_data = {}
        for inp in form.find_all('input'):
            name = inp.get('name')
            value = inp.get('value', '')
            if name:
                form_data[name] = value

        # Construir URL del POST
        post_url = urljoin(current_url, action)

        logger.info(f"UII: Submitting form to {post_url}")

        # Esperar un poco (estos sitios tienen timers)
        time.sleep(3)

        # Enviar el formulario
        resp2 = session.post(
            post_url,
            data=form_data,
            timeout=30,
            allow_redirects=True,
            headers={
                'Origin': 'https://wordcount.im',
                'Referer': current_url,
            }
        )

        if resp2.status_code == 200:
            html2 = resp2.text

            # Buscar el enlace final
            for pattern in download_patterns:
                match = re.search(pattern, html2)
                if match:
                    found_url = match.group(1)
                    logger.info(f"UII: Found download link after POST: {found_url[:60]}...")
                    return found_url

            # Buscar go_next link
            soup2 = BeautifulSoup(html2, 'html.parser')
            go_next = soup2.find('a', {'id': 'go_next'})
            if go_next and go_next.get('href'):
                next_url = go_next.get('href')
                if next_url.startswith('http') and 'wordcount' not in next_url.lower() and 'uii' not in next_url.lower():
                    logger.info(f"UII: Found go_next link: {next_url[:60]}...")
                    return next_url

            # Si hay otro form, puede que necesitemos más pasos
            form2 = soup2.find('form', {'id': 'link-view'})
            if form2:
                logger.info("UII: Found another form, may need CAPTCHA")
        else:
            logger.warning(f"UII: POST returned {resp2.status_code}")

        return None

    except ImportError:
        logger.warning("UII: curl_cffi not available")
        return None
    except Exception as e:
        logger.error(f"UII: curl_cffi error: {e}")
        return None


def _resolve_with_2captcha(uii_url: str) -> Optional[str]:
    """
    Resuelve uii.io usando el servicio 2captcha para el CAPTCHA
    Requiere CAPTCHA_API_KEY en el entorno

    Args:
        uii_url: URL de uii.io

    Returns:
        URL final o None
    """
    if not CAPTCHA_API_KEY:
        logger.debug("UII: 2captcha not configured (no CAPTCHA_API_KEY)")
        return None

    try:
        from curl_cffi import requests as cffi_requests
        from bs4 import BeautifulSoup
        import requests

        logger.info(f"UII: Trying 2captcha bypass for {uii_url}")

        session = cffi_requests.Session(impersonate="chrome110")

        # Obtener la página inicial
        resp = session.get(uii_url, timeout=30, allow_redirects=True)

        if resp.status_code != 200:
            return None

        current_url = str(resp.url)
        html = resp.text
        soup = BeautifulSoup(html, 'html.parser')

        # Buscar el sitekey de reCAPTCHA
        sitekey = None

        # Buscar en data-sitekey
        recaptcha_div = soup.find('div', {'class': 'g-recaptcha'})
        if recaptcha_div:
            sitekey = recaptcha_div.get('data-sitekey')

        # Buscar en scripts
        if not sitekey:
            for script in soup.find_all('script'):
                if script.string and 'sitekey' in str(script.string):
                    match = re.search(r"sitekey['\"]?\s*[:=]\s*['\"]([^'\"]+)", str(script.string))
                    if match:
                        sitekey = match.group(1)
                        break

        # Buscar sitekey en el patrón típico de reCAPTCHA (6L + 38 caracteres)
        if not sitekey:
            import re
            sitekey_match = re.search(r'invisible_reCAPTCHA_site_key["\']?\s*[=:]\s*["\']?(6L[a-zA-Z0-9_-]{38})', html)
            if sitekey_match:
                sitekey = sitekey_match.group(1)
            else:
                # Buscar cualquier sitekey de 40 caracteres que empiece con 6L
                sitekey_matches = re.findall(r'6L[a-zA-Z0-9_-]{38}', html)
                if sitekey_matches:
                    sitekey = sitekey_matches[0]

        if not sitekey:
            logger.error("UII: Could not find reCAPTCHA sitekey")
            return None

        logger.info(f"UII: Found sitekey: {sitekey[:20]}...")

        # Enviar a 2captcha
        captcha_request = requests.post(
            'http://2captcha.com/in.php',
            data={
                'key': CAPTCHA_API_KEY,
                'method': 'userrecaptcha',
                'googlekey': sitekey,
                'pageurl': current_url,
                'json': 1,
            },
            timeout=30
        )

        result = captcha_request.json()
        if result.get('status') != 1:
            logger.error(f"UII: 2captcha submit error: {result}")
            return None

        captcha_id = result.get('request')
        logger.info(f"UII: 2captcha ID: {captcha_id}, waiting for solution...")

        # Esperar la solución (máximo 120 segundos)
        for _ in range(24):  # 24 * 5 = 120 segundos
            time.sleep(5)

            check = requests.get(
                f'http://2captcha.com/res.php?key={CAPTCHA_API_KEY}&action=get&id={captcha_id}&json=1',
                timeout=30
            )
            check_result = check.json()

            if check_result.get('status') == 1:
                captcha_response = check_result.get('request')
                logger.info("UII: Got CAPTCHA solution")

                # Enviar el formulario con la solución del CAPTCHA
                form = soup.find('form', {'id': 'link-view'})
                if form:
                    form_data = {}
                    for inp in form.find_all('input'):
                        name = inp.get('name')
                        value = inp.get('value', '')
                        if name:
                            form_data[name] = value

                    # Agregar la respuesta del CAPTCHA
                    form_data['g-recaptcha-response'] = captcha_response

                    action = form.get('action', '')
                    post_url = urljoin(current_url, action)

                    resp2 = session.post(post_url, data=form_data, timeout=30, allow_redirects=True)

                    if resp2.status_code == 200:
                        # Buscar el enlace final
                        download_patterns = [
                            r'(https?://(?:www\.)?terabox[^\s"<>\']+)',
                            r'(https?://(?:www\.)?mega\.nz[^\s"<>\']+)',
                            r'(https?://(?:www\.)?mediafire[^\s"<>\']+)',
                            r'(https?://(?:www\.)?drive\.google[^\s"<>\']+)',
                            r'(https?://(?:www\.)?fireload[^\s"<>\']+)',
                        ]

                        for pattern in download_patterns:
                            match = re.search(pattern, resp2.text)
                            if match:
                                return match.group(1)

                        # Buscar go_next
                        soup2 = BeautifulSoup(resp2.text, 'html.parser')
                        go_next = soup2.find('a', {'id': 'go_next'})
                        if go_next and go_next.get('href'):
                            href = go_next.get('href')
                            if href.startswith('http'):
                                return href

                break
            elif 'CAPCHA_NOT_READY' not in str(check_result):
                logger.error(f"UII: 2captcha error: {check_result}")
                break

        return None

    except Exception as e:
        logger.error(f"UII: 2captcha error: {e}")
        return None


def _resolve_with_flaresolverr(uii_url: str) -> Optional[str]:
    """
    Resuelve uii.io usando FlareSolverr (proxy para Cloudflare)
    Requiere FLARESOLVERR_URL en el entorno

    Args:
        uii_url: URL de uii.io

    Returns:
        URL final o None
    """
    if not FLARESOLVERR_URL:
        logger.debug("UII: FlareSolverr not configured")
        return None

    try:
        import requests

        logger.info(f"UII: Trying FlareSolverr for {uii_url}")

        # Petición a FlareSolverr
        response = requests.post(
            f"{FLARESOLVERR_URL}/v1",
            json={
                "cmd": "request.get",
                "url": uii_url,
                "maxTimeout": 60000
            },
            timeout=65
        )

        result = response.json()

        if result.get("status") == "ok":
            solution = result.get("solution", {})
            html = solution.get("response", "")
            final_url = solution.get("url", "")

            logger.info(f"UII: FlareSolverr got response, final URL: {final_url}")

            # Buscar enlaces de descarga en el HTML
            download_patterns = [
                r'(https?://(?:www\.)?terabox[^\s"<>\']+)',
                r'(https?://(?:www\.)?1024terabox[^\s"<>\']+)',
                r'(https?://(?:www\.)?mega\.nz[^\s"<>\']+)',
                r'(https?://(?:www\.)?mediafire[^\s"<>\']+)',
                r'(https?://(?:www\.)?drive\.google[^\s"<>\']+)',
                r'(https?://(?:www\.)?fireload[^\s"<>\']+)',
            ]

            for pattern in download_patterns:
                match = re.search(pattern, html)
                if match:
                    found_url = match.group(1)
                    logger.info(f"UII: FlareSolverr found download link: {found_url[:60]}...")
                    return found_url

            # Si no encontramos enlace pero hay un go_next en el HTML
            go_next_match = re.search(r'id="go_next"[^>]*href="([^"]+)"', html)
            if go_next_match:
                next_url = go_next_match.group(1)
                if next_url.startswith('http') and 'wordcount' not in next_url.lower():
                    logger.info(f"UII: FlareSolverr found go_next: {next_url[:60]}...")
                    return next_url

        else:
            logger.warning(f"UII: FlareSolverr error: {result.get('message')}")

        return None

    except Exception as e:
        logger.error(f"UII: FlareSolverr error: {e}")
        return None


def _resolve_uii_sync(uii_url: str) -> Optional[str]:
    """
    Intenta resolver uii.io usando múltiples métodos

    Args:
        uii_url: URL de uii.io

    Returns:
        URL final o None
    """
    # Método 1: curl_cffi con impersonación
    result = _resolve_with_curl_cffi(uii_url)
    if result:
        return result

    # Método 2: FlareSolverr (si está configurado)
    if FLARESOLVERR_URL:
        result = _resolve_with_flaresolverr(uii_url)
        if result:
            return result

    # Método 3: 2captcha (si está configurado)
    if CAPTCHA_API_KEY:
        result = _resolve_with_2captcha(uii_url)
        if result:
            return result

    logger.warning(f"UII: All bypass methods failed for {uii_url}")
    return None


class UIIResolver:
    """
    Resolver para enlaces de uii.io/wordcount.im
    """

    def __init__(self):
        pass

    async def resolve(self, uii_url: str, timeout: int = 120000) -> Dict:
        """
        Resuelve un enlace de uii.io de forma asíncrona

        Args:
            uii_url: URL de uii.io
            timeout: Tiempo máximo en ms

        Returns:
            Dict con {ok, final_url, host} o {ok: False, error}
        """
        logger.info(f"UII: Resolving {uii_url}")

        loop = asyncio.get_event_loop()

        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(_executor, _resolve_uii_sync, uii_url),
                timeout=timeout/1000
            )

            if result:
                # Identificar el host
                final_host = 'unknown'
                result_lower = result.lower()

                if 'terabox' in result_lower or '1024tera' in result_lower:
                    final_host = 'terabox'
                elif 'mega.nz' in result_lower:
                    final_host = 'mega'
                elif 'mediafire' in result_lower:
                    final_host = 'mediafire'
                elif 'drive.google' in result_lower:
                    final_host = 'google_drive'
                elif 'fireload' in result_lower:
                    final_host = 'fireload'

                logger.info(f"UII: Successfully resolved to {final_host}: {result}")
                return {
                    "ok": True,
                    "final_url": result,
                    "host": final_host
                }

            error_msg = "Could not resolve uii.io/wordcount.im link (requires CAPTCHA)"
            if not CAPTCHA_API_KEY:
                error_msg += ". To fix: set CAPTCHA_API_KEY=your_2captcha_key in .env (get key at 2captcha.com)"

            return {"ok": False, "error": error_msg, "requires_captcha": True}

        except asyncio.TimeoutError:
            return {"ok": False, "error": f"Timeout resolving uii.io link ({timeout}ms)"}
        except Exception as e:
            logger.error(f"UII: Error: {e}")
            return {"ok": False, "error": str(e)}

    async def close(self):
        """Cleanup"""
        pass


# Singleton instance
_resolver_instance: Optional[UIIResolver] = None


async def get_uii_resolver() -> UIIResolver:
    """Obtiene o crea la instancia singleton del resolver"""
    global _resolver_instance
    if _resolver_instance is None:
        _resolver_instance = UIIResolver()
    return _resolver_instance


async def resolve_uii_link(uii_url: str) -> Optional[str]:
    """
    Función auxiliar para resolver un enlace de uii.io

    Args:
        uii_url: URL de uii.io

    Returns:
        URL final o None si falla
    """
    try:
        resolver = await get_uii_resolver()
        result = await resolver.resolve(uii_url)

        if result.get("ok"):
            return result.get("final_url")

        logger.error(f"UII resolve error: {result.get('error')}")
        return None
    except Exception as e:
        logger.error(f"Error in resolve_uii_link: {e}")
        return None
