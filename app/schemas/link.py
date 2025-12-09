from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
from datetime import datetime

class LinkCodeGenerateResponse(BaseModel):
	link_code: str

class LinkRequest(BaseModel):
	link_code: str
	game_id: str
	platform: str = "MC"
	platform_username: Optional[str] = None

class LinkResponse(BaseModel):
	status: str
	message: str

class ExternalLinkResponse(BaseModel):
	id: UUID
	platform: str
	external_id: str
	platform_username: Optional[str] = None
	created_at: datetime

	class Config:
		from_attributes = True

class LinkStatusResponse(BaseModel):
	user_id: UUID
	links: List[ExternalLinkResponse]

