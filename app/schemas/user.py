from pydantic import BaseModel, EmailStr
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from app.schemas.statistics import MinecraftPlayerProfile
from app.schemas.goldsource_statistics import GoldSourcePlayerProfile

class UserBase(BaseModel):
    email: Optional[EmailStr] = None
    username: Optional[str] = None
    avatar: Optional[str] = None
    is_active: Optional[bool] = True
    is_admin: Optional[bool] = False
    is_super_admin: Optional[bool] = False
    xp: Optional[int] = 0
    level: Optional[int] = 1
    selected_badge_id: Optional[UUID] = None

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
    selected_badge_id: Optional[UUID] = None

    class Config:
        from_attributes = True

class LinkedAccountInfo(BaseModel):
    platform: str
    nickname: str
    external_id: str

class BadgePreview(BaseModel):
    id: UUID
    name: str
    image_url: str
    description: Optional[str] = None
    received_at: datetime
    
    class Config:
        from_attributes = True

class UserProfileHeader(BaseModel):
    id: UUID
    username: Optional[str] = None
    avatar: Optional[str] = None
    level: int
    xp: int
    xp_progress: int
    xp_for_next_level: int
    progress_percent: float
    linked_accounts: List[LinkedAccountInfo]

class UserProfile(BaseModel):
    header: UserProfileHeader
    badges: List[BadgePreview]
    minecraft_stats: List[MinecraftPlayerProfile]
    goldsource_stats: List[GoldSourcePlayerProfile]
