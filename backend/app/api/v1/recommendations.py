"""
Recommendations API - Recomendaciones locales sin IA
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.auth import get_current_user
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
