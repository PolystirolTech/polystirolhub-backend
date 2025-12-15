from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel

from app.schemas.user import UserBase


class ServerInfo(BaseModel):
	id: UUID
	name: str
	status: str

	class Config:
		from_attributes = True


class ActivityResponse(BaseModel):
	id: UUID
	activity_type: str
	title: str
	description: Optional[str] = None
	meta_data: Optional[Dict[str, Any]] = None
	user: Optional[UserBase] = None
	server: Optional[ServerInfo] = None
	created_at: datetime

	class Config:
		from_attributes = True
