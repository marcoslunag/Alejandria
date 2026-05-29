"""
OUO.io / OUO.press Link Resolver
=================================
Resuelve enlaces acortados de OUO.io para obtener el enlace final.

Estrategia:
  1. FlareSolverr GET → obtiene página + cookies cf_clearance (bypass Cloudflare)
  2. curl_cffi POST  → usa cf_clearance para los 2 POSTs directamente (rápido)
  3. Playwright      → fallback si FlareSolverr no está disponible

Flujo de ouo.press (2 pasos):
  Paso 1: GET  ouo.press/{id}              → form con _token + cf_clearance
          POST ouo.press/go/{id}           → redirect a /xreallcygo/{id}
  Paso 2: POST ouo.press/xreallcygo/{id}  → URL final (Location header)
"""

import asyncio
import logging
import re
import time
from typing import Optional, Dict, Tuple
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

# ── Cache y deduplicación de resoluciones ──────────────────────────────────────
_resolution_cache: Dict[str, Tuple[float, Optional[str]]] = {}   # key → (ts, url)
_resolution_in_flight: Dict[str, "asyncio.Future[Optional[str]]"] = {}  # key → Future
_CACHE_TTL = 300  # 5 minutos


def _ouo_key(url: str) -> str:
    """Extrae el ID único de un enlace ouo.io/ouo.press."""
    return re.sub(r'https?://ouo\.(io|press)/', '', url).strip('/')


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

_KNOWN_HOSTS = [
    ('fireload.com',     r'https?://(?:www\.)?fireload\.com/[^\s"\'<>]+',     'fireload'),
    ('mediafire.com',    r'https?://(?:www\.)?mediafire\.com/[^\s"\'<>]+',    'mediafire'),
    ('mega.nz',          r'https?://(?:www\.)?mega\.nz/[^\s"\'<>]+',          'mega'),
    ('drive.google.com', r'https?://drive\.google\.com/[^\s"\'<>]+',          'gdrive'),
    ('terabox.com',      r'https?://(?:www\.)?terabox\.com/[^\s"\'<>]+',      'terabox'),
    ('1fichier.com',     r'https?://1fichier\.com/[^\s"\'<>]+',               '1fichier'),
    ('mega.co.nz',       r'https?://(?:www\.)?mega\.co\.nz/[^\s"\'<>]+',      'mega'),
]


def _is_final_url(url: str) -> bool:
    if not url:
        return False
    url_lower = url.lower()
    return any(host in url_lower for host, *_ in _KNOWN_HOSTS)


def _extract_url_from_html(html: str) -> Optional[str]:
    for _, pattern, host_name in _KNOWN_HOSTS:
        matches = re.findall(pattern, html)
        if matches:
            resolved = matches[0].rstrip('"\'')
            logger.info(f"OUO: Found {host_name} URL in HTML: {resolved[:80]}")
            return resolved
    return None


def _get_recaptcha_v3_sync() -> str:
    """
    Obtiene un token reCAPTCHA v3 para ouo.press sin API key externa.
    Usa los endpoints públicos de Google (igual que bypass_ouo==0.1.1).
    """
    import requests as sync_requests

    ANCHOR_URL = (
        'https://www.google.com/recaptcha/api2/anchor'
        '?ar=1&k=6Lcr1ncUAAAAAH3cghg6cOTPGARa8adOf-y9zv2x'
        '&co=aHR0cHM6Ly9vdW8ucHJlc3M6NDQz'
        '&hl=en&v=pCoGBhjs9s8EhFOHJFe8cqis&size=invisible&cb=ahgyd1gkfkhe'
    )
    url_base = 'https://www.google.com/recaptcha/'

    client = sync_requests.Session()
    client.headers.update({'content-type': 'application/x-www-form-urlencoded'})

    matches = re.findall(r'([api2|enterprise]+)/anchor\?(.*)', ANCHOR_URL)[0]
    api_path = matches[0]
    params   = matches[1]
    url_base += api_path + '/'

    res = client.get(url_base + 'anchor', params=params, timeout=15)
    res.raise_for_status()
    token = re.findall(r'"recaptcha-token" value="(.*?)"', res.text)[0]

    params_dict = dict(pair.split('=') for pair in params.split('&'))
    post_data = (
        f"v={params_dict['v']}&reason=q&c={token}"
        f"&k={params_dict['k']}&co={params_dict['co']}"
    )
    res = client.post(
        url_base + 'reload',
        params=f"k={params_dict['k']}",
        data=post_data,
        timeout=15,
    )
    res.raise_for_status()
    answer = re.findall(r'"rresp","(.*?)"', res.text)[0]
    return answer


def _extract_token_from_html(html: str) -> Optional[str]:
    """Extrae _token del HTML de una página ouo.press."""
    from bs4 import BeautifulSoup
    bs = BeautifulSoup(html, 'lxml')
    form = bs.find('form')
    if form:
        inp = form.find('input', {'name': '_token'})
        if inp:
            return inp.get('value', '')
    # fallback regex
    m = re.search(
        r'<input[^>]+name=["\']_token["\'][^>]+value=["\']([^"\']+)["\']'
        r'|<input[^>]+value=["\']([^"\']+)["\'][^>]+name=["\']_token["\']',
        html
    )
    if m:
        return m.group(1) or m.group(2)
    return None


# ──────────────────────────────────────────────────────────────────────────────
# POST con curl_cffi usando cookies de FlareSolverr (sin nuevo CF challenge)
# ──────────────────────────────────────────────────────────────────────────────

def _do_ouo_posts_sync(
    ouo_id: str,
    _token: str,
    x_token: str,
    cookies: Dict[str, str],
    user_agent: str,
) -> Optional[str]:
    """
    Realiza los 2 POSTs de ouo.press usando curl_cffi con las cookies cf_clearance
    ya obtenidas por FlareSolverr. Con cf_clearance válido no hay nuevo CF challenge.
    """
    try:
        from curl_cffi import requests as cffi_requests
    except ImportError:
        logger.warning("OUO curl_cffi: no disponible")
        return None

    ua = user_agent or (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    )

    session = cffi_requests.Session(impersonate="chrome120")
    session.headers.update({
        'user-agent': ua,
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'accept-language': 'en-US,en;q=0.9',
        'content-type': 'application/x-www-form-urlencoded',
        'origin': 'https://ouo.press',
        'referer': f'https://ouo.press/{ouo_id}',
    })

    # Inyectar cookies de FlareSolverr (incluyendo cf_clearance)
    for name, value in cookies.items():
        session.cookies.set(name, value, domain='.ouo.press')

    # ── POST 1: ouo.press/go/{id} ─────────────────────────────────────────────
    go_url = f'https://ouo.press/go/{ouo_id}'
    form_data = {'_token': _token, 'x-token': x_token, 'v-token': 'bx'}
    logger.info(f"OUO curl_cffi: POST {go_url}")
    try:
        r1 = session.post(go_url, data=form_data, allow_redirects=False, timeout=30)
    except Exception as e:
        logger.warning(f"OUO curl_cffi: POST1 error: {e}")
        return None

    logger.info(f"OUO curl_cffi: POST1 status={r1.status_code} location={r1.headers.get('Location', '')[:80]}")

    loc1 = r1.headers.get('Location', '')
    if loc1 and _is_final_url(loc1):
        return loc1
    if loc1 and 'ouo' not in loc1.lower():
        return loc1

    # Extraer URL final del body si la hay
    extracted = _extract_url_from_html(r1.text)
    if extracted:
        return extracted

    # ── POST 2: ouo.press/xreallcygo/{id} ─────────────────────────────────────
    _token2 = _extract_token_from_html(r1.text) or _token

    try:
        x_token2 = _get_recaptcha_v3_sync()
    except Exception:
        x_token2 = x_token

    xreal_url = f'https://ouo.press/xreallcygo/{ouo_id}'
    form_data2 = {'_token': _token2, 'x-token': x_token2, 'v-token': 'bx'}
    session.headers['referer'] = go_url
    logger.info(f"OUO curl_cffi: POST {xreal_url}")
    try:
        r2 = session.post(xreal_url, data=form_data2, allow_redirects=False, timeout=30)
    except Exception as e:
        logger.warning(f"OUO curl_cffi: POST2 error: {e}")
        return None

    logger.info(f"OUO curl_cffi: POST2 status={r2.status_code} location={r2.headers.get('Location', '')[:80]}")

    loc2 = r2.headers.get('Location', '')
    if loc2 and _is_final_url(loc2):
        return loc2
    if loc2 and 'ouo' not in loc2.lower():
        return loc2

    extracted2 = _extract_url_from_html(r2.text)
    if extracted2:
        return extracted2

    logger.warning(f"OUO curl_cffi: no se encontró URL final. POST2 body[:200]={r2.text[:200]}")
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Estrategia principal: FlareSolverr GET + curl_cffi POST
# ──────────────────────────────────────────────────────────────────────────────

async def _resolve_with_flaresolverr(ouo_url: str, flaresolverr_url: str) -> Optional[str]:
    """
    GET via FlareSolverr (resuelve Cloudflare WAF, ~60s).
    POST via curl_cffi con cf_clearance obtenido (~5s, sin nuevo challenge).
    """
    import aiohttp

    press_url = re.sub(r'https?://ouo\.io/', 'https://ouo.press/', ouo_url)
    if 'ouo.press' not in press_url:
        press_url = re.sub(r'https?://[^/]+/', 'https://ouo.press/', ouo_url)
    ouo_id = press_url.rstrip('/').split('/')[-1]
    session_id = f"alejandria_ouo_{ouo_id}"

    fs_base = flaresolverr_url.rstrip('/')
    # Timeout holgado: el challenge de CF tarda ~60s
    fs_timeout = aiohttp.ClientTimeout(total=150)

    async def fs_get(url: str) -> Optional[dict]:
        payload = {
            "cmd": "request.get",
            "url": url,
            "session": session_id,
            "maxTimeout": 120000,
        }
        try:
            async with aiohttp.ClientSession(timeout=fs_timeout) as sess:
                async with sess.post(f"{fs_base}/v1", json=payload) as resp:
                    if resp.status != 200:
                        logger.warning(f"OUO FlareSolverr: HTTP {resp.status} para GET {url[:60]}")
                        return None
                    data = await resp.json()
            if data.get("status") != "ok":
                logger.warning(f"OUO FlareSolverr: status={data.get('status')} msg={data.get('message','')[:120]}")
                return None
            return data.get("solution")
        except Exception as e:
            logger.warning(f"OUO FlareSolverr: error en GET: {e}")
            return None

    async def destroy_session():
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as sess:
                await sess.post(f"{fs_base}/v1", json={
                    "cmd": "sessions.destroy",
                    "session": session_id,
                })
        except Exception:
            pass

    try:
        # Crear sesión FlareSolverr
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as sess:
                await sess.post(f"{fs_base}/v1", json={
                    "cmd": "sessions.create",
                    "session": session_id,
                })
        except Exception:
            pass

        # ── GET ouo.press/{id} via FlareSolverr ───────────────────────────────
        logger.info(f"OUO FlareSolverr: GET {press_url}")
        sol = await fs_get(press_url)
        if not sol:
            logger.warning("OUO FlareSolverr: GET falló, sin solución")
            return None

        # ¿Redirigió directamente a URL final?
        final_url = sol.get("url", "")
        if _is_final_url(final_url):
            logger.info(f"OUO FlareSolverr: redirect directo → {final_url[:80]}")
            return final_url

        html = sol.get("response", "")

        # Extraer _token
        _token = _extract_token_from_html(html)
        if not _token:
            logger.warning("OUO FlareSolverr: no _token en página — ¿challenge no resuelto?")
            extracted = _extract_url_from_html(html)
            if extracted:
                return extracted
            return None

        logger.info(f"OUO FlareSolverr: _token extraído ({len(_token)} chars)")

        # Obtener cookies cf_clearance de FlareSolverr
        fs_cookies = {c['name']: c['value'] for c in sol.get('cookies', [])}
        fs_ua = sol.get('userAgent', '')
        logger.info(f"OUO FlareSolverr: cookies: {list(fs_cookies.keys())}")

        # reCAPTCHA v3
        try:
            x_token = await asyncio.get_event_loop().run_in_executor(
                None, _get_recaptcha_v3_sync
            )
            logger.info(f"OUO: reCAPTCHA v3 obtenido ({len(x_token)} chars)")
        except Exception as e:
            logger.warning(f"OUO: reCAPTCHA v3 falló ({e}), sin x-token")
            x_token = ""

        # ── POSTs con curl_cffi + cf_clearance ────────────────────────────────
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            _do_ouo_posts_sync,
            ouo_id, _token, x_token, fs_cookies, fs_ua,
        )

        if result:
            logger.info(f"OUO FlareSolverr+curl_cffi: resuelto → {result[:80]}")
            return result

        extracted = _extract_url_from_html(html)
        if extracted:
            return extracted

        logger.warning(f"OUO FlareSolverr: no se pudo resolver {ouo_url}")
        return None

    finally:
        await destroy_session()


# ──────────────────────────────────────────────────────────────────────────────
# Playwright fallback (cuando FlareSolverr no está disponible)
# ──────────────────────────────────────────────────────────────────────────────

async def _resolve_with_playwright(ouo_url: str) -> Optional[str]:
    """
    Fallback Playwright: flujo ZonaComics de 2 pasos.
    Navega a ouo.io y hace click en submit (sin convertir a ouo.press).
    """
    from app.services.book_scrapers.playwright_scraper import get_playwright_scraper

    page = None
    try:
        pw_scraper = await get_playwright_scraper()
        page = await pw_scraper._create_page()
        logger.info(f"OUO Playwright: cargando {ouo_url}")

        await page.goto(ouo_url, wait_until='domcontentloaded', timeout=20000)
        await asyncio.sleep(2)

        current_url = page.url
        if _is_final_url(current_url):
            return current_url
        if 'ouo.io' not in current_url and 'ouo.press' not in current_url:
            logger.info(f"OUO Playwright: redirect directo a {current_url[:80]}")
            return current_url

        # Flujo 2 pasos (ZonaComics style)
        for step in range(2):
            form = await page.query_selector('form#form-bypass') or await page.query_selector('form')

            if form:
                logger.info(f"OUO Playwright: paso {step+1} — formulario encontrado, esperando timer (6s)...")
                await asyncio.sleep(6)

                submit_btn = await page.query_selector(
                    'input[type="submit"], button[type="submit"], '
                    'button:has-text("Get Link"), button:has-text("Human"), '
                    '#btn-main, .btn-main, button'
                )
                if submit_btn:
                    try:
                        await submit_btn.click()
                        try:
                            await page.wait_for_url(
                                lambda u: _is_final_url(u) or ('ouo' not in u.lower()),
                                timeout=10000
                            )
                        except Exception:
                            await asyncio.sleep(3)
                    except Exception as e:
                        logger.debug(f"OUO Playwright: click falló paso {step+1}: {e}")
            else:
                title = await page.title()
                logger.warning(f"OUO Playwright: sin formulario paso {step+1}, título={title!r}")
                if 'Just a moment' in title or 'Cloudflare' in title:
                    logger.warning("OUO Playwright: bloqueado por Cloudflare, abortando")
                    break
                await asyncio.sleep(3)

            current_url = page.url
            if _is_final_url(current_url):
                logger.info(f"OUO Playwright: resuelto paso {step+1} → {current_url[:80]}")
                return current_url
            if 'ouo.io' not in current_url and 'ouo.press' not in current_url:
                return current_url

        html_content = await page.content()
        extracted = _extract_url_from_html(html_content)
        if extracted:
            return extracted

        page_links = await page.query_selector_all('a[href]')
        for link in page_links:
            href = await link.get_attribute('href')
            if href and 'ouo' not in href.lower() and _is_final_url(href):
                return href

        logger.warning(f"OUO Playwright: no se pudo resolver {ouo_url}, URL final: {page.url[:80]}")
        return None

    except asyncio.TimeoutError:
        logger.warning(f"OUO Playwright: timeout resolviendo {ouo_url}")
        return None
    except Exception as e:
        logger.error(f"OUO Playwright: error: {e}")
        return None
    finally:
        if page:
            try:
                ctx = page.context
                await page.close()
                await ctx.close()
            except Exception:
                pass


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

class OUOResolver:
    """Resolver para enlaces de OUO.io / OUO.press"""

    async def resolve(self, ouo_url: str, timeout: int = 300000) -> Dict:
        """
        Resuelve un enlace OUO.
        timeout=300000ms (5 min): FlareSolverr GET ~60s + curl_cffi POSTs ~10s.
        """
        key = _ouo_key(ouo_url)

        # ── Cache ──────────────────────────────────────────────────────────────
        cached = _resolution_cache.get(key)
        if cached:
            ts, cached_url = cached
            if time.time() - ts < _CACHE_TTL:
                if cached_url:
                    logger.info(f"OUO: cache hit para {key} → {cached_url[:60]}")
                    return self._make_ok(cached_url)
                logger.info(f"OUO: cache hit (fallo previo) para {key}")
                return {"ok": False, "error": "Cache: resolución previa fallida"}

        # ── Deduplicación in-flight ────────────────────────────────────────────
        loop = asyncio.get_event_loop()
        existing_future = _resolution_in_flight.get(key)
        if existing_future:
            logger.info(f"OUO: resolución en curso para {key}, esperando resultado...")
            try:
                result_url = await asyncio.wait_for(
                    asyncio.shield(existing_future), timeout=280
                )
                if result_url:
                    return self._make_ok(result_url)
                return {"ok": False, "error": "Resolución compartida: sin resultado"}
            except asyncio.TimeoutError:
                logger.warning(f"OUO: timeout esperando resolución compartida de {key}")
                return {"ok": False, "error": "Timeout esperando resolución compartida"}

        # ── Resolver (soy el primero) ──────────────────────────────────────────
        future: "asyncio.Future[Optional[str]]" = loop.create_future()
        _resolution_in_flight[key] = future

        try:
            logger.info(f"OUO: Resolving {ouo_url}")
            try:
                from app.config import get_settings
                settings = get_settings()
                flaresolverr_url = settings.FLARESOLVERR_URL
            except Exception:
                flaresolverr_url = None

            if flaresolverr_url:
                logger.info(f"OUO: usando FlareSolverr+curl_cffi ({flaresolverr_url})")
                resolver_coro = _resolve_with_flaresolverr(ouo_url, flaresolverr_url)
            else:
                logger.info("OUO: FlareSolverr no configurado, usando Playwright")
                resolver_coro = _resolve_with_playwright(ouo_url)

            try:
                result = await asyncio.wait_for(resolver_coro, timeout=timeout / 1000)
            except asyncio.TimeoutError:
                logger.error(f"OUO: timeout global ({timeout}ms) resolviendo {ouo_url}")
                result = None
            except Exception as e:
                logger.error(f"OUO: error inesperado: {e}")
                result = None

            # Guardar en cache
            _resolution_cache[key] = (time.time(), result)

            # Notificar waiters
            if not future.done():
                future.set_result(result)

            if result:
                return self._make_ok(result)
            return {"ok": False, "error": "No se pudo resolver el enlace de OUO.io"}

        except Exception as e:
            if not future.done():
                future.set_exception(e)
            raise
        finally:
            _resolution_in_flight.pop(key, None)

    def _make_ok(self, url: str) -> Dict:
        r = url.lower()
        host = 'unknown'
        if 'fireload' in r:       host = 'fireload'
        elif 'mediafire' in r:    host = 'mediafire'
        elif 'mega.nz' in r or 'mega.co.nz' in r: host = 'mega'
        elif '1fichier' in r:     host = '1fichier'
        elif 'drive.google' in r: host = 'google_drive'
        elif 'terabox' in r:      host = 'terabox'
        logger.info(f"OUO: resuelto a {host}: {url}")
        return {"ok": True, "final_url": url, "host": host}

    async def close(self):
        pass


# Singleton
_resolver_instance: Optional[OUOResolver] = None


async def get_ouo_resolver() -> OUOResolver:
    global _resolver_instance
    if _resolver_instance is None:
        _resolver_instance = OUOResolver()
    return _resolver_instance


async def resolve_ouo_link(ouo_url: str) -> Optional[str]:
    """Función auxiliar: resuelve un enlace OUO y devuelve la URL final o None."""
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
