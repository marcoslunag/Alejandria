"""
User Pydantic schemas for API validation
"""

from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool
    kcc_profile: str
    stk_device_serial: Optional[str] = None
    stk_device_name: Optional[str] = None
    auto_send_to_kindle: bool
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class UserSettingsUpdate(BaseModel):
    kcc_profile: Optional[str] = None
    stk_device_serial: Optional[str] = None
    stk_device_name: Optional[str] = None
    auto_send_to_kindle: Optional[bool] = None
