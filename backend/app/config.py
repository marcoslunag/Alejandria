"""
Application Configuration
Uses Pydantic Settings for environment variable management
"""

from pydantic_settings import BaseSettings
from typing import Optional
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Application
    APP_NAME: str = "Alejandria"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql://manga:manga@localhost:5432/alejandria"

    # Paths
    DOWNLOAD_DIR: str = "/downloads"
    MANGA_DIR: str = "/manga"
    KINDLE_DIR: str = "/manga/kindle"

    # Kindle Email Settings
    KINDLE_EMAIL: Optional[str] = None

    # SMTP Settings
    SMTP_SERVER: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: Optional[str] = None

    # Scheduler Settings
    CHECK_INTERVAL_HOURS: int = 6
    CLEANUP_DAYS: int = 7

    # Scraper Settings
    SCRAPER_USER_AGENT: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    SCRAPER_TIMEOUT: int = 10
    SCRAPER_MAX_RETRIES: int = 3

    # Download Settings
    DOWNLOAD_CHUNK_SIZE: int = 8192
    DOWNLOAD_TIMEOUT: int = 300
    MAX_CONCURRENT_DOWNLOADS: int = 3

    # KCC Settings
    KCC_PROFILE: str = "KPW5"  # Kindle Paperwhite 5
    KCC_FORMAT: str = "EPUB"
    KCC_TIMEOUT: int = 300

    # API Settings
    API_V1_PREFIX: str = "/api/v1"
    CORS_ORIGINS: list = ["http://localhost:3000", "http://localhost:7878"]

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
