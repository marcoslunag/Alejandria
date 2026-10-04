"""Telemetría persistente por scraper/host (roadmap #13)."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text
from app.database import Base


class ScraperStat(Base):
    """Éxitos/fallos acumulados por fuente (host de descarga o scraper).

    Se usa para priorización dinámica: los hosts/scrapers con mala
    tasa de éxito reciben penalización sobre su prioridad estática.
    """
    __tablename__ = "scraper_stats"

    key = Column(String(120), primary_key=True)   # "host:mediafire" | "scraper:zonacomics"
    kind = Column(String(10), index=True)         # 'host' | 'scraper'
    name = Column(String(60), index=True)         # 'mediafire', 'zonacomics', ...
    successes = Column(Integer, default=0)
    failures = Column(Integer, default=0)
    streak_failures = Column(Integer, default=0)  # fallos consecutivos (resetea con éxito)
    last_success_at = Column(DateTime)
    last_failure_at = Column(DateTime)
    last_error = Column(Text)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def attempts(self) -> int:
        return (self.successes or 0) + (self.failures or 0)

    @property
    def success_rate(self):
        a = self.attempts
        return (self.successes or 0) / a if a else None
