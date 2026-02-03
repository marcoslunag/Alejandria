"""
Settings API Endpoints
Manage application settings (KCC, STK configuration)
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import logging
import os
import json
from pathlib import Path

from app.database import get_db
from app.models.settings import AppSettings

logger = logging.getLogger(__name__)

# Archivo de configuración compartido con el worker KCC
KCC_CONFIG_FILE = Path("/downloads/.kcc_config.json")


def write_kcc_config(profile: str):
    """Escribe la configuración de KCC para que el worker la lea"""
    try:
        config = {
            "profile": profile,
            "format": "EPUB"
        }
        KCC_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(KCC_CONFIG_FILE, 'w') as f:
            json.dump(config, f)
        logger.info(f"KCC config updated: profile={profile}")
    except Exception as e:
        logger.warning(f"Could not write KCC config: {e}")


router = APIRouter(prefix="/settings", tags=["settings"])


# Pydantic schemas
class SettingsResponse(BaseModel):
    # KCC settings
    kcc_profile: str = "KPW5"
    # STK device settings
    stk_device_serial: Optional[str] = None
    stk_device_name: Optional[str] = None
    # Feature flags
    auto_send_to_kindle: bool = False
    is_stk_configured: bool = False

    class Config:
        from_attributes = True


class SettingsUpdate(BaseModel):
    # KCC settings
    kcc_profile: Optional[str] = None
    # STK device settings
    stk_device_serial: Optional[str] = None
    stk_device_name: Optional[str] = None
    # Feature flags
    auto_send_to_kindle: Optional[bool] = None


def get_or_create_settings(db: Session) -> AppSettings:
    """Get settings from DB or create default"""
    settings = db.query(AppSettings).first()
    if not settings:
        settings = AppSettings()
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


@router.get("", response_model=SettingsResponse)
async def get_settings(db: Session = Depends(get_db)):
    """
    Get current application settings
    """
    settings = get_or_create_settings(db)

    return SettingsResponse(
        kcc_profile=settings.kcc_profile or "KPW5",
        stk_device_serial=settings.stk_device_serial,
        stk_device_name=settings.stk_device_name,
        auto_send_to_kindle=settings.auto_send_to_kindle,
        is_stk_configured=settings.is_stk_configured
    )


@router.post("", response_model=SettingsResponse)
async def save_settings(data: SettingsUpdate, db: Session = Depends(get_db)):
    """
    Save application settings
    """
    settings = get_or_create_settings(db)

    if data.kcc_profile is not None:
        settings.kcc_profile = data.kcc_profile
        write_kcc_config(settings.kcc_profile)

    if data.stk_device_serial is not None:
        settings.stk_device_serial = data.stk_device_serial
        
    if data.stk_device_name is not None:
        settings.stk_device_name = data.stk_device_name

    if data.auto_send_to_kindle is not None:
        settings.auto_send_to_kindle = data.auto_send_to_kindle

    db.commit()
    db.refresh(settings)

    logger.info("Settings updated")

    return SettingsResponse(
        kcc_profile=settings.kcc_profile or "KPW5",
        stk_device_serial=settings.stk_device_serial,
        stk_device_name=settings.stk_device_name,
        auto_send_to_kindle=settings.auto_send_to_kindle,
        is_stk_configured=settings.is_stk_configured
    )


@router.get("/terabox-status")
async def get_terabox_status():
    """
    Get TeraBox bypass status
    """
    try:
        terabox_cookie = os.getenv('TERABOX_COOKIE', '')
        
        has_cookies = bool(terabox_cookie and 'ndus=' in terabox_cookie)
        
        cookies_found = []
        if terabox_cookie:
            for part in terabox_cookie.split(';'):
                if '=' in part:
                    key = part.strip().split('=', 1)[0].strip()
                    cookies_found.append(key)
        
        is_valid = 'ndus' in cookies_found
        
        return {
            "ok": True,
            "is_configured": has_cookies,
            "is_valid": is_valid,
            "cookies_found": cookies_found,
            "message": "Configurado" if is_valid else "No configurado"
        }
    except Exception as e:
        logger.error(f"Error getting TeraBox status: {e}")
        return {
            "ok": False,
            "is_configured": False,
            "error": str(e)
        }
