"""
Alejandria Scheduler Worker
Standalone scheduler that runs background jobs independently from the API server.
"""

import asyncio
import signal
import sys
import os
import logging

# Add backend to Python path so we can import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from app.config import get_settings
from app.database import init_db
from app.services.scheduler import ContentScheduler, set_scheduler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)


async def main():
    settings = get_settings()
    logger.info(f"Starting Alejandria Scheduler Worker")

    # Initialize database
    try:
        init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        sys.exit(1)

    # Create and start scheduler
    scheduler = ContentScheduler(
        check_interval_hours=settings.CHECK_INTERVAL_HOURS,
        download_dir=settings.DOWNLOAD_DIR,
        library_dir=settings.LIBRARY_DIR
    )
    set_scheduler(scheduler)
    scheduler.start()
    logger.info("Scheduler started with all background jobs")

    # Graceful shutdown
    stop_event = asyncio.Event()

    def shutdown(sig):
        logger.info(f"Received signal {sig}, shutting down...")
        scheduler.stop()
        stop_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: shutdown(s))

    # Wait forever until shutdown signal
    await stop_event.wait()
    logger.info("Scheduler worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
