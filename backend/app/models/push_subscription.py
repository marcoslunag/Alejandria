"""
Push Subscription Model (roadmap #7 - Web Push)
Guarda la suscripción webpush de cada usuario para notificaciones
en segundo plano (nuevos capítulos, etc.) cuando la PWA está cerrada.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from app.database import Base


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # Endpoint HTTPS del push service (único por navegador/origen)
    endpoint = Column(String(512), unique=True, nullable=False)
    # Claves del cliente (WebCrypto P-256)
    p256dh = Column(String(256), nullable=False)
    auth = Column(String(128), nullable=False)
    user_agent = Column(String(256), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<PushSubscription(user_id={self.user_id}, endpoint=...{self.endpoint[-12:]})>"
