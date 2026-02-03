"""
Alejandria FastAPI Application
Main entry point for the API
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import sys

from app.config import get_settings
from app.database import init_db
from app.api.v1 import api_router
from app.services.scheduler import MangaScheduler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        # Uncomment to log to file:
        # logging.FileHandler('/var/log/alejandria.log')
    ]
)

logger = logging.getLogger(__name__)

settings = get_settings()

# Global scheduler instance
scheduler: MangaScheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler
    Runs on startup and shutdown
    """
    # Startup
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")

    # Initialize database
    try:
        init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")

    # Initialize and start scheduler
    global scheduler
    try:
        from app.services.scheduler import set_scheduler

        scheduler = MangaScheduler(
            check_interval_hours=settings.CHECK_INTERVAL_HOURS,
            download_dir=settings.DOWNLOAD_DIR,
            manga_dir=settings.MANGA_DIR
        )
        set_scheduler(scheduler)  # Set global instance
        scheduler.start()
        logger.info("Scheduler started")
    except Exception as e:
        logger.error(f"Scheduler initialization failed: {e}")

    yield

    # Shutdown
    logger.info("Shutting down application")
    if scheduler:
        scheduler.stop()
        logger.info("Scheduler stopped")


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    description="Tu biblioteca digital - manga, cómics y libros con descarga automática y envío a Kindle",
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


# Include API routes
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


# Root endpoint
@app.get("/")
def root():
    """Root endpoint"""
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs",
        "api": settings.API_V1_PREFIX
    }


# Health check
@app.get("/health")
def health_check():
    """Simple health check"""
    return {"status": "healthy"}


# Scheduler status endpoint
@app.get("/scheduler/status")
def scheduler_status():
    """Get scheduler status"""
    if scheduler:
        return scheduler.get_status()
    else:
        return {"running": False, "message": "Scheduler not initialized"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=7878,
        reload=settings.DEBUG
    )
