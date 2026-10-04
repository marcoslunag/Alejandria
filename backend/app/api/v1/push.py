"""
Push API (roadmap #7 - Web Push)
- GET  /push/vapid-public-key : clave pública VAPID para subscribe()
- POST /push/subscribe        : guarda/actualiza la suscripción del usuario
- DELETE /push/subscribe      : borra la suscripción (endpoint en body)
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.push_subscription import PushSubscription
from app.core.deps import get_current_user
from app.services.push_service import get_public_key
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/push", tags=["push"])


class PushKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionIn(BaseModel):
    endpoint: str
    keys: PushKeys
    user_agent: Optional[str] = None


@router.get("/vapid-public-key")
def get_vapid_public_key(
    current_user: User = Depends(get_current_user),
):
    """Clave pública VAPID (base64url) para serviceWorker pushManager.subscribe()."""
    return {"publicKey": get_public_key()}


@router.post("/subscribe")
def subscribe(
    payload: PushSubscriptionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Guarda o actualiza (por endpoint) la suscripción push del usuario."""
    existing = db.query(PushSubscription).filter(
        PushSubscription.endpoint == payload.endpoint
    ).first()
    if existing:
        existing.user_id = current_user.id
        existing.p256dh = payload.keys.p256dh
        existing.auth = payload.keys.auth
        existing.user_agent = (payload.user_agent or "")[:256] or None
    else:
        db.add(PushSubscription(
            user_id=current_user.id,
            endpoint=payload.endpoint[:512],
            p256dh=payload.keys.p256dh,
            auth=payload.keys.auth,
            user_agent=(payload.user_agent or "")[:256] or None,
        ))
    db.commit()
    return {"ok": True}


@router.delete("/subscribe")
def unsubscribe(
    payload: PushSubscriptionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Borra la suscripción del usuario (solo la propia, evita IDOR)."""
    db.query(PushSubscription).filter(
        PushSubscription.endpoint == payload.endpoint,
        PushSubscription.user_id == current_user.id,
    ).delete()
    db.commit()
    return {"ok": True}
