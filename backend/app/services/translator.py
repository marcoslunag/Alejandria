"""
Translation Service
Traduce textos de AniList al español

Caché en dos niveles (roadmap #3):
- L1: memoria (dict, sobrevive mientras viva el proceso)
- L2: tabla `translations` (sobrevive a restarts y es compartida entre el
  proceso de API —página de detalle— y el worker de scheduler —enricher—)

El texto se indexa por SHA-256 del texto truncado/normalizado, que es
exactamente la cadena que se envía a Google Translate.
"""

import hashlib
import logging
import threading
import time
from typing import Optional, Dict, List

from sqlalchemy.exc import IntegrityError

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

    # ------------------------------------------------------------------
    # Caché persistente (tabla translations)
    # ------------------------------------------------------------------

    def _key(self, text: str) -> str:
        """Hash del texto tal y como se enviaría a Google (strip)."""
        return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()

    def _db_lookup(self, keys: Dict[str, str]) -> Dict[str, str]:
        """
        Busca en la caché persistente.
        keys: {source_hash: original_text} → {source_hash: translated}
        Nunca lanza: si la BD no está disponible devuelve {} (se traduce igual).
        """
        if not keys:
            return {}
        try:
            from app.database import SessionLocal
            from app.models.translation import Translation
            db = SessionLocal()
            try:
                rows = db.query(Translation).filter(
                    Translation.source_hash.in_(list(keys.keys()))
                ).all()
                return {r.source_hash: r.translated for r in rows}
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Translation DB lookup failed (procediendo sin caché): {e}")
            return {}

    def _db_store(self, text: str, translated: str) -> None:
        """Guarda en la caché persistente. Nunca lanza."""
        try:
            from app.database import SessionLocal
            from app.models.translation import Translation
            db = SessionLocal()
            try:
                db.add(Translation(
                    source_hash=self._key(text),
                    original=text,
                    translated=translated,
                ))
                db.commit()
            except IntegrityError:
                # Otro proceso (API vs scheduler) lo cacheó primero — no es error
                db.rollback()
            except Exception as e:
                db.rollback()
                logger.warning(f"Translation DB store failed: {e}")
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Translation DB unavailable: {e}")

    @staticmethod
    def _normalize(text: str, max_length: int) -> str:
        """Aplica el mismo truncado que se envía a Google (coherencia del hash)."""
        return text[:max_length] + "..." if len(text) > max_length else text

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

        # Limitar longitud (el hash se calcula sobre el texto truncado, que es
        # exactamente lo que se envía a Google)
        text = self._normalize(text, max_length)
        key = self._key(text)

        # L1: caché en memoria
        cached = self._cache.get(text)
        if cached is not None:
            return cached

        # L2: caché persistente (sobrevive a restarts, compartida con el scheduler)
        hits = self._db_lookup({key: text})
        if key in hits:
            if len(self._cache) >= 1000:
                self._cache.clear()  # cap simple de memoria
            self._cache[text] = hits[key]
            return hits[key]

        # Rate limit ANTES de llamar a Google (máx ~5 req/s)
        self._rate_limiter.wait()

        try:
            translated = self.translator.translate(text)
            if translated:
                if len(self._cache) >= 1000:
                    self._cache.clear()  # cap simple de memoria
                self._cache[text] = translated
                self._db_store(text, translated)
                return translated
            return text

        except Exception as e:
            logger.warning(f"Translation failed: {e}")
            return text

    def translate_description(self, description: str) -> str:
        """Traduce descripción de manga"""
        return self.translate_text(description)

    def translate_batch(self, texts: List[str], max_length: int = 5000) -> List[str]:
        """
        Traduce una lista de textos de una vez (roadmap #3).

        Deduplica entradas repetidas y reutiliza la caché persistente: solo los
        textos que NO están cacheados llegan a Google (cada uno espaciado por el
        rate limiter, ~5 req/s). Devuelve los resultados en el orden de entrada.

        Pensado para el enricher semanal: N descripciones nuevas → N llamadas
        espaciadas en vez de N llamadas por cada visita de detalle.
        """
        if not texts:
            return []
        unique: Dict[str, str] = {}
        for t in texts:
            if t and t not in unique:
                unique[t] = self.translate_text(t, max_length=max_length)
        return [unique.get(t, t) for t in texts]

    def get_cached_translations(self, texts: List[str], max_length: int = 5000) -> Dict[str, str]:
        """
        Devuelve {texto_original: traducido} solo para los textos YA en caché
        (memoria o BD), sin llamar a Google. El enricher lo usa para saber qué
        descripciones quedan por pre-traducir antes de `translate_batch`.
        """
        out: Dict[str, str] = {}
        pending: Dict[str, str] = {}  # source_hash → texto original de entrada
        for t in texts:
            if not t or t in out:
                continue
            norm = self._normalize(t, max_length)
            cached = self._cache.get(norm)
            if cached is not None:
                out[t] = cached
            else:
                pending[self._key(norm)] = t
        if pending:
            hits = self._db_lookup(pending)
            for key, translated in hits.items():
                original = pending[key]
                self._cache[self._normalize(original, max_length)] = translated
                out[original] = translated
        return out


# Instancia global del traductor
_translator_instance = None


def get_translator() -> TranslatorService:
    """Obtiene instancia singleton del traductor"""
    global _translator_instance
    if _translator_instance is None:
        _translator_instance = TranslatorService()
    return _translator_instance
