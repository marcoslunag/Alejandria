"""
User Model
Represents a user with authentication and per-user settings
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from datetime import datetime
from app.database import Base


class User(Base):
    """User model with embedded settings (KCC, STK, Kindle preferences)"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    # Auth
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    must_change_password = Column(Boolean, default=False)

    # Tipo de e-reader del usuario
    # 'kindle' | 'kobo' | 'pocketbook' | 'android' | 'other'
    ereader_type = Column(String(20), default='kindle', server_default='kindle')

    # Per-user Kindle/KCC settings (replaces AppSettings)
    kcc_profile = Column(String(20), default="KPW5")
    stk_device_serial = Column(String(50), nullable=True)
    stk_device_name = Column(String(100), nullable=True)
    auto_send_to_kindle = Column(Boolean, default=False)

    # Download quality preferences (Feature 4)
    preferred_quality = Column(String(10), default='hq')   # 'hq'|'lq'|'any'
    preferred_format = Column(String(10), default='auto')  # 'epub'|'cbz'|'auto'
    max_file_size_mb = Column(Integer, default=0)          # 0 = no limit
    preferred_hosts = Column(Text, default='[]')           # JSON list of host names

    # Notifications (Feature 3)
    last_notification_check = Column(DateTime, nullable=True)  # When user last checked notifications

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}')>"

    @property
    def is_stk_configured(self) -> bool:
        return bool(self.stk_device_serial)
