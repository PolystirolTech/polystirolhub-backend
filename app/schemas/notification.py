from pydantic import BaseModel
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime

class NotificationBase(BaseModel):
	notification_type: str
	title: str
	message: Optional[str] = None
	reward_xp: int = 0
	reward_balance: int = 0
	meta_data: Optional[Dict[str, Any]] = None

class NotificationCreate(NotificationBase):
	user_id: UUID

class NotificationResponse(NotificationBase):
	id: UUID
	user_id: UUID
	created_at: datetime

	class Config:
		from_attributes = True
