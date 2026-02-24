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


class AdminCreateUser(BaseModel):
    """Schema for admin to create a new user"""
    username: str
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


class ChangePassword(BaseModel):
    current_password: str
    new_password: str


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool
    is_admin: bool = False
    must_change_password: bool = False
    kcc_profile: str
    stk_device_serial: Optional[str] = None
    stk_device_name: Optional[str] = None
    auto_send_to_kindle: bool
    ereader_type: str = "kindle"
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    must_change_password: bool = False
    user: UserResponse


class UserSettingsUpdate(BaseModel):
    kcc_profile: Optional[str] = None
    stk_device_serial: Optional[str] = None
    stk_device_name: Optional[str] = None
    auto_send_to_kindle: Optional[bool] = None
