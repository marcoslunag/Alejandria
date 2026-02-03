"""
Settings Model
Stores application settings for STK (Send to Kindle) configuration
"""

from sqlalchemy import Column, Integer, String, Boolean
from app.database import Base


class AppSettings(Base):
    """Application settings stored in database"""

    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, index=True)

    # KCC Profile (Kindle model for conversion optimization)
    # KPW5 = Paperwhite 5, KO = Oasis, KS = Scribe, etc.
    kcc_profile = Column(String(20), default="KPW5")

    # STK (Send to Kindle) device preference
    stk_device_serial = Column(String(50), nullable=True)
    stk_device_name = Column(String(100), nullable=True)

    # Feature flags
    auto_send_to_kindle = Column(Boolean, default=False)

    def __repr__(self):
        return f"<AppSettings(id={self.id}, stk_device='{self.stk_device_name}')>"

    @property
    def is_stk_configured(self) -> bool:
        """Check if STK device is configured"""
        return bool(self.stk_device_serial)
