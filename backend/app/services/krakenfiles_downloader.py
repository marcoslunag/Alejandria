"""
KrakenFiles Downloader

krakenfiles.com usa Cloudflare Turnstile en el formulario de descarga.
No se puede resolver en modo headless con Playwright estándar.

Flujo:
1. Carga la página con Playwright para obtener token, fingerprint y cf_clearance
2. Usa 2captcha (si CAPTCHA_API_KEY está configurado) para resolver el Turnstile
3. POST a /download/{id} con el token, fingerprint y respuesta de Turnstile
4. Obtiene la URL CDN del JSON de respuesta
5. Descarga el archivo con aiohttp desde la URL CDN
"""

import asyncio
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

import aiohttp

logger = logging.getLogger(__name__)

CAPTCHA_API_KEY = os.environ.get("CAPTCHA_API_KEY", "")

_executor = ThreadPoolExecutor(max_workers=2)


def _solve_turnstile_2captcha(sitekey: str, page_url: str) -> Optional[str]:
    """Resuelve Cloudflare Turnstile con 2captcha. Devuelve el token o None."""
    if not CAPTCHA_API_KEY:
        logger.debug("KrakenFiles: CAPTCHA_API_KEY no configurado — no se puede resolver Turnstile")
        return None

    try:
        import requests as sync_requests

        logger.info(f"KrakenFiles: Enviando Turnstile a 2captcha (sitekey={sitekey[:20]}...)")
        resp = sync_requests.post(
            "https://2captcha.com/in.php",
            data={
                "key": CAPTCHA_API_KEY,
                "method": "turnstile",
                "sitekey": sitekey,
                "pageurl": page_url,
                "json": 1,
            },
            timeout=30,
        )
        result = resp.json()
        if result.get("status") != 1:
            logger.error(f"KrakenFiles: 2captcha submit error: {result}")
            return None

        captcha_id = result.get("request")
        logger.info(f"KrakenFiles: 2captcha Turnstile ID={captcha_id}, esperando solución...")

        # Polling (máximo 120 segundos)
        for _ in range(24):
            time.sleep(5)
            check = sync_requests.get(
                "https://2captcha.com/res.php",
                params={
                    "key": CAPTCHA_API_KEY,
                    "action": "get",
                    "id": captcha_id,
                    "json": 1,
                },
                timeout=30,
            )
            check_result = check.json()
            if check_result.get("status") == 1:
                token = check_result.get("request")
                logger.info("KrakenFiles: Turnstile resuelto por 2captcha")
                return token
            elif "CAPCHA_NOT_READY" not in str(check_result):
                logger.error(f"KrakenFiles: 2captcha polling error: {check_result}")
                return None

        logger.warning("KrakenFiles: 2captcha timeout (120s)")
        return None

    except Exception as e:
        logger.error(f"KrakenFiles: 2captcha error: {e}")
        return None


def _extract_file_id(url: str) -> Optional[str]:
    """Extrae el ID del archivo de una URL de krakenfiles.com/view/{id}/file.html"""
    m = re.search(r"krakenfiles\.com/view/([^/]+)/", url)
    return m.group(1) if m else None


async def download_from_krakenfiles(view_url: str, dest_path: Path) -> bool:
    """
    Descarga un archivo de krakenfiles.com.

    Args:
        view_url: URL de la forma https://krakenfiles.com/view/{id}/file.html
        dest_path: Ruta de destino donde guardar el archivo

    Returns:
        True si la descarga fue exitosa, False en caso contrario
    """
    file_id = _extract_file_id(view_url)
    if not file_id:
        logger.error(f"KrakenFiles: No se pudo extraer el ID del archivo de: {view_url}")
        return False

    logger.info(f"KrakenFiles: Descargando {file_id} desde {view_url}")

    # Paso 1: Cargar la página con Playwright para obtener token, fingerprint y cookies
    page = None
    try:
        from app.services.book_scrapers.playwright_scraper import get_playwright_scraper

        scraper = await get_playwright_scraper()
        page = await scraper._create_page()

        logger.info("KrakenFiles: Cargando página con Playwright...")
        await page.goto(view_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        # Extraer datos del formulario
        token = await page.input_value("#dl-token")
        if not token:
            logger.error("KrakenFiles: No se encontró el token en la página")
            return False

        fingerprint = await page.evaluate(
            'document.querySelector("input[name=fingerprint]")?.value || ""'
        )

        # Extraer sitekey del Turnstile (para 2captcha)
        sitekey = await page.evaluate(
            'document.querySelector(".cf-turnstile")?.dataset?.sitekey || ""'
        )

        # Obtener cookies (cf_clearance es crítica)
        cookies = await page.context.cookies()
        cookie_dict = {
            c["name"]: c["value"]
            for c in cookies
            if "krakenfiles" in c.get("domain", "") or c.get("domain", "").endswith(".com")
        }

        logger.info(f"KrakenFiles: token={token[:20]}..., fingerprint={fingerprint}, sitekey={sitekey[:20]}...")

    finally:
        if page:
            await page.close()

    # Paso 2: Resolver el Turnstile con 2captcha
    loop = asyncio.get_event_loop()
    turnstile_response = None

    if sitekey and CAPTCHA_API_KEY:
        try:
            turnstile_response = await asyncio.wait_for(
                loop.run_in_executor(
                    _executor,
                    _solve_turnstile_2captcha,
                    sitekey,
                    view_url,
                ),
                timeout=150,
            )
        except asyncio.TimeoutError:
            logger.warning("KrakenFiles: Timeout esperando 2captcha")
    else:
        if not CAPTCHA_API_KEY:
            logger.error(
                "KrakenFiles: No se puede descargar — CAPTCHA_API_KEY no configurado. "
                "Configura 2captcha en .env para descargar de krakenfiles.com"
            )
            return False
        if not sitekey:
            logger.error("KrakenFiles: No se encontró sitekey del Turnstile en la página")
            return False

    if not turnstile_response:
        logger.error("KrakenFiles: No se pudo obtener token de Turnstile")
        return False

    # Paso 3: POST al endpoint de descarga de krakenfiles
    post_url = f"https://krakenfiles.com/download/{file_id}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": view_url,
        "Origin": "https://krakenfiles.com",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
    }
    form_data = {
        "token": token,
        "fingerprint": fingerprint,
        "userdata": "",
        "cf-turnstile-response": turnstile_response,
    }
    # Añadir cookies al header
    cookie_header = "; ".join(f"{k}={v}" for k, v in cookie_dict.items())
    if cookie_header:
        headers["Cookie"] = cookie_header

    logger.info(f"KrakenFiles: POST a {post_url}...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                post_url,
                data=form_data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error(f"KrakenFiles: POST falló con {resp.status}: {body[:200]}")
                    return False

                result = await resp.json()
                cdn_url = result.get("url")
                if result.get("status") != "success" or not cdn_url:
                    logger.error(f"KrakenFiles: Respuesta de error: {result}")
                    return False

                logger.info(f"KrakenFiles: URL CDN obtenida: {cdn_url[:80]}")
    except Exception as e:
        logger.error(f"KrakenFiles: Error en POST: {e}")
        return False

    # Paso 4: Descargar el archivo desde la URL CDN
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"KrakenFiles: Descargando desde CDN a {dest_path}...")
    try:
        download_headers = {
            "User-Agent": headers["User-Agent"],
            "Referer": "https://krakenfiles.com/",
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(
                cdn_url,
                headers=download_headers,
                timeout=aiohttp.ClientTimeout(total=600),
                allow_redirects=True,
            ) as resp:
                if resp.status != 200:
                    logger.error(f"KrakenFiles: CDN download falló con {resp.status}")
                    return False

                # Detectar extensión real desde Content-Disposition o URL
                content_disp = resp.headers.get("Content-Disposition", "")
                suggested_name = re.search(r'filename[^;=\n]*=(?:["\']?)([^"\';\n]+)', content_disp)
                if suggested_name:
                    real_name = suggested_name.group(1).strip().strip('"')
                    ext = Path(real_name).suffix.lower()
                    if ext and dest_path.suffix.lower() != ext:
                        dest_path = dest_path.with_suffix(ext)
                        logger.info(f"KrakenFiles: Extensión ajustada a {ext} → {dest_path}")

                total = 0
                with open(dest_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(1024 * 1024):
                        f.write(chunk)
                        total += len(chunk)

                logger.info(
                    f"KrakenFiles: ✅ Descargado {total / (1024*1024):.2f} MB → {dest_path}"
                )
                return True

    except Exception as e:
        logger.error(f"KrakenFiles: Error descargando desde CDN: {e}")
        if dest_path.exists():
            dest_path.unlink()
        return False
