"""
MangayComics.com Scraper Service
Scrapes manga and volume/chapter information from mangaycomics.com
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


class MangayComicsScraper:
    """
    Scraper específico para mangaycomics.com

    Estructura del sitio:
    - Búsqueda: https://mangaycomics.com/?s=nombre-manga
    - Página manga: https://mangaycomics.com/descargar/nombre-manga/
    - Tomos: Links DDL (MEGA, MediaFire, etc)
    """

    BASE_URL = "https://mangaycomics.com"

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
        Busca manga en mangaycomics.com

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

            # Buscar artículos de resultados
            articles = soup.select('article.post, article.type-post, .search-result')

            if not articles:
                articles = soup.select('article')

            for article in articles[:20]:
                try:
                    # Buscar título y enlace
                    title_elem = article.select_one('h2 a, h3 a, .entry-title a, .post-title a')

                    if not title_elem:
                        continue

                    title = title_elem.text.strip()
                    url = title_elem.get('href', '')

                    # Buscar imagen
                    cover_elem = article.select_one('img')
                    cover = cover_elem.get('src', '') if cover_elem else None

                    # Generar slug
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
            chapters = self._extract_volumes(soup, manga_url)

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

    def _extract_volumes(self, soup: BeautifulSoup, base_url: str) -> List[Dict]:
        """
        Extrae lista de tomos con sus enlaces de descarga

        Args:
            soup: BeautifulSoup object de la página
            base_url: URL base para enlaces relativos

        Returns:
            List[Dict]: [{'number': float, 'title': str, 'url': str, 'download_links': []}]
        """
        volumes = []

        # Buscar contenido principal
        content = soup.select_one('.entry-content, .post-content, article')
        if not content:
            return volumes

        # NUEVA LÓGICA: Buscar botones de Elementor primero (estructura moderna)
        elementor_buttons = content.find_all('span', class_='elementor-button-text')

        if elementor_buttons:
            logger.info(f"Found {len(elementor_buttons)} Elementor buttons, using modern extraction")

            # Diccionario para agrupar links por número de volumen
            volumes_dict = {}

            for span in elementor_buttons:
                button_text = span.get_text(strip=True)

                # Solo procesar si tiene "Tomo" o "Tomos"
                if 'tomo' not in button_text.lower():
                    continue

                # Buscar el <a> padre
                parent_a = span.find_parent('a')
                if not parent_a:
                    continue

                href = parent_a.get('href', '')
                if not href:
                    continue

                # Extraer número de tomo del texto
                volume_num = self._extract_volume_number(button_text)
                if not volume_num:
                    continue

                # Si el volumen ya existe, agregar link; si no, crear nuevo
                if volume_num not in volumes_dict:
                    volumes_dict[volume_num] = {
                        'number': volume_num,
                        'title': button_text,
                        'url': base_url,
                        'download_links': []
                    }

                # Agregar link al volumen
                volumes_dict[volume_num]['download_links'].append({
                    'url': href,
                    'host': self._get_host(href),
                    'text': button_text
                })

            # Convertir dict a lista y seleccionar mejores links
            for volume_data in volumes_dict.values():
                self._select_best_download_links(volume_data)
                volumes.append(volume_data)

            # Ordenar por número y retornar
            volumes.sort(key=lambda x: x['number'])
            logger.info(f"Extracted {len(volumes)} volumes from Elementor buttons")
            return volumes

        # LÓGICA ANTIGUA: Buscar por headers (para sitios con estructura antigua)
        # Buscar secciones de tomos (divs, headers, etc.)
        volume_sections = []

        # Buscar por headers (h2, h3, h4) que contengan "tomo", "volumen", etc.
        headers = content.find_all(['h2', 'h3', 'h4', 'h5', 'strong', 'b'])

        current_volume_data = None

        for header in headers:
            header_text = header.get_text(strip=True)
            volume_num = self._extract_volume_number(header_text)

            if volume_num:
                # Si ya teníamos un volumen anterior, guardarlo
                if current_volume_data and current_volume_data.get('download_links'):
                    volumes.append(current_volume_data)

                # Iniciar nuevo volumen
                current_volume_data = {
                    'number': volume_num,
                    'title': header_text,
                    'url': base_url,
                    'download_links': []
                }

                # Buscar enlaces después del header
                sibling = header.find_next_sibling()
                links_found = 0

                while sibling and links_found < 20:  # Limitar búsqueda
                    if sibling.name in ['h2', 'h3', 'h4', 'h5']:
                        # Encontramos otro header, parar
                        break

                    # Buscar enlaces en este elemento y sus hijos
                    links = sibling.find_all('a', href=True)
                    for link in links:
                        href = link.get('href', '')
                        if self._is_download_link(href):
                            current_volume_data['download_links'].append({
                                'url': href,
                                'host': self._get_host(href),
                                'text': link.text.strip()
                            })
                            links_found += 1

                    sibling = sibling.find_next_sibling()

        # Añadir el último volumen
        if current_volume_data and current_volume_data.get('download_links'):
            volumes.append(current_volume_data)

        # Seleccionar los mejores enlaces para cada volumen
        for volume in volumes:
            self._select_best_download_links(volume)

        # Ordenar por número
        volumes.sort(key=lambda x: x['number'])

        logger.info(f"Extracted {len(volumes)} volumes with prioritized download links")
        return volumes

    def _extract_volume_number(self, title: str) -> Optional[float]:
        """
        Extrae número de tomo del título

        Args:
            title: Título del tomo

        Returns:
            float o None: Número del tomo
        """
        # Patrones para tomos
        patterns = [
            r'tomo\s+(\d+(?:[.,]\d+)?)',
            r'vol(?:umen)?\s+(\d+(?:[.,]\d+)?)',
            r'vol\.?\s*(\d+(?:[.,]\d+)?)',
            r'#\s*(\d+(?:[.,]\d+)?)',
            r'(\d+(?:[.,]\d+)?)\s*-',
            r'^(\d+(?:[.,]\d+)?)[^\d]',
        ]

        for pattern in patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                number_str = match.group(1).replace(',', '.')
                try:
                    return float(number_str)
                except ValueError:
                    continue

        # Buscar cualquier número
        numbers = re.findall(r'\d+(?:[.,]\d+)?', title)
        if numbers:
            try:
                return float(numbers[0].replace(',', '.'))
            except ValueError:
                pass

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
            'terabox.com',
            'terabox.app',
            '1024terabox.com',
            'fireload.com',
            'ouo.io',
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
        elif 'zippyshare' in url_lower:
            return 'Zippyshare'
        elif 'terabox' in url_lower:
            return 'TeraBox'
        elif 'fireload' in url_lower:
            return 'Fireload'
        elif 'ouo.io' in url_lower or 'ouo.press' in url_lower:
            return 'OUO.io'
        elif 'shrinkme' in url_lower:
            return 'ShrinkMe'

        return 'Unknown'

    def _select_best_download_links(self, volume: Dict) -> None:
        """
        Selecciona los mejores enlaces de descarga para un volumen
        usando el sistema de priorización de hosts

        Args:
            volume: Dict del volumen con 'download_links'
        """
        download_links = volume.get('download_links', [])

        if not download_links:
            return

        if HOST_MANAGER_AVAILABLE:
            # Usar el host manager para ordenar por prioridad
            sorted_links = select_best_links(download_links, max_links=2)

            if sorted_links:
                # Primer enlace = principal
                best_link = sorted_links[0]
                volume['download_url'] = best_link.get('url')
                volume['download_host'] = identify_host(best_link.get('url', '')) or best_link.get('host', 'unknown')

                # Segundo enlace = backup (si existe)
                if len(sorted_links) > 1:
                    backup_link = sorted_links[1]
                    volume['backup_url'] = backup_link.get('url')

                logger.debug(f"Selected {volume['download_host']} as primary for volume {volume['number']}")
        else:
            # Fallback: usar el primer enlace disponible
            if download_links:
                volume['download_url'] = download_links[0].get('url')
                volume['download_host'] = download_links[0].get('host', 'unknown')

                if len(download_links) > 1:
                    volume['backup_url'] = download_links[1].get('url')

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
            slug = slug.replace('descargar-', '').replace('-manga', '').replace('-comic', '')
            return slug

        return 'unknown'

    def test_connection(self) -> bool:
        """
        Prueba la conexión con mangaycomics.com

        Returns:
            bool: True si la conexión es exitosa
        """
        try:
            response = self.session.get(self.BASE_URL, timeout=10)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False
