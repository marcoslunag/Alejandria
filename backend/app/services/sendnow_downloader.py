"""
Send.now Downloader

send.now es un hosting de archivos simple con:
- Botón #downloadbtn en la página
- Sin captcha ni bot-protection
- Playwright hace click y captura el evento download

URL pattern: https://send.now/{id}
"""

import asyncio
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


async def download_from_sendnow(view_url: str, dest_path: Path) -> bool:
    """
    Descarga un archivo de send.now.

    Args:
        view_url: URL de la forma https://send.now/{id}
        dest_path: Ruta de destino donde guardar el archivo

    Returns:
        True si la descarga fue exitosa, False en caso contrario
    """
    logger.info(f"SendNow: Descargando desde {view_url}")

    page = None
    try:
        from app.services.book_scrapers.playwright_scraper import get_playwright_scraper

        scraper = await get_playwright_scraper()
        page = await scraper._create_page()

        logger.info("SendNow: Cargando página...")
        await page.goto(view_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)

        # Buscar el botón de descarga
        btn = await page.query_selector("#downloadbtn")
        if not btn:
            # Fallback: cualquier botón/link con texto de descarga
            btn = await page.query_selector(
                'a[id*=download], button[id*=download], '
                'a.btn--primary[href*=download], a[href*="send.now"]'
            )

        if not btn:
            logger.error(f"SendNow: No se encontró botón de descarga en {view_url}")
            return False

        btn_text = await btn.inner_text()
        logger.info(f"SendNow: Botón encontrado: {repr(btn_text.strip()[:60])}")

        dest_path.parent.mkdir(parents=True, exist_ok=True)

        async with page.expect_download(timeout=60000) as dl_info:
            await btn.click()
            logger.info("SendNow: Click realizado, esperando descarga...")

        dl = await dl_info.value
        suggested = dl.suggested_filename

        # Usar el nombre sugerido para determinar la extensión real
        if suggested:
            real_ext = Path(suggested).suffix.lower()
            if real_ext and dest_path.suffix.lower() != real_ext:
                dest_path = dest_path.with_suffix(real_ext)
                logger.info(f"SendNow: Extensión ajustada a {real_ext}")

        await dl.save_as(str(dest_path))
        size = dest_path.stat().st_size
        logger.info(
            f"SendNow: ✅ Descargado '{suggested}' → {dest_path.name} "
            f"({size / (1024*1024):.2f} MB)"
        )
        return True

    except Exception as e:
        logger.error(f"SendNow: Error descargando {view_url}: {e}")
        if dest_path.exists():
            dest_path.unlink()
        return False

    finally:
        if page:
            await page.close()
