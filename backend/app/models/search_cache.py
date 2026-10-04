"""
SearchCache Model (roadmap #2)
Caché persistente de resultados de búsqueda (manga/cómic/libro).

El payload se guarda SIN estado por usuario: `in_library`/`library_id` se
recalculan en cada hit con una sola query (ver services/search_cache.py),
porque cada usuario tiene su propia biblioteca.
"""
from sqlalchemy import Column, Integer, String, DateTime, JSON
from datetime import datetime
from app.database import Base


class SearchCache(Base):
    """Caché de resultados de búsqueda con TTL (15 min, en services/search_cache.py)"""

    __tablename__ = "search_cache"

    id = Column(Integer, primary_key=True, index=True)
    # sha256(f"{tipo}|{q.lower().strip()}|{page}|{limit}|{extras}")
    query_hash = Column(String(64), unique=True, index=True, nullable=False)
    tipo = Column(String(20), nullable=False)  # manga | comic | book
    # {"results": [...], "total": int, "sources": [...]}
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<SearchCache(id={self.id}, tipo='{self.tipo}', hash={self.query_hash[:8]})>"
