"""
Settings API Endpoints
Per-user settings (KCC, STK configuration)
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import logging
import os
import json
from pathlib import Path

from app.database import get_db
from app.models.user import User
from app.core.deps import get_current_user

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
    kcc_profile: str = "KPW5"
    stk_device_serial: Optional[str] = None
    stk_device_name: Optional[str] = None
    auto_send_to_kindle: bool = False
    is_stk_configured: bool = False

    class Config:
        from_attributes = True


class SettingsUpdate(BaseModel):
    kcc_profile: Optional[str] = None
    stk_device_serial: Optional[str] = None
    stk_device_name: Optional[str] = None
    auto_send_to_kindle: Optional[bool] = None


@router.get("", response_model=SettingsResponse)
async def get_settings(current_user: User = Depends(get_current_user)):
    """Get current user's settings"""
    return SettingsResponse(
        kcc_profile=current_user.kcc_profile or "KPW5",
        stk_device_serial=current_user.stk_device_serial,
        stk_device_name=current_user.stk_device_name,
        auto_send_to_kindle=current_user.auto_send_to_kindle,
        is_stk_configured=current_user.is_stk_configured
    )


@router.post("", response_model=SettingsResponse)
async def save_settings(
    data: SettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Save current user's settings"""
    if data.kcc_profile is not None:
        current_user.kcc_profile = data.kcc_profile
        write_kcc_config(current_user.kcc_profile)

    if data.stk_device_serial is not None:
        current_user.stk_device_serial = data.stk_device_serial

    if data.stk_device_name is not None:
        current_user.stk_device_name = data.stk_device_name

    if data.auto_send_to_kindle is not None:
        current_user.auto_send_to_kindle = data.auto_send_to_kindle

    db.commit()
    db.refresh(current_user)

    logger.info(f"Settings updated for user {current_user.username}")

    return SettingsResponse(
        kcc_profile=current_user.kcc_profile or "KPW5",
        stk_device_serial=current_user.stk_device_serial,
        stk_device_name=current_user.stk_device_name,
        auto_send_to_kindle=current_user.auto_send_to_kindle,
        is_stk_configured=current_user.is_stk_configured
    )


@router.get("/terabox-status")
async def get_terabox_status(current_user: User = Depends(get_current_user)):
    """Get TeraBox bypass status"""
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
