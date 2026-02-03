"""
Logging Configuration
Sets up structured logging for the application
"""

import logging
import sys
from typing import Any
from app.config import get_settings

settings = get_settings()


def setup_logging():
    """
    Configure application logging

    Sets up:
    - Console handler with formatted output
    - Log level from settings
    - Format for structured logging
    """
    # Get log level from settings
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

    # Set specific loggers
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    # Application loggers
    logging.getLogger("app").setLevel(log_level)

    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured at {settings.LOG_LEVEL} level")


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance

    Args:
        name: Logger name (usually __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)
