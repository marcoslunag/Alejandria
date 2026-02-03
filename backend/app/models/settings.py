"""
Settings Model
Stores application settings (SMTP, Kindle configuration, Amazon credentials)
"""

from sqlalchemy import Column, Integer, String, Boolean
from datetime import datetime
from app.database import Base


class AppSettings(Base):
    """Application settings stored in database"""

    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, index=True)

    # Kindle settings
    kindle_email = Column(String(255), nullable=True)

    # SMTP settings (for small files via email)
    smtp_server = Column(String(255), default="smtp.gmail.com")
    smtp_port = Column(Integer, default=587)
    smtp_user = Column(String(255), nullable=True)
    smtp_password = Column(String(255), nullable=True)  # App password (encrypted in production)
    smtp_from_email = Column(String(255), nullable=True)

    # Amazon credentials (for large files via Send to Kindle)
    amazon_email = Column(String(255), nullable=True)
    amazon_password = Column(String(255), nullable=True)  # Stored securely
    amazon_device_name = Column(String(255), nullable=True)  # Optional: specific Kindle device

    # Sync method preference
    # 'auto' = use Amazon for large files, email for small
    # 'amazon' = always use Amazon Send to Kindle
    # 'email' = always use email (will fail for large files)
    kindle_sync_method = Column(String(50), default="auto")

    # KCC Profile (Kindle model for conversion optimization)
    # KPW5 = Paperwhite 5, KO = Oasis, KS = Scribe, etc.
    kcc_profile = Column(String(20), default="KPW5")

    # STK (Send to Kindle) device preference
    # Store device serial to send only to specific Kindle
    stk_device_serial = Column(String(50), nullable=True)
    stk_device_name = Column(String(100), nullable=True)  # For display purposes

    # Feature flags
    auto_send_to_kindle = Column(Boolean, default=False)

    def __repr__(self):
        return f"<AppSettings(id={self.id}, kindle_email='{self.kindle_email}')>"

    @property
    def is_smtp_configured(self) -> bool:
        """Check if SMTP is fully configured"""
        return all([
            self.smtp_server,
            self.smtp_port,
            self.smtp_user,
            self.smtp_password,
            self.smtp_from_email
        ])

    @property
    def is_amazon_configured(self) -> bool:
        """Check if Amazon Send to Kindle is configured"""
        return bool(self.amazon_email and self.amazon_password)

    @property
    def is_kindle_configured(self) -> bool:
        """Check if any Kindle sending method is configured"""
        return self.is_amazon_configured or (bool(self.kindle_email) and self.is_smtp_configured)

    @property
    def can_send_large_files(self) -> bool:
        """Check if we can send large files (>25MB)"""
        return self.is_amazon_configured
