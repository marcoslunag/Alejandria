"""
Import API Endpoints
Status and control of the /imports folder watcher
"""

import shutil
import logging
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException

from app.core.deps import get_current_user
from app.models.user import User
from app.services.import_watcher import ImportWatcher

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/import", tags=["import"])

_watcher = ImportWatcher()


@router.get("/status")
async def get_import_status(current_user: User = Depends(get_current_user)):
    """Estado de la carpeta /imports: pendientes, procesados, fallidos"""
    try:
        return _watcher.get_status()
    except Exception as e:
        logger.error(f"Error getting import status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process")
async def trigger_import_processing(current_user: User = Depends(get_current_user)):
    """Dispara el procesamiento inmediato de la carpeta /imports"""
    try:
        await _watcher.process_import_queue()
        return {"ok": True, "message": "Import queue procesada"}
    except Exception as e:
        logger.error(f"Error processing import queue: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/retry/{filename}")
async def retry_failed_import(
    filename: str,
    current_user: User = Depends(get_current_user)
):
    """Mueve un archivo de /imports/failed a /imports para reintentarlo"""
    failed_path = _watcher.failed_dir / filename
    if not failed_path.exists():
        raise HTTPException(status_code=404, detail=f"Archivo no encontrado en failed: {filename}")

    # Sanitize: ensure filename doesn't try to escape the directory
    if '/' in filename or '\\' in filename or '..' in filename:
        raise HTTPException(status_code=400, detail="Nombre de archivo inválido")

    dest = _watcher.import_dir / filename
    shutil.move(str(failed_path), str(dest))
    return {"ok": True, "message": f"'{filename}' movido a /imports para reintento"}
