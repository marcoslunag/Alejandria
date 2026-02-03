"""
Translation Service
Traduce textos de AniList al español
"""

import logging
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

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

        try:
            # Limitar longitud
            if len(text) > max_length:
                text = text[:max_length] + "..."

            translated = self.translator.translate(text)
            return translated if translated else text

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
