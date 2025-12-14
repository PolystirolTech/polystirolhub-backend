from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import datetime
from app.models.game_server import ServerStatus

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
	port: Optional[int] = None
	resource_pack_url: Optional[str] = None
	resource_pack_hash: Optional[str] = None
	status: ServerStatus = ServerStatus.active

class GameServerCreate(GameServerBase):
	pass

class GameServerUpdate(BaseModel):
	name: Optional[str] = None
	game_type_id: Optional[UUID] = None
	banner_url: Optional[str] = None
	description: Optional[str] = None
	mods: Optional[list[str]] = None
	ip: Optional[str] = None
	port: Optional[int] = None
	resource_pack_url: Optional[str] = None
	resource_pack_hash: Optional[str] = None
	status: Optional[ServerStatus] = None

class GameServerResponse(GameServerBase):
	id: UUID
	status: ServerStatus
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
	port: Optional[int] = None
	resource_pack_url: Optional[str] = None
	resource_pack_hash: Optional[str] = None
	status: ServerStatus
	created_at: datetime
	updated_at: datetime

	class Config:
		from_attributes = True

# Схема ответа статуса сервера
class ServerStatusResponse(BaseModel):
	server_icon: Optional[str] = None  # base64
	motd: Optional[str] = None
	players_online: int = 0
	players_max: int = 0
	players_list: Optional[list[str]] = None
	ping: Optional[float] = None
	version: Optional[str] = None
	online: bool = False
	error: Optional[str] = None
