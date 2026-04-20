"""
OUO.io / OUO.press Link Resolver
=================================
Resuelve enlaces acortados de OUO.io para obtener el enlace final.

Estrategia (por orden de preferencia):
  1. FlareSolverr  — lanza Chrome real, bypassa Cloudflare WAF y Turnstile.
                     Requiere FLARESOLVERR_URL (se habilita en docker-compose).
  2. Playwright    — fallback cuando FlareSolverr no está disponible.
                     Sigue funcionando si ouo.press afloja las restricciones CF.

Flujo de ouo.press (2 pasos):
  Paso 1: GET  ouo.press/{id}        → form con _token
          POST ouo.press/go/{id}     → redirect a /xreallcygo/{id} o URL final
  Paso 2: GET  ouo.press/xreallcygo/{id}  → form con _token
          POST ouo.press/xreallcygo/{id}  → URL final
"""

import asyncio
import logging
import re
from typing import Optional, Dict
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

_KNOWN_HOSTS = [
    ('fireload.com',      r'https?://(?:www\.)?fireload\.com/[^\s"\'<>]+',      'fireload'),
    ('mediafire.com',     r'https?://(?:www\.)?mediafire\.com/[^\s"\'<>]+',     'mediafire'),
    ('mega.nz',           r'https?://(?:www\.)?mega\.nz/[^\s"\'<>]+',           'mega'),
    ('drive.google.com',  r'https?://drive\.google\.com/[^\s"\'<>]+',           'gdrive'),
    ('terabox.com',       r'https?://(?:www\.)?terabox\.com/[^\s"\'<>]+',       'terabox'),
    ('1fichier.com',      r'https?://1fichier\.com/[^\s"\'<>]+',                '1fichier'),
    ('mega.co.nz',        r'https?://(?:www\.)?mega\.co\.nz/[^\s"\'<>]+',       'mega'),
]


def _is_final_url(url: str) -> bool:
    """Returns True if the URL points to a known file host (not OUO)."""
    if not url:
        return False
    url_lower = url.lower()
    return any(host in url_lower for host, *_ in _KNOWN_HOSTS)


def _extract_url_from_html(html: str) -> Optional[str]:
    """Scan HTML for known file-host URLs."""
    for _, pattern, host_name in _KNOWN_HOSTS:
        matches = re.findall(pattern, html)
        if matches:
            resolved = matches[0].rstrip('"\'')
            logger.info(f"OUO: Found {host_name} URL in HTML: {resolved[:80]}")
            return resolved
    return None


def _get_recaptcha_v3_sync() -> str:
    """
    Obtiene un token reCAPTCHA v3 para ouo.press SIN necesitar API key externa.
    Usa los endpoints públicos de Google igual que bypass_ouo==0.1.1.
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
    params = matches[1]
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


# ──────────────────────────────────────────────────────────────────────────────
# FlareSolverr strategy
# ──────────────────────────────────────────────────────────────────────────────

async def _resolve_with_flaresolverr(ouo_url: str, flaresolverr_url: str) -> Optional[str]:
    """
    Resuelve un enlace OUO usando FlareSolverr.

    FlareSolverr lanza un Chrome real que resuelve el JS-challenge de Cloudflare
    y devuelve las cookies (incluido cf_clearance). Usamos una sesión para que
    las cookies persistan entre el GET y los POST.

    Flujo:
      GET  ouo.press/{id}           → HTML con form (_token)
      POST ouo.press/go/{id}        → redirect (paso 1)
      POST ouo.press/xreallcygo/{id}→ URL final (paso 2, si fue necesario)
    """
    import aiohttp
    from bs4 import BeautifulSoup

    # Siempre usar ouo.press (sin Turnstile, solo reCAPTCHA v3)
    press_url = re.sub(r'https?://ouo\.io/', 'https://ouo.press/', ouo_url)
    if 'ouo.press' not in press_url:
        press_url = re.sub(r'https?://[^/]+/', 'https://ouo.press/', ouo_url)
    ouo_id = press_url.rstrip('/').split('/')[-1]
    session_id = f"alejandria_ouo_{ouo_id}"

    fs_base = flaresolverr_url.rstrip('/')
    timeout = aiohttp.ClientTimeout(total=90)

    async def fs_request(cmd: str, url: str, post_data: Optional[str] = None) -> Optional[dict]:
        """Envía un request a FlareSolverr y devuelve solution dict o None."""
        payload: dict = {
            "cmd": cmd,
            "url": url,
            "session": session_id,
            "maxTimeout": 60000,
        }
        if post_data is not None:
            payload["postData"] = post_data

        try:
            async with aiohttp.ClientSession(timeout=timeout) as sess:
                async with sess.post(f"{fs_base}/v1", json=payload) as resp:
                    if resp.status != 200:
                        logger.warning(f"OUO FlareSolverr: HTTP {resp.status} for {cmd} {url[:60]}")
                        return None
                    data = await resp.json()

            if data.get("status") != "ok":
                logger.warning(f"OUO FlareSolverr: status={data.get('status')} msg={data.get('message','')[:120]}")
                return None

            return data.get("solution")
        except Exception as e:
            logger.warning(f"OUO FlareSolverr: request error: {e}")
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
        # ── Crear sesión (para persistir cookies CF entre requests) ─────────
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as sess:
                await sess.post(f"{fs_base}/v1", json={
                    "cmd": "sessions.create",
                    "session": session_id,
                })
        except Exception:
            pass  # No crítico — FlareSolverr puede funcionar sin sesión explícita

        # ── Paso 1: GET ouo.press/{id} ───────────────────────────────────────
        logger.info(f"OUO FlareSolverr: GET {press_url}")
        sol = await fs_request("request.get", press_url)
        if not sol:
            return None

        # ¿Ya nos redirigió a la URL final?
        final_url = sol.get("url", "")
        if _is_final_url(final_url):
            logger.info(f"OUO FlareSolverr: Direct redirect → {final_url[:80]}")
            return final_url

        html = sol.get("response", "")

        # Extraer _token del formulario
        bs = BeautifulSoup(html, 'lxml')
        form = bs.find('form')
        token_input = form.find('input', {'name': '_token'}) if form else None
        if not token_input:
            # Intentar regex como fallback
            m = re.search(
                r'<input[^>]+name=["\']_token["\'][^>]+value=["\']([^"\']+)["\']'
                r'|<input[^>]+value=["\']([^"\']+)["\'][^>]+name=["\']_token["\']',
                html
            )
            if not m:
                logger.warning("OUO FlareSolverr: No _token in page — CF challenge not solved?")
                extracted = _extract_url_from_html(html)
                return extracted
            _token = m.group(1) or m.group(2)
        else:
            _token = token_input.get('value', '')

        logger.info(f"OUO FlareSolverr: Got _token ({len(_token)} chars)")

        # reCAPTCHA v3 (sin API key externa)
        try:
            x_token = await asyncio.get_event_loop().run_in_executor(
                None, _get_recaptcha_v3_sync
            )
            logger.info(f"OUO FlareSolverr: Got x-token ({len(x_token)} chars)")
        except Exception as e:
            logger.warning(f"OUO FlareSolverr: RecaptchaV3 failed ({e}), trying without x-token")
            x_token = ""

        # ── Paso 1 POST: ouo.press/go/{id} ──────────────────────────────────
        go_url = f"https://ouo.press/go/{ouo_id}"
        form_data = urlencode({"_token": _token, "x-token": x_token, "v-token": "bx"})
        logger.info(f"OUO FlareSolverr: POST {go_url}")
        sol2 = await fs_request("request.post", go_url, post_data=form_data)

        if sol2:
            final_url2 = sol2.get("url", "")
            if _is_final_url(final_url2):
                logger.info(f"OUO FlareSolverr: Resolved via /go/ → {final_url2[:80]}")
                return final_url2

            html2 = sol2.get("response", "")
            extracted = _extract_url_from_html(html2)
            if extracted:
                return extracted

            # ── Paso 2 POST: ouo.press/xreallcygo/{id} ──────────────────────
            # La primera POST a /go/ redirige a /xreallcygo/ (el "Get Link" real)
            xreal_url = f"https://ouo.press/xreallcygo/{ouo_id}"

            # Nuevo _token del HTML de /go/ (si lo tiene)
            bs2 = BeautifulSoup(html2, 'lxml')
            form2 = bs2.find('form')
            token2_input = form2.find('input', {'name': '_token'}) if form2 else None
            _token2 = token2_input.get('value', '') if token2_input else _token

            # Nuevo x-token para el segundo POST
            try:
                x_token2 = await asyncio.get_event_loop().run_in_executor(
                    None, _get_recaptcha_v3_sync
                )
            except Exception:
                x_token2 = x_token

            form_data2 = urlencode({"_token": _token2, "x-token": x_token2, "v-token": "bx"})
            logger.info(f"OUO FlareSolverr: POST {xreal_url}")
            sol3 = await fs_request("request.post", xreal_url, post_data=form_data2)

            if sol3:
                final_url3 = sol3.get("url", "")
                if _is_final_url(final_url3):
                    logger.info(f"OUO FlareSolverr: Resolved via /xreallcygo/ → {final_url3[:80]}")
                    return final_url3

                html3 = sol3.get("response", "")
                extracted = _extract_url_from_html(html3)
                if extracted:
                    return extracted

        logger.warning(f"OUO FlareSolverr: Could not resolve {ouo_url}")
        return None

    finally:
        await destroy_session()


# ──────────────────────────────────────────────────────────────────────────────
# Playwright fallback (mantener por si FlareSolverr no está configurado)
# ──────────────────────────────────────────────────────────────────────────────

async def _resolve_with_playwright(ouo_url: str) -> Optional[str]:
    """
    Fallback: Playwright headless.
    Funciona solo si Cloudflare no exige cf_clearance (raro con ouo.io actual).
    """
    from app.services.book_scrapers.playwright_scraper import get_playwright_scraper

    async def _find_and_click(pg, *selectors):
        for sel in selectors:
            try:
                el = await pg.query_selector(sel)
                if el:
                    await el.click()
                    return True
            except Exception:
                pass
        return False

    page = None
    try:
        pw_scraper = await get_playwright_scraper()
        page = await pw_scraper._create_page()
        logger.info(f"OUO Playwright: Navigating to {ouo_url}")

        await page.goto(ouo_url, wait_until='domcontentloaded', timeout=20000)
        await asyncio.sleep(2)

        current_url = page.url
        if _is_final_url(current_url):
            return current_url
        if 'ouo.io' not in current_url and 'ouo.press' not in current_url:
            logger.info(f"OUO Playwright: Direct redirect to {current_url[:80]}")
            return current_url

        # Paso 1: click "I'm a human"
        clicked = await _find_and_click(
            page,
            'button:has-text("human")',
            'button:has-text("Human")',
            '#btn-main', '.btn-main',
            'input[type="submit"]',
            'button[type="submit"]',
            'button',
        )
        if clicked:
            try:
                await page.wait_for_url(
                    lambda u: '/go/' in u or _is_final_url(u),
                    timeout=8000
                )
            except Exception:
                await asyncio.sleep(4)

        current_url = page.url
        if _is_final_url(current_url):
            return current_url
        if 'ouo.io' not in current_url and 'ouo.press' not in current_url:
            return current_url

        # Paso 2: countdown + "Get Link"
        if '/go/' in page.url or 'ouo.io' in page.url or 'ouo.press' in page.url:
            logger.info(f"OUO Playwright: Waiting for countdown on {page.url[:60]}")

            # Esperar a que countdown llegue a 0s (texto "0 Seconds")
            for _ in range(15):
                try:
                    body_text = await page.text_content('body') or ''
                    if re.search(r'\b0\s+[Ss]econd', body_text):
                        break
                except Exception:
                    pass
                await asyncio.sleep(1)

            await asyncio.sleep(1)

            clicked2 = await _find_and_click(
                page,
                'button:has-text("Get Link")',
                'button:has-text("get link")',
                'a:has-text("Get Link")',
                '#btn-main', '.btn-main',
                'input[type="submit"]',
                'button[type="submit"]',
                'button',
            )
            if clicked2:
                try:
                    await page.wait_for_url(
                        lambda u: _is_final_url(u),
                        timeout=10000
                    )
                except Exception:
                    await asyncio.sleep(4)
                    try:
                        await page.wait_for_load_state('networkidle', timeout=8000)
                    except Exception:
                        pass

            current_url = page.url
            if _is_final_url(current_url):
                return current_url
            if 'ouo.io' not in current_url and 'ouo.press' not in current_url:
                return current_url

        # Fallback: buscar en HTML
        html_content = await page.content()
        extracted = _extract_url_from_html(html_content)
        if extracted:
            return extracted

        # Último recurso: links <a>
        page_links = await page.query_selector_all('a[href]')
        for link in page_links:
            href = await link.get_attribute('href')
            if href and 'ouo' not in href.lower() and _is_final_url(href):
                logger.info(f"OUO Playwright: Found host link in <a>: {href[:80]}")
                return href

        logger.warning(f"OUO Playwright: Could not resolve {ouo_url}, final URL: {page.url[:80]}")
        return None

    except asyncio.TimeoutError:
        logger.warning(f"OUO Playwright: Timeout resolving {ouo_url}")
        return None
    except Exception as e:
        logger.error(f"OUO Playwright: Error resolving {ouo_url}: {e}")
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

    async def resolve(self, ouo_url: str, timeout: int = 90000) -> Dict:
        """
        Resuelve un enlace OUO de forma asíncrona.

        Usa FlareSolverr si FLARESOLVERR_URL está configurado; si no, Playwright.
        """
        logger.info(f"OUO: Resolving {ouo_url}")

        try:
            from app.config import get_settings
            settings = get_settings()
            flaresolverr_url = settings.FLARESOLVERR_URL
        except Exception:
            flaresolverr_url = None

        # Seleccionar estrategia
        if flaresolverr_url:
            logger.info(f"OUO: Using FlareSolverr ({flaresolverr_url})")
            resolver_coro = _resolve_with_flaresolverr(ouo_url, flaresolverr_url)
        else:
            logger.info("OUO: FlareSolverr not configured — falling back to Playwright")
            resolver_coro = _resolve_with_playwright(ouo_url)

        try:
            result = await asyncio.wait_for(resolver_coro, timeout=timeout / 1000)
        except asyncio.TimeoutError:
            logger.error(f"OUO: Global timeout ({timeout}ms) resolving {ouo_url}")
            return {"ok": False, "error": f"Timeout after {timeout}ms"}
        except Exception as e:
            logger.error(f"OUO: Unexpected error: {e}")
            return {"ok": False, "error": str(e)}

        if result:
            final_host = 'unknown'
            r = result.lower()
            if 'fireload' in r:       final_host = 'fireload'
            elif 'mediafire' in r:    final_host = 'mediafire'
            elif 'mega.nz' in r or 'mega.co.nz' in r:  final_host = 'mega'
            elif '1fichier' in r:     final_host = '1fichier'
            elif 'drive.google' in r: final_host = 'google_drive'
            elif 'terabox' in r:      final_host = 'terabox'

            logger.info(f"OUO: Successfully resolved to {final_host}: {result}")
            return {"ok": True, "final_url": result, "host": final_host}

        return {"ok": False, "error": "No se pudo resolver el enlace de OUO.io"}

    async def close(self):
        """Cleanup (no-op)."""
        pass


# Singleton
_resolver_instance: Optional[OUOResolver] = None


async def get_ouo_resolver() -> OUOResolver:
    global _resolver_instance
    if _resolver_instance is None:
        _resolver_instance = OUOResolver()
    return _resolver_instance


async def resolve_ouo_link(ouo_url: str) -> Optional[str]:
    """
    Función auxiliar: resuelve un enlace OUO y devuelve la URL final o None.
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
