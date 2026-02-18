"""
SystemLog Model
Persistent system log entries for the admin panel
"""

from sqlalchemy import Column, Integer, String, DateTime, Text
from datetime import datetime
from app.database import Base


class SystemLog(Base):
    """System log entry"""

    __tablename__ = "system_logs"

    id = Column(Integer, primary_key=True, index=True)
    level = Column(String(10), nullable=False, index=True)  # INFO, WARNING, ERROR
    message = Column(Text, nullable=False)
    context = Column(Text, nullable=True)  # JSON string with extra context
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    def __repr__(self):
        return f"<SystemLog(id={self.id}, level='{self.level}', created_at='{self.created_at}')>"
