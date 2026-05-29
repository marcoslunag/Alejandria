"""
OUO.io / OUO.press Link Resolver
=================================
Resuelve enlaces acortados de OUO.io para obtener el enlace final.

Estrategia (en orden):
  1. curl_cffi chrome120 puro   → GET ouo.io/{id} + 2 POSTs (sin browser, ~10s)
                                   chrome120 bypasses Cloudflare WAF en ouo.io
                                   (chrome110 = bloqueado; chrome120/124 = OK)
  2. FlareSolverr               → fallback si curl_cffi falla (~120s por CF challenge)
  3. Playwright                 → fallback si FlareSolverr no disponible

Flujo de ouo.io (2 pasos):
  GET  ouo.io/{id}              → form con _token (sin CF con chrome120)
  POST ouo.io/go/{id}           → {_token, x-token=reCAPTCHA, v-token=bx}
  POST ouo.io/xreallcygo/{id}   → Location header = URL final
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
# Estrategia 1: curl_cffi chrome120 puro (sin browser)
# ──────────────────────────────────────────────────────────────────────────────

def _resolve_curl_cffi_sync(ouo_url: str) -> Optional[str]:
    """
    Bypass puro HTTP con curl_cffi chrome120.

    Usa ouo.io (no ouo.press) — confirmado que chrome120 retorna 200 con formulario.
    chrome110 (bypass_ouo lib) → bloqueado 403.
    chrome120 / chrome124      → bypass OK (status 200, form visible).

    Flujo completo en ~10s sin necesidad de browser.
    """
    try:
        from curl_cffi import requests as cffi_requests
    except ImportError:
        logger.warning("OUO curl_cffi: librería no disponible, saltando")
        return None

    # Siempre usar ouo.io (chrome120 bypassa su WAF; ouo.press tiene WAF más agresivo)
    io_url = re.sub(r'https?://ouo\.(io|press)/', 'https://ouo.io/', ouo_url)
    ouo_id = io_url.rstrip('/').split('/')[-1]

    # Intentar múltiples fingerprints en orden (el WAF de ouo.io bloquea
    # versiones específicas; chrome124/131/safari funcionan desde Docker)
    fingerprints = ["chrome124", "chrome131", "safari15_5", "safari17_0", "chrome120"]
    r0 = None
    used_fingerprint = None

    for fp in fingerprints:
        try:
            session = cffi_requests.Session(impersonate=fp)
            session.headers.update({
                'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'accept-language': 'en-US,en;q=0.9',
                'upgrade-insecure-requests': '1',
            })
            logger.info(f"OUO curl_cffi: GET {io_url} (impersonate={fp})")
            r0 = session.get(io_url, timeout=15, allow_redirects=True)
            logger.info(f"OUO curl_cffi: status={r0.status_code} fingerprint={fp}")
            if r0.status_code == 200 and '_token' in r0.text:
                used_fingerprint = fp
                break
            elif r0.status_code == 200 and 'just a moment' not in r0.text.lower():
                used_fingerprint = fp
                break
        except Exception as e:
            logger.warning(f"OUO curl_cffi: fingerprint {fp} error: {e}")
            r0 = None
            continue

    if r0 is None or r0.status_code != 200:
        logger.warning(f"OUO curl_cffi: todos los fingerprints bloqueados")
        return None

    # Si el GET ya redirigió a la URL final
    if _is_final_url(r0.url):
        logger.info(f"OUO curl_cffi: redirect directo en GET → {r0.url[:80]}")
        return r0.url

    extracted_get = _extract_url_from_html(r0.text)
    if extracted_get:
        return extracted_get

    # Extraer _token del formulario
    _token = _extract_token_from_html(r0.text)
    if not _token:
        logger.warning(f"OUO curl_cffi: no _token en GET response (html[:300]={r0.text[:300]!r})")
        return None

    logger.info(f"OUO curl_cffi: _token extraído ({len(_token)} chars)")

    # reCAPTCHA v3 para x-token
    try:
        x_token = _get_recaptcha_v3_sync()
        logger.info(f"OUO curl_cffi: reCAPTCHA v3 obtenido ({len(x_token)} chars)")
    except Exception as e:
        logger.warning(f"OUO curl_cffi: reCAPTCHA falló ({e}), usando vacío")
        x_token = ""

    # ── POST 1: ouo.io/go/{id} ─────────────────────────────────────────────────
    # IMPORTANTE: usar la MISMA sesión del GET para que las cookies CF
    # (cf_clearance, __cf_bm) se incluyan automáticamente en el POST
    go_url = f'https://ouo.io/go/{ouo_id}'
    session.headers.update({
        'content-type': 'application/x-www-form-urlencoded',
        'origin': 'https://ouo.io',
        'referer': io_url,
    })
    form_data = {'_token': _token, 'x-token': x_token, 'v-token': 'bx'}

    logger.info(f"OUO curl_cffi: POST {go_url}")
    try:
        r1 = session.post(go_url, data=form_data, allow_redirects=False, timeout=30)
    except Exception as e:
        logger.warning(f"OUO curl_cffi: POST1 error: {e}")
        return None

    logger.info(f"OUO curl_cffi: POST1 status={r1.status_code} loc={r1.headers.get('Location','')[:80]}")

    loc1 = r1.headers.get('Location', '')
    if loc1:
        if _is_final_url(loc1):
            return loc1
        if 'ouo' not in loc1.lower():
            return loc1

    extracted1 = _extract_url_from_html(r1.text)
    if extracted1:
        return extracted1

    # ── POST 2: ouo.io/xreallcygo/{id} ────────────────────────────────────────
    _token2 = _extract_token_from_html(r1.text) or _token
    try:
        x_token2 = _get_recaptcha_v3_sync()
    except Exception:
        x_token2 = x_token

    xreal_url = f'https://ouo.io/xreallcygo/{ouo_id}'
    session.headers['referer'] = go_url
    form_data2 = {'_token': _token2, 'x-token': x_token2, 'v-token': 'bx'}

    logger.info(f"OUO curl_cffi: POST {xreal_url}")
    try:
        r2 = session.post(xreal_url, data=form_data2, allow_redirects=False, timeout=30)
    except Exception as e:
        logger.warning(f"OUO curl_cffi: POST2 error: {e}")
        return None

    logger.info(f"OUO curl_cffi: POST2 status={r2.status_code} loc={r2.headers.get('Location','')[:80]}")

    loc2 = r2.headers.get('Location', '')
    if loc2:
        if _is_final_url(loc2):
            return loc2
        if 'ouo' not in loc2.lower():
            return loc2

    extracted2 = _extract_url_from_html(r2.text)
    if extracted2:
        return extracted2

    logger.warning(f"OUO curl_cffi: no URL final. POST2 body[:300]={r2.text[:300]!r}")
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Helper: seguir redirect de páginas intermedias (mks98.com, etc.)
# ──────────────────────────────────────────────────────────────────────────────

def _follow_intermediate_sync(url: str) -> Optional[str]:
    """
    Sigue el redirect de URLs intermedias (mks98.com y similares) para obtener
    la URL de descarga final. FlareSolverr navega hasta aquí; solo falta un GET.
    """
    # Intentar con curl_cffi chrome124 (sigue redirects automáticamente)
    try:
        from curl_cffi import requests as cffi_requests
        s = cffi_requests.Session(impersonate="chrome124")
        r = s.get(url, timeout=15, allow_redirects=True)
        if _is_final_url(r.url):
            logger.info(f"OUO intermediario: {url[:60]} → {r.url[:80]}")
            return r.url
        loc = r.headers.get('Location', '')
        if loc and _is_final_url(loc):
            return loc
        extracted = _extract_url_from_html(r.text)
        if extracted:
            return extracted
    except Exception as e:
        logger.debug(f"OUO intermediario curl_cffi: {e}")

    # Fallback con requests básico
    try:
        import requests as sync_req
        r = sync_req.get(url, timeout=15, allow_redirects=True)
        if _is_final_url(r.url):
            return r.url
        extracted = _extract_url_from_html(r.text)
        if extracted:
            return extracted
    except Exception as e:
        logger.debug(f"OUO intermediario requests: {e}")

    logger.warning(f"OUO intermediario: no se pudo extraer URL de {url[:80]}")
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Estrategia 2: FlareSolverr (navegación completa con Chrome)
# ──────────────────────────────────────────────────────────────────────────────

async def _resolve_with_flaresolverr(ouo_url: str, flaresolverr_url: str) -> Optional[str]:
    """
    FlareSolverr navega el flujo completo de ouo.io en su Chrome (~90s):
      1. GET ouo.io/{id} → CF challenge + countdown auto-submit
      2. Chrome navega hasta mks98.com/link2 (página de tracking intermedia)
      3. Seguimos el redirect de mks98.com → URL de descarga final

    No se necesitan POSTs manuales — FlareSolverr lo hace todo en un solo GET.
    Usa ouo.io (no ouo.press) — ouo.press tiene WAF más agresivo en GET también.
    """
    import aiohttp

    # Usar ouo.io (Chrome de FlareSolverr navega el countdown auto-submit)
    io_url = re.sub(r'https?://ouo\.(io|press)/', 'https://ouo.io/', ouo_url)
    ouo_id = io_url.rstrip('/').split('/')[-1]
    session_id = f"alejandria_ouo_{ouo_id}"

    fs_base = flaresolverr_url.rstrip('/')

    async def fs_get(url: str, timeout_ms: int = 130000) -> Optional[dict]:
        payload = {"cmd": "request.get", "url": url, "session": session_id, "maxTimeout": timeout_ms}
        http_timeout = aiohttp.ClientTimeout(total=timeout_ms / 1000 + 20)
        try:
            async with aiohttp.ClientSession(timeout=http_timeout) as sess:
                async with sess.post(f"{fs_base}/v1", json=payload) as resp:
                    if resp.status != 200:
                        logger.warning(f"OUO FlareSolverr: HTTP {resp.status}")
                        return None
                    data = await resp.json()
            if data.get("status") != "ok":
                logger.warning(f"OUO FlareSolverr: {data.get('status')} — {data.get('message','')[:120]}")
                return None
            return data.get("solution")
        except Exception as e:
            logger.warning(f"OUO FlareSolverr: error GET: {e}")
            return None

    async def destroy_session():
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as sess:
                await sess.post(f"{fs_base}/v1", json={"cmd": "sessions.destroy", "session": session_id})
        except Exception:
            pass

    try:
        # Crear sesión persistente
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as sess:
                await sess.post(f"{fs_base}/v1", json={"cmd": "sessions.create", "session": session_id})
        except Exception:
            pass

        # GET ouo.io/{id} — Chrome navega CF + countdown auto-submit (~90s)
        logger.info(f"OUO FlareSolverr: GET {io_url}")
        sol = await fs_get(io_url, timeout_ms=130000)
        if not sol:
            return None

        final_url = sol.get("url", "")
        html = sol.get("response", "")
        logger.info(f"OUO FlareSolverr: GET terminó → {final_url[:80]}")

        # Caso 1: URL de descarga directa
        if _is_final_url(final_url):
            logger.info(f"OUO FlareSolverr: URL final directa → {final_url[:80]}")
            return final_url

        # Caso 2: Chrome navegó más allá de ouo.io (bypass exitoso!)
        # final_url es mks98.com/... u otro intermediario → seguir redirect
        if final_url and 'ouo.io' not in final_url and 'ouo.press' not in final_url:
            logger.info(f"OUO FlareSolverr: bypass exitoso, siguiendo intermediario {final_url[:60]}")
            real_url = await asyncio.get_event_loop().run_in_executor(
                None, _follow_intermediate_sync, final_url
            )
            if real_url:
                return real_url
            # Buscar en el HTML de la página intermediaria
            extracted = _extract_url_from_html(html)
            if extracted:
                return extracted
            logger.warning(f"OUO FlareSolverr: intermediario {final_url[:60]} no tiene URL de descarga")
            return None

        # Caso 3: Chrome sigue en ouo.io (countdown no terminó o form pendiente)
        # Extraer _token e intentar POSTs manuales como último recurso
        _token = _extract_token_from_html(html)
        if not _token:
            logger.warning(f"OUO FlareSolverr: sin redirect Y sin _token. html[:200]={html[:200]!r}")
            extracted = _extract_url_from_html(html)
            return extracted

        logger.info(f"OUO FlareSolverr: form pendiente, intentando POST manual")
        try:
            x_token = await asyncio.get_event_loop().run_in_executor(None, _get_recaptcha_v3_sync)
        except Exception:
            x_token = ""

        # POST manual a ouo.io/go/{id} via FlareSolverr
        go_url = f"https://ouo.io/go/{ouo_id}"
        form_data = urlencode({"_token": _token, "x-token": x_token, "v-token": "bx"})
        payload_post = {
            "cmd": "request.post", "url": go_url, "session": session_id,
            "postData": form_data, "maxTimeout": 120000,
        }
        http_timeout2 = aiohttp.ClientTimeout(total=140)
        try:
            async with aiohttp.ClientSession(timeout=http_timeout2) as sess:
                async with sess.post(f"{fs_base}/v1", json=payload_post) as resp:
                    data2 = await resp.json() if resp.status == 200 else {}
        except Exception as e:
            logger.warning(f"OUO FlareSolverr: POST manual error: {e}")
            data2 = {}

        sol2 = data2.get("solution") if data2.get("status") == "ok" else None
        if sol2:
            fu2 = sol2.get("url", "")
            if _is_final_url(fu2):
                return fu2
            if fu2 and 'ouo' not in fu2.lower():
                real_url = await asyncio.get_event_loop().run_in_executor(None, _follow_intermediate_sync, fu2)
                if real_url:
                    return real_url
            extracted2 = _extract_url_from_html(sol2.get("response", ""))
            if extracted2:
                return extracted2

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

    async def resolve(self, ouo_url: str, timeout: int = 600000) -> Dict:
        """
        Resuelve un enlace OUO con 3 estrategias en cascada:
          1. curl_cffi chrome120 (~10s) — puro HTTP, sin browser
          2. FlareSolverr (~120s)       — si curl_cffi falla
          3. Playwright fallback        — último recurso
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
                    asyncio.shield(existing_future), timeout=570
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

            # ── Estrategia 1: curl_cffi chrome120 (puro HTTP, ~10s, sin browser) ──────
            result = None
            try:
                logger.info(f"OUO: estrategia 1 — curl_cffi chrome120")
                result = await asyncio.get_event_loop().run_in_executor(
                    None, _resolve_curl_cffi_sync, ouo_url
                )
                if result:
                    logger.info(f"OUO: curl_cffi resolvió → {result[:80]}")
            except Exception as e:
                logger.warning(f"OUO: curl_cffi falló: {e}")
                result = None

            # ── Estrategia 2: FlareSolverr (fallback, ~120s) ─────────────────────
            if not result and flaresolverr_url:
                logger.info(f"OUO: estrategia 2 — FlareSolverr ({flaresolverr_url})")
                try:
                    result = await asyncio.wait_for(
                        _resolve_with_flaresolverr(ouo_url, flaresolverr_url),
                        timeout=min(timeout / 1000, 400)
                    )
                    if result:
                        logger.info(f"OUO: FlareSolverr resolvió → {result[:80]}")
                except asyncio.TimeoutError:
                    logger.error(f"OUO: FlareSolverr timeout")
                except Exception as e:
                    logger.error(f"OUO: FlareSolverr error: {e}")

            # ── Estrategia 3: Playwright (fallback final) ────────────────────────
            if not result:
                logger.info("OUO: estrategia 3 — Playwright fallback")
                try:
                    result = await asyncio.wait_for(
                        _resolve_with_playwright(ouo_url),
                        timeout=min(timeout / 1000, 120)
                    )
                    if result:
                        logger.info(f"OUO: Playwright resolvió → {result[:80]}")
                except asyncio.TimeoutError:
                    logger.error(f"OUO: Playwright timeout")
                except Exception as e:
                    logger.error(f"OUO: Playwright error: {e}")
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
