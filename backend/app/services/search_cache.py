"""
Search cache persistente (roadmap #2).

La búsqueda (AniList/ComicVine/Google Books + scrapers) es la parte más lenta
de la plataforma: 15-90s por consulta. Con caché TTL de 15 min, repetir una
búsqueda (o que otro usuario busque lo mismo) es instantáneo.

DISEÑO:
- Key: sha256(f"{tipo}|{q.lower().strip()}|{page}|{limit}|{extras}")
  - manga:  extras=""
  - comic:  extras=check_availability (cambia el pipeline: con job o sin)
  - book:   extras=f"{source}|{language or ''}"
- El payload se guarda SIN estado por usuario: `in_library`/`library_id` se
  recalculan en cada hit (annotate_in_library) porque cada usuario tiene su
  propia biblioteca. El resto del resultado (títulos, covers, fuentes de
  scrapers, scores) es global.
- TTL 15 min, expiración LAZY: se purga en cada put (una DELETE) y en cada
  get que toca una fila vencida. Sin worker extra.
- get/put NUNCA lanzan: un fallo de caché degrada a búsqueda en vivo, no a
  error 500.
"""

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TTL_SECONDS = 15 * 60  # 15 minutos


def _hash(tipo: str, q: str, page: int, limit: int, extras: str = "") -> str:
    key = f"{tipo}|{q.strip().lower()}|{page}|{limit}|{extras}"
    return hashlib.sha256(key.encode()).hexdigest()


def get_cached(tipo: str, q: str, page: int = 1, limit: int = 20,
               extras: str = "") -> Optional[Dict[str, Any]]:
    """Devuelve el payload {"results", "total", "sources"} si hay entrada
    vigente, o None. Nunca lanza."""
    from app.database import SessionLocal
    from app.models.search_cache import SearchCache

    h = _hash(tipo, q, page, limit, extras)
    db = SessionLocal()
    try:
        row = db.query(SearchCache).filter(SearchCache.query_hash == h).first()
        if not row:
            return None
        if row.created_at < datetime.utcnow() - timedelta(seconds=TTL_SECONDS):
            db.delete(row)
            db.commit()
            return None
        return row.payload
    except Exception as e:
        logger.warning(f"SearchCache get error ({tipo} '{q}'): {e}")
        return None
    finally:
        db.close()


def put_cached(tipo: str, q: str, results: List[Dict[str, Any]],
               total: int, sources: Optional[List[str]] = None,
               page: int = 1, limit: int = 20, extras: str = "") -> None:
    """Upsert del resultado + purge lazy de entradas vencidas. Nunca lanza.

    `results` debe ser JSON-serializable (r.dict() / dicts planos)."""
    from app.database import SessionLocal
    from app.models.search_cache import SearchCache

    h = _hash(tipo, q, page, limit, extras)
    payload = {"results": results, "total": total, "sources": sources or []}
    db = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(seconds=TTL_SECONDS)
        db.query(SearchCache).filter(
            SearchCache.created_at < cutoff
        ).delete(synchronize_session=False)

        row = db.query(SearchCache).filter(SearchCache.query_hash == h).first()
        now = datetime.utcnow()
        if row:
            row.payload = payload
            row.created_at = now
        else:
            db.add(SearchCache(query_hash=h, tipo=tipo, payload=payload, created_at=now))
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"SearchCache put error ({tipo} '{q}'): {e}")
    finally:
        db.close()


# ============================================================================
# Re-anotación de in_library por usuario (el payload es global)
# ============================================================================

def _annotate_manga(db, user_id: int, results: List[Dict[str, Any]]) -> None:
    from app.models.manga import Manga
    ids = [r.get("anilist_id") for r in results if r.get("anilist_id")]
    id_map = {}
    if ids:
        rows = db.query(Manga.id, Manga.anilist_id).filter(
            Manga.user_id == user_id, Manga.anilist_id.in_(ids)
        ).all()
        id_map = {a: i for i, a in rows}
    for r in results:
        if r.get("anilist_id") in id_map:
            r["in_library"] = True
            r["library_id"] = id_map[r["anilist_id"]]
        else:
            r["in_library"] = False
            r["library_id"] = None


def _annotate_comic(db, user_id: int, results: List[Dict[str, Any]]) -> None:
    from app.models.comic import Comic
    ids = [r.get("comicvine_id") for r in results if r.get("comicvine_id")]  # 0 = virtual
    id_map = {}
    if ids:
        rows = db.query(Comic.id, Comic.comicvine_id).filter(
            Comic.user_id == user_id, Comic.comicvine_id.in_(ids)
        ).all()
        id_map = {cv: i for i, cv in rows}
    for r in results:
        if r.get("comicvine_id") in id_map:
            r["in_library"] = True
            r["library_id"] = id_map[r["comicvine_id"]]
        else:
            r["in_library"] = False
            r["library_id"] = None


def _annotate_book(db, user_id: int, results: List[Dict[str, Any]]) -> None:
    """Libros: match por google_books_id y (para cards de scraper sin ID)
    por prefijo de título — misma regla que _enrich_book_search_results.
    Una sola query: los libros del usuario (id, google_books_id, title)."""
    from app.models.book import Book
    rows = db.query(Book.id, Book.google_books_id, Book.title).filter(
        Book.user_id == user_id
    ).all()
    gb_map = {g: i for i, g, t in rows if g}
    for r in results:
        if r.get("google_books_id") in gb_map:
            r["in_library"] = True
            r["library_id"] = gb_map[r["google_books_id"]]
            continue
        title = (r.get("title") or "").lower().strip()
        match = None
        if title:
            for i, g, t in rows:
                if not t:
                    continue
                t_lower = t.lower()
                if title[:35] in t_lower or t_lower[:35] in title:
                    match = i
                    break
        if match:
            r["in_library"] = True
            r["library_id"] = match
        else:
            r["in_library"] = False
            r["library_id"] = None


_ANNOTATORS = {
    "manga": _annotate_manga,
    "comic": _annotate_comic,
    "book": _annotate_book,
}


def annotate_in_library(tipo: str, db, user_id: int,
                        results: List[Dict[str, Any]]) -> None:
    """Recalcula in_library/library_id del payload (global) para el usuario
    que consulta. In-place. Nunca lanza."""
    try:
        _ANNOTATORS[tipo](db, user_id, results)
    except Exception as e:
        logger.warning(f"annotate_in_library error ({tipo}): {e}")
