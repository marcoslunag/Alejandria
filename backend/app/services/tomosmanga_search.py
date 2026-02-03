"""
TomosManga Search Service
Búsqueda automática de manga en TomosManga.com
"""

import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import logging
from slugify import slugify

logger = logging.getLogger(__name__)


class TomosMangaSearch:
    """Servicio de búsqueda en TomosManga"""

    def __init__(self):
        self.base_url = "https://tomosmanga.com"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
            'Connection': 'keep-alive'
        })

    def search(self, query: str) -> List[Dict]:
        """
        Busca manga en TomosManga

        Args:
            query: Título del manga a buscar

        Returns:
            Lista de resultados con {title, url, volumes_text}
        """
        try:
            # Construir URL de búsqueda
            search_url = f"{self.base_url}/?s={query.replace(' ', '+')}"

            logger.info(f"Searching TomosManga: {search_url}")

            response = self.session.get(search_url, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            results = []

            # Buscar todos los títulos de entrada
            entries = soup.select('h2.entry-title')

            for entry in entries:
                link = entry.find('a')
                if not link:
                    continue

                title = link.get_text(strip=True)
                url = link.get('href', '')

                if not url or not title:
                    continue

                # Extraer información de volúmenes del título
                # Ejemplo: "Chainsaw Man Tomos [01-21]"
                volumes_text = ""
                if '[' in title and ']' in title:
                    volumes_text = title[title.find('['):title.find(']')+1]

                results.append({
                    'title': title,
                    'url': url,
                    'volumes_text': volumes_text,
                    'source': 'tomosmanga'
                })

            logger.info(f"Found {len(results)} results for '{query}'")
            return results

        except Exception as e:
            logger.error(f"Error searching TomosManga: {e}")
            return []

    def find_best_match(self, query: str) -> Optional[Dict]:
        """
        Busca y retorna el mejor match para un manga.
        Prioriza: más tomos > versión completa > match exacto de título

        Args:
            query: Título del manga

        Returns:
            Mejor resultado o None
        """
        import re

        results = self.search(query)

        if not results:
            return None

        # Si solo hay un resultado, retornarlo
        if len(results) == 1:
            return results[0]

        query_lower = query.lower()
        query_slug = slugify(query)

        best_match = None
        best_score = -1000

        for result in results:
            score = 0
            title_lower = result['title'].lower()
            title = result['title']

            # Extraer número de tomos del título [01-72] o similar
            volume_count = 0
            range_match = re.search(r'\[(\d+)\s*-\s*(\d+)\]', title)
            if range_match:
                start = int(range_match.group(1))
                end = int(range_match.group(2))
                volume_count = end - start + 1
                # Puntos por cantidad de tomos (más tomos = mejor)
                score += volume_count * 2

            # Match por título exacto (muy importante)
            result_base_title = re.sub(r'\s*\[.*\].*$', '', title).strip().lower()
            result_slug = slugify(result_base_title)

            if query_lower == result_base_title or query_slug == result_slug:
                score += 100  # Match exacto
            elif query_lower in result_base_title or query_slug in result_slug:
                score += 50  # Match parcial

            # PREFERIR versiones "Completo"
            if 'completo' in title_lower:
                score += 30

            # PENALIZAR versiones alternativas
            if 're-edition' in title_lower or 'reedition' in title_lower:
                score -= 50
            if 'color' in title_lower or 'full color' in title_lower:
                score -= 20
            if 'guia' in title_lower or 'guía' in title_lower:
                score -= 100  # No es el manga principal

            # Penalizar si es spin-off o relacionado (ej: "Boruto: Naruto")
            if ':' in title and query_lower not in title_lower.split(':')[0]:
                score -= 80

            logger.debug(f"Score for '{title}': {score} (volumes: {volume_count})")

            if score > best_score:
                best_score = score
                best_match = result

        logger.info(f"Best match for '{query}': {best_match['title'] if best_match else 'None'} (score: {best_score})")
        return best_match


class MangayComicsSearch:
    """Servicio de búsqueda en MangayComics"""

    def __init__(self):
        self.base_url = "https://mangaycomics.com"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
            'Connection': 'keep-alive'
        })

    def search(self, query: str) -> List[Dict]:
        """
        Busca manga en MangayComics

        Args:
            query: Título del manga a buscar

        Returns:
            Lista de resultados con {title, url}
        """
        try:
            search_url = f"{self.base_url}/?s={query.replace(' ', '+')}"

            logger.info(f"Searching MangayComics: {search_url}")

            response = self.session.get(search_url, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            results = []

            # MangayComics tiene una estructura similar
            entries = soup.select('h2.entry-title, h3.entry-title')

            for entry in entries:
                link = entry.find('a')
                if not link:
                    continue

                title = link.get_text(strip=True)
                url = link.get('href', '')

                if not url or not title:
                    continue

                results.append({
                    'title': title,
                    'url': url,
                    'source': 'mangaycomics'
                })

            logger.info(f"Found {len(results)} results for '{query}'")
            return results

        except Exception as e:
            logger.error(f"Error searching MangayComics: {e}")
            return []