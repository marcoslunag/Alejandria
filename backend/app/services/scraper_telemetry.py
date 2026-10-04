"""
Telemetría persistente por scraper/host + priorización dinámica (roadmap #13).

- record_success/record_failure: upsert en `scraper_stats` por clave
  "host:<id>" (mediafire, mega, ...) o "scraper:<nombre>" (zonacomics, ...).
- dynamic_penalty: penalización sobre la prioridad ESTÁTICA según tasa de
  éxito observada y rachas de fallo (mínimo de intentos para actuar).
- effective_host_priority / sort_links_dynamically: orden de intentos de
  descarga ajustado en tiempo real.
- get_stats / reset: visibilidad y mantenimiento vía endpoints admin.

La telemetría NUNCA rompe el flujo principal: todo error de BD se traga y
se loguea a nivel debug (peor caso = seguir con prioridades estáticas).
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Umbrales de penalización
MIN_ATTEMPTS = 5      # Muestra mínima antes de penalizar
RATE_WARN = 0.5       # tasa < 50% → PENALTY_WARN
RATE_BAD = 0.3        # tasa < 30% → PENALTY_BAD
STREAK_BAD = 5        # 5+ fallos consecutivos → PENALTY_BAD

PENALTY_WARN = 2      # +2 sobre prioridad estática (baja 2 rangos)
PENALTY_BAD = 4       # +4 (casi bloqueado, pero siempre se intenta de último)


def _get_session_and_model():
    """Session perezoso: permite monkeypatch en tests y evita import cíclico."""
    from app.database import SessionLocal
    from app.models.scraper_stat import ScraperStat
    return SessionLocal(), ScraperStat


def _upsert(kind: str, name: str, success: bool, error: Optional[str] = None):
    if not kind or not name:
        return
    db, model = _get_session_and_model()
    try:
        key = f"{kind}:{name}"
        stat = db.query(model).filter(model.key == key).first()
        if not stat:
            stat = model(key=key, kind=kind, name=name, successes=0, failures=0,
                         streak_failures=0)
            db.add(stat)
        if success:
            stat.successes = (stat.successes or 0) + 1
            stat.streak_failures = 0
            stat.last_success_at = datetime.utcnow()
        else:
            stat.failures = (stat.failures or 0) + 1
            stat.streak_failures = (stat.streak_failures or 0) + 1
            stat.last_failure_at = datetime.utcnow()
            if error:
                stat.last_error = str(error)[:500]
        db.commit()
    except Exception as e:
        db.rollback()
        logger.debug(f"Telemetry: no se pudo registrar {kind}:{name} ({'ok' if success else 'fail'}): {e}")
    finally:
        db.close()


def record_success(kind: str, name: str) -> None:
    """Registrar éxito de descarga (host) o scrape/búsqueda (scraper)."""
    _upsert(kind, name, True)


def record_failure(kind: str, name: str, error: Optional[str] = None) -> None:
    """Registrar fallo de descarga (host) o scrape/búsqueda (scraper)."""
    _upsert(kind, name, False, error)


def _stat_to_dict(s) -> Dict:
    rate = s.success_rate
    return {
        "key": s.key,
        "kind": s.kind,
        "name": s.name,
        "successes": s.successes or 0,
        "failures": s.failures or 0,
        "attempts": s.attempts,
        "success_rate": round(rate, 3) if rate is not None else None,
        "streak_failures": s.streak_failures or 0,
        "last_success_at": s.last_success_at.isoformat() if s.last_success_at else None,
        "last_failure_at": s.last_failure_at.isoformat() if s.last_failure_at else None,
        "last_error": s.last_error,
        "dynamic_penalty": dynamic_penalty(s.kind, s.name),
    }


def get_stats() -> List[Dict]:
    """Todas las métricas persistidas, con tasa y penalización actual."""
    db, model = _get_session_and_model()
    try:
        rows = db.query(model).order_by(model.kind, model.name).all()
        return [_stat_to_dict(r) for r in rows]
    except Exception as e:
        logger.debug(f"Telemetry: no se pudieron leer stats: {e}")
        return []
    finally:
        db.close()


def reset(kind: str, name: str) -> bool:
    """Reset manual (admin): borra la fila de métricas."""
    if kind not in ("host", "scraper"):
        return False
    db, model = _get_session_and_model()
    try:
        deleted = db.query(model).filter(model.kind == kind, model.name == name).delete()
        db.commit()
        return deleted > 0
    except Exception as e:
        db.rollback()
        logger.debug(f"Telemetry: no se pudo resetear {kind}:{name}: {e}")
        return False
    finally:
        db.close()


def dynamic_penalty(kind: str, name: str) -> int:
    """
    Penalización a sumar a la prioridad estática según resultados observados.

    - < MIN_ATTEMPTS intentos → 0 (sin evidencia suficiente)
    - streak_failures >= STREAK_BAD → PENALTY_BAD
    - success_rate < RATE_BAD → PENALTY_BAD
    - success_rate < RATE_WARN → PENALTY_WARN
    """
    if not kind or not name:
        return 0
    db, model = _get_session_and_model()
    try:
        stat = db.query(model).filter(model.kind == kind, model.name == name).first()
    except Exception:
        db.rollback()
        return 0
    finally:
        db.close()
    if not stat:
        return 0
    if (stat.streak_failures or 0) >= STREAK_BAD:
        return PENALTY_BAD
    attempts = stat.attempts
    if attempts < MIN_ATTEMPTS:
        return 0
    rate = stat.success_rate
    if rate is None:
        return 0
    if rate < RATE_BAD:
        return PENALTY_BAD
    if rate < RATE_WARN:
        return PENALTY_WARN
    return 0


def effective_host_priority(url: str) -> int:
    """Prioridad estática del host + penalización dinámica observada."""
    from app.services.host_manager import get_host_priority, identify_host
    base = get_host_priority(url)
    host_id = identify_host(url)
    penalty = dynamic_penalty("host", host_id) if host_id else 0
    return base + penalty


def sort_links_dynamically(links: List[Dict]) -> List[Dict]:
    """
    Ordena links de descarga por prioridad dinámica (estática + telemetría).

    Fallback a orden original si algo falla (la telemetría nunca rompe el flujo).
    """
    if not links:
        return links
    try:
        return sorted(links, key=lambda l: effective_host_priority(l.get("url") or ""))
    except Exception as e:
        logger.debug(f"Telemetry: sort dinámico falló, uso orden original: {e}")
        return links
