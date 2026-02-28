"""
Alejandria FastAPI Application
Main entry point for the API
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import os
import sys

from app.config import get_settings
from app.database import init_db
from app.api.v1 import api_router
from app.core.deps import get_current_user
from app.models.user import User
from fastapi import Depends
from app.services.scheduler import ContentScheduler

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
scheduler: ContentScheduler = None


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

    # Initialize and start scheduler (unless disabled via env var)
    global scheduler
    disable_scheduler = os.environ.get("DISABLE_SCHEDULER", "").lower() in ("true", "1", "yes")
    if disable_scheduler:
        logger.info("Scheduler disabled (DISABLE_SCHEDULER=true) - running in separate container")
    else:
        try:
            from app.services.scheduler import set_scheduler

            scheduler = ContentScheduler(
                check_interval_hours=settings.CHECK_INTERVAL_HOURS,
                download_dir=settings.DOWNLOAD_DIR,
                library_dir=settings.LIBRARY_DIR
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


# Create FastAPI app — disable interactive docs in production
app = FastAPI(
    title=settings.APP_NAME,
    description="Tu biblioteca digital - manga, cómics y libros con descarga automática y envío a Kindle",
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
)

# Configure CORS � use CORS_ORIGINS_STR env var in production (comma-separated)
cors_origins = (
    [o.strip() for o in settings.CORS_ORIGINS_STR.split(",") if o.strip()]
    if settings.CORS_ORIGINS_STR
    else settings.CORS_ORIGINS
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
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
    response = {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "api": settings.API_V1_PREFIX
    }
    if settings.DEBUG:
        response["docs"] = "/docs"
    return response


# Health check
@app.get("/health")
def health_check():
    """Simple health check"""
    return {"status": "healthy"}


# Scheduler status endpoint
@app.get("/scheduler/status")
def scheduler_status(current_user: User = Depends(get_current_user)):
    """Get scheduler status (requires authentication)"""
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
