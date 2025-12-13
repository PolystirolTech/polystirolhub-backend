from pydantic import BaseModel, field_validator
from typing import Optional, Any
from uuid import UUID
from datetime import datetime, date
from enum import Enum

class QuestType(str, Enum):
	daily = "daily"
	achievement = "achievement"

class QuestBase(BaseModel):
	name: str
	description: Optional[str] = None
	quest_type: QuestType
	condition_key: str
	target_value: int
	reward_xp: int = 0
	is_active: bool = True
	
	@field_validator('quest_type', mode='before')
	@classmethod
	def convert_enum(cls, v: Any) -> str:
		"""Конвертирует SQLAlchemy enum в строку для Pydantic"""
		if isinstance(v, Enum):
			return v.value
		if isinstance(v, str):
			return v
		return str(v)

class QuestCreate(QuestBase):
	pass

class QuestUpdate(BaseModel):
	name: Optional[str] = None
	description: Optional[str] = None
	quest_type: Optional[QuestType] = None
	condition_key: Optional[str] = None
	target_value: Optional[int] = None
	reward_xp: Optional[int] = None
	is_active: Optional[bool] = None

class Quest(QuestBase):
	id: UUID
	created_at: datetime

	class Config:
		from_attributes = True

class UserQuestBase(BaseModel):
	progress: int = 0
	completed_at: Optional[datetime] = None
	claimed_at: Optional[datetime] = None
	quest_date: Optional[date] = None

class UserQuest(UserQuestBase):
	id: UUID
	user_id: UUID
	quest_id: UUID

	class Config:
		from_attributes = True

class UserQuestWithQuest(UserQuest):
	quest: Quest

	class Config:
		from_attributes = True

