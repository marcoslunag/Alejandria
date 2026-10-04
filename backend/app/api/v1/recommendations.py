"""
Recommendations API - Recomendaciones locales sin IA
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.core.deps import get_current_user
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("")
async def get_recommendations(
    limit: int = Query(20, ge=1, le=50),
    type: str = Query("all", regex="^(all|manga|comics|books)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Genera recomendaciones personalizadas basadas en la biblioteca del usuario.
    Sin IA - usa perfil de géneros, autores y ratings de la biblioteca.
    Cache en memoria por (user_id, día).
    """
    from app.services.recommender import get_recommender

    recommender = get_recommender()
    recommendations = await recommender.get_recommendations(
        user_id=current_user.id,
        db=db,
        limit=limit,
        content_type=type
    )

    return {"recommendations": recommendations, "total": len(recommendations)}


@router.get("/library-sections")
def get_library_sections(
    limit: int = Query(12, ge=1, le=24),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Discover 2.0 (roadmap #18): secciones de la biblioteca del usuario.

    - following:         monitored=True (watchlist inteligente)
    - continue_reading:  reading_status='reading'
    - recently_added:    los añadidos más recientes

    Cada item usa un shape unificado compatible con ContentCard (frontend).
    """
    from app.models.manga import Manga
    from app.models.comic import Comic
    from app.models.book import Book

    MODELS = [(Manga, "manga"), (Comic, "comic"), (Book, "book")]

    def _adapt(item, content_type: str) -> dict:
        return {
            "content_type": content_type,
            "library_id": item.id,
            "id": item.id,
            "title": item.title,
            "cover_image": item.cover_image,
            "cover": item.cover_image,
            "cover_color": getattr(item, "cover_color", None),
            "average_score": getattr(item, "average_score", None),
            "average_rating": getattr(item, "average_rating", None),
            # Book usa `categories` para géneros
            "genres": getattr(item, "genres", None) or getattr(item, "categories", None) or [],
            "authors": getattr(item, "authors", None) or [],
            "publisher": getattr(item, "publisher", None),
            "start_year": getattr(item, "start_year", None),
            "status": getattr(item, "status", None),
            "reading_status": item.reading_status,
            "monitored": item.monitored,
            "in_library": True,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }

    def _section(apply_filter) -> list:
        items = []
        for model, ctype in MODELS:
            q = db.query(model).filter(model.user_id == current_user.id)
            if apply_filter:
                q = apply_filter(q, model)
            for row in q.order_by(model.created_at.desc()).limit(limit).all():
                items.append(_adapt(row, ctype))
        items.sort(key=lambda x: x["created_at"] or "", reverse=True)
        return items[:limit]

    following = _section(lambda q, m: q.filter(m.monitored == True))
    continue_reading = _section(lambda q, m: q.filter(m.reading_status == "reading"))
    recently_added = _section(None)

    return {
        "following": following,
        "continue_reading": continue_reading,
        "recently_added": recently_added,
    }
