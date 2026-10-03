"""
Registro de jobs de búsqueda en memoria (búsqueda progresiva).

Cada endpoint de búsqueda (manga/comics/books) devuelve YA los resultados de
metadata (AniList/ComicVine/Google Books, ~2-3s) y lanza la fase de scrapers
en background. El frontend hace polling a `GET /{tipo}/search/{job_id}` hasta
que `status == "complete"`.

Diseño:
- In-memory (el backend corre con 1 worker uvicorn, ver backend/start.sh).
- TTL de 10 min: limpieza lazy al crear/leer (sin scheduler).
- Los resultados se guardan como dicts JSON-serializables (pydantic .dict()).
- Cada job guarda el user_id: solo su dueño puede leerlo.
"""

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Los jobs caducan a los 10 minutos (más que el timeout máximo de scrapers: 45s)
JOB_TTL_SECONDS = 600


@dataclass
class SearchJob:
    job_id: str
    query: str
    user_id: int
    status: str = "in_progress"  # in_progress | complete
    created_at: float = field(default_factory=time.time)
    # Resultados: inicial = solo metadata; final = enriquecidos con scrapers
    results: List[Any] = field(default_factory=list)
    total: int = 0
    # Datos extra por tipo (p. ej. sources=["anilist"], total de ComicVine, page...)
    meta: Dict[str, Any] = field(default_factory=dict)


_JOBS: Dict[str, SearchJob] = {}
_LOCK = threading.Lock()


def _purge_expired_locked() -> int:
    """Borrar jobs caducados. Llamar con _LOCK adquirido."""
    now = time.time()
    expired = [k for k, j in _JOBS.items() if now - j.created_at > JOB_TTL_SECONDS]
    for k in expired:
        del _JOBS[k]
    return len(expired)


def create_job(
    query: str,
    user_id: int,
    initial_results: List[Any],
    total: int,
    meta: Optional[Dict[str, Any]] = None,
) -> SearchJob:
    """Crear un job in_progress con los resultados iniciales (metadata)."""
    job = SearchJob(
        job_id=uuid.uuid4().hex,
        query=query,
        user_id=user_id,
        results=initial_results,
        total=total,
        meta=meta or {},
    )
    with _LOCK:
        purged = _purge_expired_locked()
        _JOBS[job.job_id] = job
    if purged:
        logger.debug(f"search_jobs: purged {purged} expired job(s)")
    logger.info(
        f"search_jobs: created {job.job_id[:8]} for user {user_id} "
        f"query={query!r} initial_results={len(initial_results)}"
    )
    return job


def get_job(job_id: str, user_id: Optional[int] = None) -> Optional[SearchJob]:
    """Devolver el job si existe, no ha caducado y (si se pasa user_id) es suyo."""
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return None
        if time.time() - job.created_at > JOB_TTL_SECONDS:
            del _JOBS[job_id]
            return None
        if user_id is not None and job.user_id != user_id:
            return None
        return job


def complete_job(
    job_id: str,
    results: List[Any],
    total: Optional[int] = None,
) -> bool:
    """Marcar el job como complete con los resultados finales. False si no existe."""
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return False
        job.results = results
        job.total = total if total is not None else len(results)
        job.status = "complete"
        return True
