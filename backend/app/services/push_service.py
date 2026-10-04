"""
Push Service (roadmap #7 - Web Push)
- Genera y persiste la pareja de claves VAPID en app_settings (BD), de modo que
  el API (subscribe) y el scheduler (send) compartan siempre la misma pareja.
- `send_push()` es fire-and-forget: NUNCA lanza; borra suscripciones muertas (404/410).
"""

import json
import logging
import threading

from app.database import SessionLocal
from app.models.settings import AppSettings
from app.models.push_subscription import PushSubscription

logger = logging.getLogger(__name__)

_VAPID_LOCK = threading.Lock()
_VAPID_CLAIMS = {"sub": "mailto:alejadria@localhost"}


def _get_or_create_app_settings(db):
    s = db.query(AppSettings).first()
    if not s:
        s = AppSettings(id=1)
        db.add(s)
        db.flush()
    return s


def _generate_vapid_pair() -> tuple:
    """Genera pareja P-256 y la devuelve como (public_b64url, private_b64url) raw."""
    from py_vapid import Vapid, b64urlencode
    from cryptography.hazmat.primitives import serialization
    v = Vapid()
    v.generate_keys()
    private_b64 = b64urlencode(
        v.private_key.private_numbers().private_value.to_bytes(32, "big")
    )
    public_b64 = b64urlencode(
        v.public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )
    )
    return public_b64, private_b64


def get_vapid_keys() -> tuple:
    """Devuelve (public_key, private_key) base64url, generando y guardando si faltan."""
    with _VAPID_LOCK:
        db = SessionLocal()
        try:
            s = _get_or_create_app_settings(db)
            if s.vapid_private_key and s.vapid_public_key:
                return s.vapid_public_key, s.vapid_private_key
            s.vapid_public_key, s.vapid_private_key = _generate_vapid_pair()
            db.commit()
            logger.info("Generated new VAPID key pair for Web Push")
            return s.vapid_public_key, s.vapid_private_key
        finally:
            db.close()


def get_public_key() -> str:
    public, _ = get_vapid_keys()
    return public


def send_push(user_id: int, title: str, body: str, url: str = "/", icon: str = "/icon-192.svg", tag: str = None) -> None:
    """
    Envía una notificación webpush a todas las suscripciones del usuario.
    Fire-and-forget: cualquier error se loguea y se traga (nunca rompe al caller).
    """
    try:
        from pywebpush import webpush, WebPushException
        from py_vapid import Vapid

        _, private_key = get_vapid_keys()
        vapid = Vapid.from_raw(private_key.encode("ascii"))
        db = SessionLocal()
        try:
            subs = db.query(PushSubscription).filter(PushSubscription.user_id == user_id).all()
            if not subs:
                return
            payload = json.dumps({
                "title": title,
                "body": body,
                "url": url,
                "icon": icon,
                "tag": tag or f"user-{user_id}",
            })
            for sub in subs:
                try:
                    webpush(
                        subscription_info={
                            "endpoint": sub.endpoint,
                            "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                        },
                        data=payload.encode("utf-8"),
                        vapid_private_key=vapid,
                        vapid_claims=_VAPID_CLAIMS,
                    )
                except WebPushException as e:
                    status = e.response.status_code if e.response is not None else None
                    if status in (404, 410):
                        db.delete(sub)
                        db.commit()
                        logger.info(f"Removed dead push subscription for user {user_id} (HTTP {status})")
                    else:
                        logger.warning(f"WebPush failed for user {user_id}: {e}")
        finally:
            db.close()
    except Exception as e:
        # Nunca lanzar: el envío es mejor-esfuerzo
        logger.warning(f"send_push error for user {user_id}: {e}")
