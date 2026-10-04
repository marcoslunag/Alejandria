"""
Translation Model
Caché persistente de traducciones (en → es) para que sobrevivan a restarts
y sean compartidas entre el proceso de API (página de detalle) y el worker
de scheduler (enricher semanal).

El texto se indexa por hash (SHA-256) del texto truncado/normalizado, que es
exactamente la cadena que se envía a Google Translate.
"""

from sqlalchemy import Column, Integer, String, Text, DateTime
from datetime import datetime
from app.database import Base


class Translation(Base):
    """Caché de traducciones original → español"""

    __tablename__ = "translations"

    id = Column(Integer, primary_key=True)
    # SHA-256 del texto (tras truncado a max_length y strip) que se envió a Google
    source_hash = Column(String(64), unique=True, nullable=False, index=True)
    original = Column(Text, nullable=False)
    translated = Column(Text, nullable=False)
    source_lang = Column(String(10), default="en")
    target_lang = Column(String(10), default="es")
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Translation(source_hash='{self.source_hash[:8]}', created_at={self.created_at})>"
