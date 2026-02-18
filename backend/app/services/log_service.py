"""
System Log Service
Persistent logging to DB for admin diagnostic panel
"""

import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.log_entry import SystemLog

logger = logging.getLogger(__name__)

# Only keep last N entries to avoid unbounded growth
MAX_LOG_ENTRIES = 1000


class SystemLogger:
    def _get_db(self) -> Session:
        return SessionLocal()

    def log(self, level: str, message: str, context: Optional[Dict[str, Any]] = None):
        """Insert a log entry into the DB."""
        db = self._get_db()
        try:
            entry = SystemLog(
                level=level.upper(),
                message=message,
                context=json.dumps(context) if context else None,
                created_at=datetime.utcnow(),
            )
            db.add(entry)
            db.commit()

            # Prune old entries if over limit
            count = db.query(SystemLog).count()
            if count > MAX_LOG_ENTRIES:
                oldest_ids = (
                    db.query(SystemLog.id)
                    .order_by(SystemLog.created_at.asc())
                    .limit(count - MAX_LOG_ENTRIES)
                    .all()
                )
                if oldest_ids:
                    db.query(SystemLog).filter(
                        SystemLog.id.in_([r.id for r in oldest_ids])
                    ).delete(synchronize_session=False)
                    db.commit()
        except Exception as e:
            logger.warning(f"SystemLogger: failed to write log entry: {e}")
            db.rollback()
        finally:
            db.close()

    def info(self, message: str, context: Optional[Dict[str, Any]] = None):
        self.log("INFO", message, context)

    def warning(self, message: str, context: Optional[Dict[str, Any]] = None):
        self.log("WARNING", message, context)

    def error(self, message: str, context: Optional[Dict[str, Any]] = None):
        self.log("ERROR", message, context)

    def get_recent(
        self,
        level: Optional[str] = None,
        limit: int = 50,
        db: Optional[Session] = None,
    ) -> List[Dict]:
        """Get recent log entries, optionally filtered by level."""
        close_db = False
        if db is None:
            db = self._get_db()
            close_db = True
        try:
            query = db.query(SystemLog).order_by(SystemLog.created_at.desc())
            if level:
                query = query.filter(SystemLog.level == level.upper())
            entries = query.limit(limit).all()
            return [
                {
                    "id": e.id,
                    "level": e.level,
                    "message": e.message,
                    "context": json.loads(e.context) if e.context else None,
                    "created_at": e.created_at.isoformat(),
                }
                for e in entries
            ]
        finally:
            if close_db:
                db.close()


_system_logger = SystemLogger()


def get_system_logger() -> SystemLogger:
    return _system_logger
