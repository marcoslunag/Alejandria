"""
OUO.io Link Resolver
Resuelve enlaces acortados de OUO.io para obtener el enlace final
Usa Playwright para resolver el bypass de 2 pasos (JS-heavy anti-bot)
"""

import asyncio
import logging
import re
from typing import Optional, Dict

logger = logging.getLogger(__name__)


async def _resolve_ouo_with_playwright(ouo_url: str) -> Optional[str]:
    """
    Resolve an OUO.io link using Playwright headless browser.
    OUO.io requires real JS execution — libraries and curl_cffi get 403.
    Uses the existing PlaywrightBookScraper singleton for browser management.
    """
    from app.services.book_scrapers.playwright_scraper import get_playwright_scraper

    page = None
    try:
        pw_scraper = await get_playwright_scraper()
        page = await pw_scraper._create_page()
        logger.info(f"OUO Playwright: Navigating to {ouo_url}")

        await page.goto(ouo_url, wait_until='domcontentloaded', timeout=20000)
        await asyncio.sleep(2)

        current_url = page.url

        if 'ouo.io' not in current_url and 'ouo.press' not in current_url:
            logger.info(f"OUO Playwright: Direct redirect to {current_url[:80]}")
            return current_url

        # OUO.io 2-step form bypass
        for step in range(2):
            form = await page.query_selector('form#form-bypass')
            if not form:
                form = await page.query_selector('form')

            if form:
                await asyncio.sleep(6)

                submit_btn = await page.query_selector(
                    'input[type="submit"], button[type="submit"], '
                    '.btn-main, #btn-main, a.btn'
                )

                if submit_btn:
                    try:
                        await submit_btn.click()
                        await asyncio.sleep(3)
                        try:
                            await page.wait_for_load_state('networkidle', timeout=10000)
                        except:
                            pass
                    except Exception as e:
                        logger.debug(f"OUO Playwright: Click failed step {step+1}: {e}")

                current_url = page.url
                if 'ouo.io' not in current_url and 'ouo.press' not in current_url:
                    logger.info(f"OUO Playwright: Resolved after step {step+1}: {current_url[:80]}")
                    return current_url

        # Fallback: search HTML for known host URLs
        html_content = await page.content()
        host_patterns = [
            (r'https?://(?:www\.)?fireload\.com/[^\s"\'<>]+', 'fireload'),
            (r'https?://(?:www\.)?mediafire\.com/[^\s"\'<>]+', 'mediafire'),
            (r'https?://(?:www\.)?mega\.nz/[^\s"\'<>]+', 'mega'),
            (r'https?://drive\.google\.com/[^\s"\'<>]+', 'gdrive'),
            (r'https?://(?:www\.)?terabox\.com/[^\s"\'<>]+', 'terabox'),
            (r'https?://1fichier\.com/[^\s"\'<>]+', '1fichier'),
        ]

        for pattern, host_name in host_patterns:
            matches = re.findall(pattern, html_content)
            if matches:
                resolved = matches[0].rstrip('"\'')
                logger.info(f"OUO Playwright: Found {host_name} in HTML: {resolved[:80]}")
                return resolved

        # Last resort: scan all anchor hrefs
        page_links = await page.query_selector_all('a[href]')
        for link in page_links:
            href = await link.get_attribute('href')
            if href and 'ouo' not in href.lower():
                known_hosts = ['mega.nz', 'mediafire.com', 'drive.google.com',
                               'terabox.com', '1fichier.com', 'fireload.com']
                if any(h in href.lower() for h in known_hosts):
                    logger.info(f"OUO Playwright: Found host link: {href[:80]}")
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


class OUOResolver:
    """Resolver para enlaces de OUO.io usando Playwright"""

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

        try:
            result = await asyncio.wait_for(
                _resolve_ouo_with_playwright(ouo_url),
                timeout=timeout / 1000
            )

            if result:
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
                elif 'terabox' in result_lower:
                    final_host = 'terabox'

                logger.info(f"OUO: Successfully resolved to {final_host}: {result}")
                return {
                    "ok": True,
                    "final_url": result,
                    "host": final_host
                }

            return {"ok": False, "error": "No se pudo resolver el enlace de OUO.io"}

        except asyncio.TimeoutError:
            logger.error(f"OUO: Global timeout ({timeout}ms) resolving {ouo_url}")
            return {"ok": False, "error": f"Timeout after {timeout}ms"}
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
