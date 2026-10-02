"""
Translation Service
Traduce textos de AniList al español
"""

import logging
import threading
import time
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)


class _TranslateRateLimiter:
    """
    Rate limiter thread-safe para Google Translate (endpoint gratuito).

    Google devuelve 429 con >~5 req/s. Este limitador espacia las llamadas
    con un intervalo mínimo fijo (cola de "slots"): si llegan N llamadas a la
    vez, salen espaciadas a 1/min_interval. Thread-safe porque el servicio se
    llama desde asyncio.to_thread (página de detalle) y desde el enricher
    semanal (scheduler).
    """

    def __init__(self, min_interval: float = 0.2):  # 0.2s → máx ~5 req/s
        self._min_interval = min_interval
        self._lock = threading.Lock()
        self._next_slot = 0.0

    def wait(self):
        while True:
            with self._lock:
                now = time.monotonic()
                if now >= self._next_slot:
                    self._next_slot = now + self._min_interval
                    return
                scheduled = self._next_slot
            # Duerme FUERA del lock (+10ms de margen para no despertar todos a la vez)
            time.sleep(max(0.0, scheduled - time.monotonic()) + 0.01)

# Traducción de géneros de AniList
GENRE_TRANSLATIONS = {
    'Action': 'Acción',
    'Adventure': 'Aventura',
    'Comedy': 'Comedia',
    'Drama': 'Drama',
    'Ecchi': 'Ecchi',
    'Fantasy': 'Fantasía',
    'Horror': 'Terror',
    'Mahou Shoujo': 'Mahou Shoujo',
    'Mecha': 'Mecha',
    'Music': 'Música',
    'Mystery': 'Misterio',
    'Psychological': 'Psicológico',
    'Romance': 'Romance',
    'Sci-Fi': 'Ciencia Ficción',
    'Slice of Life': 'Vida Cotidiana',
    'Sports': 'Deportes',
    'Supernatural': 'Sobrenatural',
    'Thriller': 'Thriller',
    'Hentai': 'Hentai',
    'Isekai': 'Isekai',
    'Shounen': 'Shonen',
    'Shoujo': 'Shojo',
    'Seinen': 'Seinen',
    'Josei': 'Josei',
    'Kids': 'Infantil',
    'Historical': 'Histórico',
    'Military': 'Militar',
    'Police': 'Policial',
    'School': 'Escolar',
    'Space': 'Espacial',
    'Vampire': 'Vampiros',
    'Martial Arts': 'Artes Marciales',
    'Samurai': 'Samuráis',
    'Demons': 'Demonios',
    'Magic': 'Magia',
    'Game': 'Juegos',
    'Parody': 'Parodia',
    'Super Power': 'Superpoderes',
    'Dementia': 'Demencia',
    'Cars': 'Coches',
}

# Traducción de estados de AniList
STATUS_TRANSLATIONS = {
    'FINISHED': 'Finalizado',
    'RELEASING': 'En publicación',
    'NOT_YET_RELEASED': 'Próximamente',
    'CANCELLED': 'Cancelado',
    'HIATUS': 'En pausa',
}

# Traducción de formatos de AniList
FORMAT_TRANSLATIONS = {
    'MANGA': 'Manga',
    'NOVEL': 'Novela',
    'ONE_SHOT': 'One Shot',
    'LIGHT_NOVEL': 'Novela Ligera',
    'MANHUA': 'Manhua',
    'MANHWA': 'Manhwa',
}


def translate_genres(genres: List[str]) -> List[str]:
    """Traduce lista de géneros al español"""
    if not genres:
        return []
    return [GENRE_TRANSLATIONS.get(g, g) for g in genres]


def translate_status(status: str) -> str:
    """Traduce estado al español"""
    if not status:
        return ''
    return STATUS_TRANSLATIONS.get(status, status)


def translate_format(format_type: str) -> str:
    """Traduce formato al español"""
    if not format_type:
        return ''
    return FORMAT_TRANSLATIONS.get(format_type, format_type)


class TranslatorService:
    """
    Servicio de traducción usando deep-translator (gratuito)
    Traduce descripciones al español de forma asíncrona
    """

    def __init__(self):
        self.translator = None
        # Máx ~5 req/s hacia Google (evita 429) + caché para no re-traducir
        # el mismo texto (el enricher semanal y la página de detalle repiten)
        self._rate_limiter = _TranslateRateLimiter(min_interval=0.2)
        self._cache: Dict[str, str] = {}
        self._init_translator()

    def _init_translator(self):
        """Inicializa el traductor si está disponible"""
        try:
            from deep_translator import GoogleTranslator
            self.translator = GoogleTranslator(source='en', target='es')
            logger.info("Translator service initialized")
        except ImportError:
            logger.warning("deep-translator not installed. Run: pip install deep-translator")
            self.translator = None
        except Exception as e:
            logger.warning(f"Could not initialize translator: {e}")
            self.translator = None

    def translate_text(self, text: str, max_length: int = 5000) -> str:
        """
        Traduce texto al español

        Args:
            text: Texto a traducir
            max_length: Longitud máxima (deep-translator tiene límite de ~5000 chars)

        Returns:
            Texto traducido o original si falla
        """
        if not text or not self.translator:
            return text

        # Limitar longitud
        if len(text) > max_length:
            text = text[:max_length] + "..."

        # Caché: el mismo texto (mismo manga, enricher semanal, visitas repetidas)
        # no se vuelve a enviar a Google
        cached = self._cache.get(text)
        if cached is not None:
            return cached

        # Rate limit ANTES de llamar a Google (máx ~5 req/s)
        self._rate_limiter.wait()

        try:
            translated = self.translator.translate(text)
            if translated:
                if len(self._cache) >= 1000:
                    self._cache.clear()  # cap simple de memoria
                self._cache[text] = translated
                return translated
            return text

        except Exception as e:
            logger.warning(f"Translation failed: {e}")
            return text

    def translate_description(self, description: str) -> str:
        """Traduce descripción de manga"""
        return self.translate_text(description)


# Instancia global del traductor
_translator_instance = None


def get_translator() -> TranslatorService:
    """Obtiene instancia singleton del traductor"""
    global _translator_instance
    if _translator_instance is None:
        _translator_instance = TranslatorService()
    return _translator_instance
