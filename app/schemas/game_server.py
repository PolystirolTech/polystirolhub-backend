from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import datetime

# GameType схемы
class GameTypeBase(BaseModel):
	name: str

class GameTypeCreate(GameTypeBase):
	pass

class GameTypeUpdate(BaseModel):
	name: Optional[str] = None

class GameTypeResponse(GameTypeBase):
	id: UUID
	created_at: datetime

	class Config:
		from_attributes = True

# GameServer схемы
class GameServerBase(BaseModel):
	name: str
	game_type_id: UUID
	banner_url: Optional[str] = None
	description: Optional[str] = None
	mods: list[str] = []
	ip: str

class GameServerCreate(GameServerBase):
	pass

class GameServerUpdate(BaseModel):
	name: Optional[str] = None
	game_type_id: Optional[UUID] = None
	banner_url: Optional[str] = None
	description: Optional[str] = None
	mods: Optional[list[str]] = None
	ip: Optional[str] = None

class GameServerResponse(GameServerBase):
	id: UUID
	created_at: datetime
	updated_at: datetime
	game_type: GameTypeResponse

	class Config:
		from_attributes = True

# Публичные схемы (без внутренних данных)
class GameServerPublic(BaseModel):
	id: UUID
	name: str
	game_type: GameTypeResponse
	banner_url: Optional[str] = None
	description: Optional[str] = None
	mods: list[str]
	ip: str
	created_at: datetime
	updated_at: datetime

	class Config:
		from_attributes = True
