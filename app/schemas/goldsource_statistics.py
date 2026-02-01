from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict

# ========== Batch requests from game servers ==========

class GoldSourceServerData(BaseModel):
	"""Server data for batch request"""
	server_uuid: str = Field(..., max_length=36, description="Server UUID from plugin")
	name: str = Field(..., max_length=100)
	address: Optional[str] = Field(None, max_length=64)
	max_players: int = 32

class GoldSourceUserData(BaseModel):
	"""Player data for batch request"""
	steam_id: str = Field(..., max_length=32)
	name: str = Field(..., max_length=64)
	registered: int = Field(..., description="Timestamp in ms")

class GoldSourceSessionData(BaseModel):
	"""Session data"""
	steam_id: str = Field(..., max_length=32)
	server_uuid: str = Field(..., max_length=36)
	map_name: Optional[str] = Field(None, max_length=64)
	session_start: int = Field(..., description="Timestamp in ms")
	session_end: Optional[int] = Field(None, description="Timestamp in ms")
	kills: int = 0
	deaths: int = 0
	headshots: int = 0

class GoldSourceKillData(BaseModel):
	"""Kill data"""
	killer_steam_id: Optional[str] = Field(None, max_length=32)
	victim_steam_id: str = Field(..., max_length=32)
	server_uuid: str = Field(..., max_length=36)
	weapon: Optional[str] = Field(None, max_length=32)
	headshot: bool = False
	date: int = Field(..., description="Timestamp in ms")
	
class GoldSourceFPSData(BaseModel):
	"""Server FPS data"""
	server_uuid: str = Field(..., max_length=36)
	date: int = Field(..., description="Timestamp in ms")
	fps: float
	players_online: int
	map_name: Optional[str] = Field(None, max_length=64)

class GoldSourcePlayerCountersData(BaseModel):
	"""Player counters (custom metrics)"""
	steam_id: str = Field(..., max_length=32)
	server_uuid: str = Field(..., max_length=36)
	counters: Dict[str, int] = Field(default_factory=dict)

class GoldSourceStatisticsBatch(BaseModel):
	"""Batch request from game server"""
	server_uuid: str = Field(..., max_length=36)
	
	servers: Optional[List[GoldSourceServerData]] = None
	users: Optional[List[GoldSourceUserData]] = None
	sessions: Optional[List[GoldSourceSessionData]] = None
	kills: Optional[List[GoldSourceKillData]] = None
	fps: Optional[List[GoldSourceFPSData]] = None
	counters: Optional[List[GoldSourcePlayerCountersData]] = None

	@field_validator('server_uuid')
	@classmethod
	def validate_server_uuid(cls, v: str) -> str:
		if len(v) != 36:
			raise ValueError("server_uuid must be 36 characters long")
		return v

# ========== API responses for frontend ==========

class GoldSourcePlayerProfile(BaseModel):
	"""Player profile"""
	steam_id: str
	name: str
	registered: int # ms
	total_playtime: int
	total_kills: int
	total_deaths: int
	total_headshots: int
	servers_played: List[str]

	class Config:
		from_attributes = True

class GoldSourceServerStats(BaseModel):
	"""Server statistics"""
	server_id: int
	server_uuid: str
	name: str
	total_players: int
	total_sessions: int
	average_fps: Optional[float] = None
	current_players: Optional[int] = None
	current_map: Optional[str] = None
	last_update: Optional[int] = None

	class Config:
		from_attributes = True

class GoldSourceTopPlayer(BaseModel):
	"""Top player entry"""
	steam_id: str
	name: str
	playtime: int
	kills: int
	deaths: int
	kd_ratio: float
	headshot_percentage: float

	class Config:
		from_attributes = True

class BatchResponse(BaseModel):
	success: bool
	message: str
	processed: dict
	errors: Optional[List[str]] = None
