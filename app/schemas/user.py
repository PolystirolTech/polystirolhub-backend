from pydantic import BaseModel, EmailStr
from typing import Optional
from uuid import UUID
from datetime import datetime

class UserBase(BaseModel):
    email: Optional[EmailStr] = None
    username: Optional[str] = None
    avatar: Optional[str] = None
    is_active: Optional[bool] = True
    is_admin: Optional[bool] = False
    is_super_admin: Optional[bool] = False
    xp: Optional[int] = 0
    level: Optional[int] = 1

class UserCreate(UserBase):
    pass

class UserUpdate(UserBase):
    pass

class UserInDBBase(UserBase):
    id: UUID
    created_at: datetime

    class Config:
        from_attributes = True

class User(UserInDBBase):
    pass

class UserInDB(UserInDBBase):
    pass

class OAuthAccountBase(BaseModel):
    provider: str
    provider_account_id: str
    access_token: str
    refresh_token: Optional[str] = None
    expires_at: Optional[datetime] = None

class OAuthAccountCreate(OAuthAccountBase):
    pass

class OAuthAccount(OAuthAccountBase):
    id: UUID
    user_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True

class OAuthAccountPublic(BaseModel):
    """Public schema for OAuth account - safe to return to client"""
    provider: str
    provider_username: Optional[str] = None
    provider_avatar: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class LeaderboardPlayer(BaseModel):
    """Schema for player in leaderboard"""
    id: UUID
    username: Optional[str] = None
    level: int
    xp: int
    avatar: Optional[str] = None

    class Config:
        from_attributes = True
