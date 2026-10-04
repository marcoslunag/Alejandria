"""
Rate limiting (roadmap #17)
Sliding-window rate limiter in-memory, thread-safe.

Los endpoints de búsqueda (manga/comics/libros) lanzan peticiones a
AniList/ComicVine/Google Books + scrapers, que son lentos y con rate limits
propios. Este módulo limita el nº de búsquedas por usuario para no saturar
las fuentes externas ni la API.

Patrón in-memory (mismo que el rate-limit de login en auth.py): no sobrevive
a un restart del proceso, pero es suficiente para un uso legítimo
(protege de bugs de polling agresivo y de abuso accidental).
"""
import threading
import time
from collections import defaultdict
from typing import Optional

from fastapi import Depends, HTTPException, status

from app.config import get_settings
from app.core.deps import get_current_user
from app.models.user import User


class SlidingWindowRateLimiter:
    """Ventana deslizante in-memory: máx. `max_requests` por `window_seconds`."""

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict = defaultdict(list)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        """Devuelve True y registra el hit si el key está bajo el límite."""
        now = time.time()
        cutoff = now - self.window_seconds
        with self._lock:
            hits = [t for t in self._hits[key] if t > cutoff]
            if len(hits) >= self.max_requests:
                self._hits[key] = hits
                return False
            hits.append(now)
            self._hits[key] = hits
            return True

    def remaining(self, key: str) -> int:
        """Hits disponibles restantes para el key (sin consumir)."""
        now = time.time()
        cutoff = now - self.window_seconds
        with self._lock:
            hits = [t for t in self._hits[key] if t > cutoff]
            self._hits[key] = hits
            return max(0, self.max_requests - len(hits))

    def reset(self, key: str):
        with self._lock:
            self._hits.pop(key, None)


# ── Limiter de búsquedas (instance lazy, configurable por settings) ──────────

_search_limiter: Optional[SlidingWindowRateLimiter] = None
_init_lock = threading.Lock()


def get_search_limiter() -> SlidingWindowRateLimiter:
    """Lazy singleton: lee SEARCH_RATE_LIMIT_MAX / WINDOW de settings al 1er uso."""
    global _search_limiter
    if _search_limiter is None:
        with _init_lock:
            if _search_limiter is None:
                settings = get_settings()
                _search_limiter = SlidingWindowRateLimiter(
                    max_requests=settings.SEARCH_RATE_LIMIT_MAX,
                    window_seconds=settings.SEARCH_RATE_LIMIT_WINDOW,
                )
    return _search_limiter


def rate_limit_search(current_user: User = Depends(get_current_user)):
    """Dependency para endpoints de búsqueda: máx. N búsquedas por usuario/ventana.

    Se aplica a GET /manga/search, /comics/search y /books/search.
    429 si se excede (el frontend lo muestra como toast de error).
    """
    limiter = get_search_limiter()
    if not limiter.allow(f"user:{current_user.id}"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiadas búsquedas en poco tiempo. Espera unos minutos y vuelve a intentarlo.",
        )
    return current_user
