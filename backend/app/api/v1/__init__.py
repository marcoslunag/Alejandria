"""
API v1 Router
Combines all v1 endpoints
"""

from fastapi import APIRouter
from app.api.v1 import manga, system, queue, settings, kindle, kindle_sync

api_router = APIRouter()

# Include all routers
api_router.include_router(manga.router)
api_router.include_router(system.router)
api_router.include_router(queue.router)
api_router.include_router(settings.router)
api_router.include_router(kindle.router)
api_router.include_router(kindle_sync.router)
