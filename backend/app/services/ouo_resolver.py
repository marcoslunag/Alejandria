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
            "maxTimeout": 120000,
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
# Playwright fallback
# ──────────────────────────────────────────────────────────────────────────────

async def _resolve_with_playwright(ouo_url: str) -> Optional[str]:
    """
    Resuelve ouo.io / ouo.press usando Playwright + reCAPTCHA v3 token injection.

    Flujo (idéntico al de FlareSolverr pero con Playwright como browser):
      Paso 1: GET  ouo.press/{id}          → extraer _token del form
              GET recaptcha v3 token        → inyectar x-token
              Click submit                  → redirect a /go/{id} o URL final
      Paso 2: GET  ouo.press/go/{id}       → extraer nuevo _token
              GET recaptcha v3 token        → inyectar x-token
              Click submit                  → URL final

    La diferencia clave con el approach anterior (click de botones):
      El form de ouo.press requiere un token reCAPTCHA v3 válido en el campo
      "x-token" para que el servidor acepte el POST. Sin él, la página no avanza
      aunque hagas click en el botón. Este approach lo obtiene e inyecta
      directamente en el DOM antes del submit.
    """
    from app.services.book_scrapers.playwright_scraper import get_playwright_scraper
    from bs4 import BeautifulSoup

    # Siempre ouo.press (reCAPTCHA v3, sin Turnstile)
    press_url = re.sub(r'https?://ouo\.io/', 'https://ouo.press/', ouo_url)
    if 'ouo.press' not in press_url:
        press_url = re.sub(r'https?://[^/]+/', 'https://ouo.press/', ouo_url)
    ouo_id = press_url.rstrip('/').split('/')[-1]

    def _extract_token(html: str) -> str:
        bs = BeautifulSoup(html, 'lxml')
        form = bs.find('form')
        if form:
            inp = form.find('input', {'name': '_token'})
            if inp:
                return inp.get('value', '')
        m = re.search(
            r'<input[^>]+name=["\']_token["\'][^>]+value=["\']([^"\']+)["\']'
            r'|<input[^>]+value=["\']([^"\']+)["\'][^>]+name=["\']_token["\']',
            html
        )
        if m:
            return m.group(1) or m.group(2)
        return ''

    page = None
    try:
        pw_scraper = await get_playwright_scraper()
        page = await pw_scraper._create_page()

        logger.info(f"OUO Playwright: cargando {press_url}")
        await page.goto(press_url, wait_until='domcontentloaded', timeout=30000)
        # Esperar a que Cloudflare JS challenge se auto-resuelva (si aplica)
        await asyncio.sleep(4)

        # ¿Redirigió ya a URL final?
        if _is_final_url(page.url):
            return page.url
        if 'ouo' not in page.url.lower():
            logger.info(f"OUO Playwright: redirect directo → {page.url[:80]}")
            return page.url

        # ─── DOS PASOS DE FORM SUBMISSION ──────────────────────────────────
        for step in range(2):
            current_url = page.url
            logger.info(f"OUO Playwright paso {step + 1}: en {current_url[:70]}")

            if _is_final_url(current_url):
                return current_url
            if 'ouo' not in current_url.lower():
                return current_url

            html = await page.content()

            # Buscar URL en HTML (a veces ya está embebida)
            extracted = _extract_url_from_html(html)
            if extracted:
                logger.info(f"OUO Playwright: URL encontrada en HTML → {extracted[:80]}")
                return extracted

            # Extraer _token del form
            _token = _extract_token(html)
            if not _token:
                logger.warning(f"OUO Playwright paso {step + 1}: no se encontró _token")
                break
            logger.info(f"OUO Playwright paso {step + 1}: _token obtenido ({len(_token)} chars)")

            # reCAPTCHA v3 (sin API key externa, igual que FlareSolverr)
            try:
                x_token = await asyncio.get_event_loop().run_in_executor(
                    None, _get_recaptcha_v3_sync
                )
                logger.info(f"OUO Playwright paso {step + 1}: x-token obtenido ({len(x_token)} chars)")
            except Exception as e:
                logger.warning(f"OUO Playwright paso {step + 1}: reCAPTCHA falló ({e}), intentando sin token")
                x_token = ""

            # Inyectar tokens en los campos del form
            safe_token = _token.replace('\\', '\\\\').replace("'", "\\'")
            safe_xtoken = x_token.replace('\\', '\\\\').replace("'", "\\'")
            await page.evaluate(f"""() => {{
                const setVal = (name, val) => {{
                    document.querySelectorAll('input[name="' + name + '"]').forEach(el => el.value = val);
                }};
                setVal('_token', '{safe_token}');
                setVal('x-token', '{safe_xtoken}');
                setVal('v-token', 'bx');
            }}""")

            # Click en el botón de submit (cualquier submit del form)
            submitted = False
            for sel in ['#btn-main', '.btn-main', 'button[type="submit"]',
                        'input[type="submit"]', 'form button']:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        await el.click()
                        submitted = True
                        logger.info(f"OUO Playwright paso {step + 1}: click en '{sel}'")
                        break
                except Exception:
                    pass

            if not submitted:
                # JS submit como último recurso
                await page.evaluate("const f = document.querySelector('form'); if(f) f.submit();")
                logger.info(f"OUO Playwright paso {step + 1}: form.submit() via JS")

            # Esperar navegación (networkidle o timeout)
            try:
                await page.wait_for_load_state('networkidle', timeout=15000)
            except Exception:
                await asyncio.sleep(6)

            new_url = page.url
            logger.info(f"OUO Playwright paso {step + 1} completado: {new_url[:80]}")

            if _is_final_url(new_url):
                return new_url
            if 'ouo' not in new_url.lower():
                return new_url

        # ─── Último intento: escanear HTML y links ──────────────────────────
        html = await page.content()
        extracted = _extract_url_from_html(html)
        if extracted:
            return extracted

        for link_el in await page.query_selector_all('a[href]'):
            href = await link_el.get_attribute('href')
            if href and 'ouo' not in href.lower() and _is_final_url(href):
                logger.info(f"OUO Playwright: link <a> encontrado: {href[:80]}")
                return href

        logger.warning(f"OUO Playwright: no se pudo resolver {ouo_url}, URL final: {page.url[:80]}")
        return None

    except asyncio.TimeoutError:
        logger.warning(f"OUO Playwright: timeout resolviendo {ouo_url}")
        return None
    except Exception as e:
        logger.error(f"OUO Playwright: error resolviendo {ouo_url}: {e}")
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

        result = None

        # Intentar FlareSolverr primero (si está configurado)
        if flaresolverr_url:
            logger.info(f"OUO: Trying FlareSolverr ({flaresolverr_url})")
            try:
                result = await asyncio.wait_for(
                    _resolve_with_flaresolverr(ouo_url, flaresolverr_url),
                    timeout=min(timeout / 1000, 150)  # máx 150s para FlareSolverr
                )
            except asyncio.TimeoutError:
                logger.warning(f"OUO: FlareSolverr timeout — intentando Playwright como fallback")
            except Exception as e:
                logger.warning(f"OUO: FlareSolverr error ({e}) — intentando Playwright como fallback")

        # Playwright: si FlareSolverr no está, o si falló/no resolvió
        if not result:
            if flaresolverr_url:
                logger.info("OUO: FlareSolverr no resolvió el enlace, usando Playwright como fallback")
            else:
                logger.info("OUO: FlareSolverr no configurado — usando Playwright")
            try:
                result = await asyncio.wait_for(
                    _resolve_with_playwright(ouo_url),
                    timeout=60
                )
            except asyncio.TimeoutError:
                logger.error(f"OUO: Playwright fallback también expiró para {ouo_url}")
                return {"ok": False, "error": f"Timeout en FlareSolverr y Playwright"}
            except Exception as e:
                logger.error(f"OUO: Playwright fallback error: {e}")
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
