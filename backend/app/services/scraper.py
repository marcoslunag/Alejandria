"""
TomosManga.com Scraper Service
Scrapes manga and chapter information from tomosmanga.com
Con sistema de priorización de hosts de descarga
"""

import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import re
from urllib.parse import urljoin, quote
import logging
import time

logger = logging.getLogger(__name__)

# Importar host manager para priorización
try:
    from app.services.host_manager import select_best_links, identify_host, get_host_priority
    HOST_MANAGER_AVAILABLE = True
except ImportError:
    HOST_MANAGER_AVAILABLE = False
    logger.warning("Host manager not available")


class TomosMangaScraper:
    """
    Scraper específico para tomosmanga.com

    Estructura del sitio:
    - Búsqueda: https://tomosmanga.com/?s=nombre-manga
    - Página manga: https://tomosmanga.com/descargar-nombre-manga/
    - Tomos: Botones con clase 'fasc-button' conteniendo enlaces a Terabox/OUO/MEGA
    """

    BASE_URL = "https://tomosmanga.com"

    def __init__(self, rate_limit: float = 1.0):
        """
        Initialize scraper

        Args:
            rate_limit: Minimum seconds between requests (default 1.0)
        """
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        self.rate_limit = rate_limit
        self.last_request = 0

    def _rate_limit_wait(self):
        """Enforce rate limiting between requests"""
        elapsed = time.time() - self.last_request
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self.last_request = time.time()

    def search_manga(self, query: str) -> List[Dict]:
        """
        Busca manga en tomosmanga.com

        Args:
            query: Término de búsqueda

        Returns:
            List[Dict]: [{'title': str, 'url': str, 'cover': str, 'slug': str}]
        """
        try:
            self._rate_limit_wait()

            search_url = f"{self.BASE_URL}/?s={quote(query)}"
            logger.info(f"Searching manga: {search_url}")

            response = self.session.get(search_url, timeout=15)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')
            results = []

            # Selector para artículos de búsqueda
            articles = soup.select('article.post, article.type-post, .search-result-item')

            if not articles:
                articles = soup.select('article')

            for article in articles[:20]:
                try:
                    # Buscar título y enlace
                    title_elem = article.select_one('h2.entry-title a, h3.entry-title a, .post-title a, h2 a')

                    if not title_elem:
                        continue

                    title = title_elem.text.strip()
                    url = title_elem.get('href', '')

                    # Buscar imagen de portada
                    cover_elem = article.select_one('img.wp-post-image, img.attachment-post-thumbnail, .post-thumbnail img, img')
                    cover = cover_elem.get('src', '') if cover_elem else None

                    # Generar slug desde URL
                    slug = self._generate_slug(url)

                    if title and url:
                        results.append({
                            'title': title,
                            'url': url,
                            'cover': cover,
                            'slug': slug
                        })
                        logger.debug(f"Found manga: {title}")

                except Exception as e:
                    logger.warning(f"Error parsing article: {e}")
                    continue

            logger.info(f"Found {len(results)} manga results for '{query}'")
            return results

        except requests.exceptions.RequestException as e:
            logger.error(f"Error searching manga: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error in search_manga: {e}")
            return []

    def get_manga_details(self, manga_url: str) -> Optional[Dict]:
        """
        Obtiene detalles del manga desde su página

        Args:
            manga_url: URL de la página del manga

        Returns:
            Dict: {'title', 'description', 'cover', 'chapters': []}
        """
        try:
            self._rate_limit_wait()

            logger.info(f"Fetching manga details: {manga_url}")

            response = self.session.get(manga_url, timeout=15)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            # Extraer título
            title_elem = soup.select_one('h1.entry-title, h1.post-title, h1')
            title = title_elem.text.strip() if title_elem else "Unknown Title"

            # Extraer descripción
            description_elem = soup.select_one('.entry-content p, .post-content p, article p')
            description = description_elem.text.strip() if description_elem else ""

            # Extraer portada
            cover_elem = soup.select_one('.wp-post-image, .post-thumbnail img, article img')
            cover = cover_elem.get('src', '') if cover_elem else None

            # Extraer tomos/capítulos
            chapters = self._extract_chapters(soup, manga_url, title)

            result = {
                'title': title,
                'description': description,
                'cover': cover,
                'chapters': chapters
            }

            logger.info(f"Found {len(chapters)} volumes for '{title}'")
            return result

        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting manga details: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in get_manga_details: {e}")
            return None

    def _extract_chapters(self, soup: BeautifulSoup, base_url: str, manga_title: str) -> List[Dict]:
        """
        Extrae lista de tomos con sus enlaces de descarga

        TomosManga usa botones con clase 'fasc-button' que contienen:
        - Texto: "One Piece Tomos [001-004]"
        - URL: Terabox, OUO.io, MEGA, etc.

        Args:
            soup: BeautifulSoup object de la página
            base_url: URL base para enlaces relativos
            manga_title: Título del manga para parsear rangos

        Returns:
            List[Dict]: [{'number': float, 'title': str, 'url': str, 'download_links': []}]
        """
        chapters = []
        seen_volumes = set()  # Para evitar duplicados

        # Buscar todos los botones de descarga
        download_buttons = soup.select('a.fasc-button')

        logger.info(f"Found {len(download_buttons)} download buttons")

        for button in download_buttons:
            try:
                # Obtener texto y URL
                button_text = button.get_text(strip=True)
                button_url = button.get('href', '')

                if not button_url or not button_text:
                    continue

                # Solo procesar enlaces de descarga
                if not self._is_download_link(button_url):
                    continue

                # Intentar extraer rango de tomos del texto
                # Patrones: "Tomos [001-004]", "Tomo 5", "Vol 1-3", etc.
                volume_range = self._extract_volume_range(button_text)

                if not volume_range:
                    logger.debug(f"Could not parse volume range from: {button_text}")
                    continue

                start_vol, end_vol = volume_range
                host = self._get_host(button_url)

                logger.debug(f"Found volumes {start_vol}-{end_vol} at {host}: {button_url}")

                # Crear un capítulo por cada tomo en el rango
                for vol_num in range(start_vol, end_vol + 1):
                    if vol_num in seen_volumes:
                        # Ya tenemos este volumen, añadir enlace alternativo
                        for chapter in chapters:
                            if chapter['number'] == vol_num:
                                chapter['download_links'].append({
                                    'url': button_url,
                                    'host': host,
                                    'text': f"{host} - Tomos {start_vol}-{end_vol}"
                                })
                        continue

                    seen_volumes.add(vol_num)

                    chapter = {
                        'number': float(vol_num),
                        'title': f"Tomo {vol_num:03d}",
                        'url': base_url,
                        'download_links': [{
                            'url': button_url,
                            'host': host,
                            'text': f"{host} - Tomos {start_vol}-{end_vol}"
                        }]
                    }
                    chapters.append(chapter)

            except Exception as e:
                logger.warning(f"Error parsing download button: {e}")
                continue

        # Seleccionar los mejores enlaces para cada capítulo
        for chapter in chapters:
            self._select_best_download_links(chapter)

        # Ordenar por número de volumen
        chapters.sort(key=lambda x: x['number'])

        logger.info(f"Extracted {len(chapters)} individual volumes from {len(download_buttons)} buttons")
        return chapters

    def _extract_volume_range(self, text: str) -> Optional[tuple]:
        """
        Extrae rango de volúmenes del texto

        Args:
            text: Texto como "One Piece Tomos [001-004]", "Tomos 01-05", "Tomo 5", etc.

        Returns:
            tuple: (start, end) o None
        """
        # Patrón 1: Rangos con corchetes: [001-004], [1-4], etc.
        range_pattern = r'\[(\d+)\s*-\s*(\d+)\]'
        match = re.search(range_pattern, text)
        if match:
            start = int(match.group(1))
            end = int(match.group(2))
            return (start, end)

        # Patrón 2: Rangos sin corchetes: "Tomos 01-05", "18-20", etc.
        # Busca "Tomos" o "Tomo" seguido de dígitos-dígitos
        range_no_bracket_pattern = r'(?:tomos?|vols?|volumes?)\s*(\d+)\s*-\s*(\d+)'
        match = re.search(range_no_bracket_pattern, text, re.IGNORECASE)
        if match:
            start = int(match.group(1))
            end = int(match.group(2))
            return (start, end)

        # Patrón 3: Tomo único: "Tomo 5", "Vol 3", etc.
        single_pattern = r'(?:tomo|vol|volumen|volume)\s*(\d+)'
        match = re.search(single_pattern, text, re.IGNORECASE)
        if match:
            vol = int(match.group(1))
            return (vol, vol)

        # Buscar cualquier número entre corchetes: [5]
        bracket_pattern = r'\[(\d+)\]'
        match = re.search(bracket_pattern, text)
        if match:
            vol = int(match.group(1))
            return (vol, vol)

        return None

    def _is_download_link(self, url: str) -> bool:
        """
        Verifica si una URL es un enlace de descarga válido

        Args:
            url: URL a verificar

        Returns:
            bool: True si es un enlace de descarga
        """
        download_hosts = [
            'mega.nz', 'mega.co',
            'mediafire.com',
            'drive.google.com',
            '1fichier.com',
            'uptobox.com',
            'uploaded.net',
            'dropbox.com',
            'zippyshare.com',
            'terabox.com',  # Popular en TomosManga
            'fireload.com',  # No requiere login
            'ouo.io',       # Acortador usado en TomosManga
            'ouo.press',
            'shrinkme.io'
        ]
        url_lower = url.lower()
        return any(host in url_lower for host in download_hosts)

    def _get_host(self, url: str) -> str:
        """
        Identifica el host del enlace de descarga

        Args:
            url: URL del enlace

        Returns:
            str: Nombre del servicio de hosting
        """
        url_lower = url.lower()

        if 'mega.nz' in url_lower or 'mega.co' in url_lower:
            return 'MEGA'
        elif 'mediafire' in url_lower:
            return 'MediaFire'
        elif 'drive.google' in url_lower:
            return 'Google Drive'
        elif '1fichier' in url_lower:
            return '1fichier'
        elif 'uptobox' in url_lower:
            return 'Uptobox'
        elif 'uploaded' in url_lower:
            return 'Uploaded'
        elif 'dropbox' in url_lower:
            return 'Dropbox'
        elif 'terabox' in url_lower:
            return 'TeraBox'
        elif 'fireload' in url_lower:
            return 'Fireload'
        elif 'ouo.io' in url_lower or 'ouo.press' in url_lower:
            return 'OUO.io'
        elif 'shrinkme' in url_lower:
            return 'ShrinkMe'

        return 'Unknown'

    def _generate_slug(self, url: str) -> str:
        """
        Genera slug desde URL

        Args:
            url: URL del manga

        Returns:
            str: Slug del manga
        """
        parts = url.rstrip('/').split('/')
        if parts:
            slug = parts[-1]
            slug = slug.replace('descargar-', '').replace('-manga', '')
            return slug

        return 'unknown'

    def _select_best_download_links(self, chapter: Dict) -> None:
        """
        Selecciona los mejores enlaces de descarga para un capítulo
        usando el sistema de priorización de hosts

        Args:
            chapter: Dict del capítulo con 'download_links'
        """
        download_links = chapter.get('download_links', [])

        if not download_links:
            return

        if HOST_MANAGER_AVAILABLE:
            # Usar el host manager para ordenar por prioridad
            sorted_links = select_best_links(download_links, max_links=2)

            if sorted_links:
                # Primer enlace = principal
                best_link = sorted_links[0]
                chapter['download_url'] = best_link.get('url')
                chapter['download_host'] = identify_host(best_link.get('url', '')) or best_link.get('host', 'unknown')

                # Segundo enlace = backup (si existe)
                if len(sorted_links) > 1:
                    backup_link = sorted_links[1]
                    chapter['backup_url'] = backup_link.get('url')

                logger.debug(f"Selected {chapter['download_host']} as primary for volume {chapter['number']}")
        else:
            # Fallback: usar el primer enlace disponible
            if download_links:
                chapter['download_url'] = download_links[0].get('url')
                chapter['download_host'] = download_links[0].get('host', 'unknown')

                if len(download_links) > 1:
                    chapter['backup_url'] = download_links[1].get('url')

    def test_connection(self) -> bool:
        """
        Prueba la conexión con tomosmanga.com

        Returns:
            bool: True si la conexión es exitosa
        """
        try:
            response = self.session.get(self.BASE_URL, timeout=10)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False
