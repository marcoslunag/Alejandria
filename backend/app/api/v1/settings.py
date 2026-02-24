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
    # Feature 4: Download quality preferences
    preferred_quality: str = "hq"
    preferred_format: str = "auto"
    max_file_size_mb: int = 0
    preferred_hosts: str = "[]"
    # Tipo de dispositivo de lectura
    ereader_type: str = "kindle"

    class Config:
        from_attributes = True


class SettingsUpdate(BaseModel):
    kcc_profile: Optional[str] = None
    stk_device_serial: Optional[str] = None
    stk_device_name: Optional[str] = None
    auto_send_to_kindle: Optional[bool] = None
    # Feature 4: Download quality preferences
    preferred_quality: Optional[str] = None
    preferred_format: Optional[str] = None
    max_file_size_mb: Optional[int] = None
    preferred_hosts: Optional[str] = None
    # Tipo de dispositivo de lectura
    ereader_type: Optional[str] = None


@router.get("", response_model=SettingsResponse)
async def get_settings(current_user: User = Depends(get_current_user)):
    """Get current user's settings"""
    return SettingsResponse(
        kcc_profile=current_user.kcc_profile or "KPW5",
        stk_device_serial=current_user.stk_device_serial,
        stk_device_name=current_user.stk_device_name,
        auto_send_to_kindle=current_user.auto_send_to_kindle,
        is_stk_configured=current_user.is_stk_configured,
        preferred_quality=current_user.preferred_quality or "hq",
        preferred_format=current_user.preferred_format or "auto",
        max_file_size_mb=current_user.max_file_size_mb or 0,
        preferred_hosts=current_user.preferred_hosts or "[]",
        ereader_type=current_user.ereader_type or "kindle",
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

    if data.preferred_quality is not None:
        current_user.preferred_quality = data.preferred_quality

    if data.preferred_format is not None:
        current_user.preferred_format = data.preferred_format

    if data.max_file_size_mb is not None:
        current_user.max_file_size_mb = data.max_file_size_mb

    if data.preferred_hosts is not None:
        current_user.preferred_hosts = data.preferred_hosts

    if data.ereader_type is not None:
        valid_types = {'kindle', 'kobo', 'pocketbook', 'android', 'other'}
        if data.ereader_type in valid_types:
            current_user.ereader_type = data.ereader_type

    db.commit()
    db.refresh(current_user)

    logger.info(f"Settings updated for user {current_user.username}")

    return SettingsResponse(
        kcc_profile=current_user.kcc_profile or "KPW5",
        stk_device_serial=current_user.stk_device_serial,
        stk_device_name=current_user.stk_device_name,
        auto_send_to_kindle=current_user.auto_send_to_kindle,
        is_stk_configured=current_user.is_stk_configured,
        preferred_quality=current_user.preferred_quality or "hq",
        preferred_format=current_user.preferred_format or "auto",
        max_file_size_mb=current_user.max_file_size_mb or 0,
        preferred_hosts=current_user.preferred_hosts or "[]",
        ereader_type=current_user.ereader_type or "kindle",
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
