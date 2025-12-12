from pydantic import BaseModel, field_validator
from typing import Optional, Any
from uuid import UUID
from datetime import datetime
from enum import Enum

class BadgeType(str, Enum):
	temporary = "temporary"
	event = "event"
	permanent = "permanent"

class BadgeBase(BaseModel):
	name: str
	description: Optional[str] = None
	badge_type: BadgeType = BadgeType.permanent
	
	@field_validator('badge_type', mode='before')
	@classmethod
	def convert_enum(cls, v: Any) -> str:
		"""Конвертирует SQLAlchemy enum в строку для Pydantic"""
		if isinstance(v, Enum):
			return v.value
		if isinstance(v, str):
			return v
		return str(v)

class BadgeCreate(BadgeBase):
	pass

class BadgeUpdate(BaseModel):
	name: Optional[str] = None
	description: Optional[str] = None
	badge_type: Optional[BadgeType] = None

class Badge(BadgeBase):
	id: UUID
	image_url: str
	created_at: datetime

	class Config:
		from_attributes = True

class UserBadgeBase(BaseModel):
	pass

class UserBadge(UserBadgeBase):
	id: UUID
	user_id: UUID
	badge_id: UUID
	received_at: datetime
	expires_at: Optional[datetime] = None

	class Config:
		from_attributes = True

class UserBadgeWithBadge(UserBadge):
	badge: Badge

	class Config:
		from_attributes = True

class AwardBadgeRequest(BaseModel):
	expires_at: Optional[datetime] = None  # Для временных бэджиков

