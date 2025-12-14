from pydantic import BaseModel, Field, field_validator
from typing import Optional, List


# ========== Batch запросы от игровых серверов ==========

class MinecraftServerData(BaseModel):
	"""Данные сервера для batch запроса"""
	server_uuid: str = Field(..., max_length=36, description="UUID сервера из игры")
	name: str = Field(..., max_length=100)
	web_address: Optional[str] = Field(None, max_length=100)
	is_installed: bool = True
	is_proxy: bool = False
	max_players: int = -1
	plan_version: str = Field(default="Old", max_length=18)


class MinecraftUserData(BaseModel):
	"""Данные игрока для batch запроса"""
	uuid: str = Field(..., max_length=36)
	registered: int = Field(..., description="Timestamp в миллисекундах")
	name: str = Field(..., max_length=36)
	times_kicked: int = 0


class MinecraftUserInfoData(BaseModel):
	"""Информация об игроке на сервере"""
	uuid: str = Field(..., max_length=36)
	server_uuid: str = Field(..., max_length=36)
	join_address: Optional[str] = Field(None, max_length=191)
	registered: int = Field(..., description="Timestamp в миллисекундах")
	opped: bool = False
	banned: bool = False


class MinecraftSessionData(BaseModel):
	"""Данные игровой сессии"""
	uuid: str = Field(..., max_length=36)
	server_uuid: str = Field(..., max_length=36)
	session_start: int = Field(..., description="Timestamp в миллисекундах")
	session_end: Optional[int] = Field(None, description="Timestamp в миллисекундах")
	mob_kills: Optional[int] = None
	deaths: Optional[int] = None
	afk_time: Optional[int] = Field(None, description="Время в миллисекундах")
	join_address: Optional[str] = Field(None, max_length=191)


class MinecraftNicknameData(BaseModel):
	"""Данные ника"""
	uuid: str = Field(..., max_length=36)
	nickname: str = Field(..., max_length=75)
	server_uuid: str = Field(..., max_length=36)
	last_used: int = Field(..., description="Timestamp в миллисекундах")


class MinecraftKillData(BaseModel):
	"""Данные убийства"""
	killer_uuid: str = Field(..., max_length=36)
	victim_uuid: str = Field(..., max_length=36)
	server_uuid: str = Field(..., max_length=36)
	weapon: Optional[str] = Field(None, max_length=30)
	date: int = Field(..., description="Timestamp в миллисекундах")
	session_id: Optional[int] = None


class MinecraftPingData(BaseModel):
	"""Данные пинга"""
	uuid: str = Field(..., max_length=36)
	server_uuid: str = Field(..., max_length=36)
	date: int = Field(..., description="Timestamp в миллисекундах")
	max_ping: Optional[int] = None
	min_ping: Optional[int] = None
	avg_ping: Optional[float] = None


class MinecraftPlatformData(BaseModel):
	"""Данные платформы игрока"""
	uuid: str = Field(..., max_length=36)
	platform: int = Field(..., description="0 = Java, 1 = Bedrock")
	bedrock_username: Optional[str] = Field(None, max_length=32)
	java_username: Optional[str] = Field(None, max_length=16)
	linked_player: Optional[str] = Field(None, max_length=16)
	language_code: Optional[str] = Field(None, max_length=8)
	version: Optional[str] = Field(None, max_length=16)


class MinecraftPluginVersionData(BaseModel):
	"""Данные версии плагина"""
	server_uuid: str = Field(..., max_length=36)
	plugin_name: str = Field(..., max_length=100)
	version: Optional[str] = Field(None, max_length=255)
	modified: int = Field(default=0, description="Timestamp в миллисекундах")


class MinecraftTPSData(BaseModel):
	"""Данные производительности сервера"""
	server_uuid: str = Field(..., max_length=36)
	date: int = Field(..., description="Timestamp в миллисекундах")
	tps: Optional[float] = None
	players_online: Optional[int] = None
	cpu_usage: Optional[float] = None
	ram_usage: Optional[int] = None
	entities: Optional[int] = None
	chunks_loaded: Optional[int] = None
	free_disk_space: Optional[int] = None


class MinecraftWorldData(BaseModel):
	"""Данные мира"""
	server_uuid: str = Field(..., max_length=36)
	world_name: str = Field(..., max_length=100)


class MinecraftWorldTimeData(BaseModel):
	"""Данные времени в мире"""
	uuid: str = Field(..., max_length=36)
	world_id: int
	server_uuid: str = Field(..., max_length=36)
	session_id: Optional[int] = None
	survival_time: int = Field(default=0, description="Время в миллисекундах")
	creative_time: int = Field(default=0, description="Время в миллисекундах")
	adventure_time: int = Field(default=0, description="Время в миллисекундах")
	spectator_time: int = Field(default=0, description="Время в миллисекундах")


class MinecraftVersionProtocolData(BaseModel):
	"""Данные версии протокола"""
	uuid: str = Field(..., max_length=36)
	protocol_version: int


class MinecraftGeolocationData(BaseModel):
	"""Данные геолокации"""
	uuid: str = Field(..., max_length=36)
	geolocation: Optional[str] = Field(None, max_length=50)
	last_used: int = Field(default=0, description="Timestamp в миллисекундах")


class MinecraftStatisticsBatch(BaseModel):
	"""Batch запрос статистики от игрового сервера"""
	server_uuid: str = Field(..., max_length=36, description="UUID сервера для идентификации")
	
	# Опциональные массивы данных
	servers: Optional[List[MinecraftServerData]] = None
	users: Optional[List[MinecraftUserData]] = None
	user_info: Optional[List[MinecraftUserInfoData]] = None
	sessions: Optional[List[MinecraftSessionData]] = None
	nicknames: Optional[List[MinecraftNicknameData]] = None
	kills: Optional[List[MinecraftKillData]] = None
	pings: Optional[List[MinecraftPingData]] = None
	platforms: Optional[List[MinecraftPlatformData]] = None
	plugin_versions: Optional[List[MinecraftPluginVersionData]] = None
	tps: Optional[List[MinecraftTPSData]] = None
	worlds: Optional[List[MinecraftWorldData]] = None
	world_times: Optional[List[MinecraftWorldTimeData]] = None
	version_protocols: Optional[List[MinecraftVersionProtocolData]] = None
	geolocations: Optional[List[MinecraftGeolocationData]] = None

	@field_validator('server_uuid')
	@classmethod
	def validate_server_uuid(cls, v: str) -> str:
		if len(v) != 36:
			raise ValueError("server_uuid must be 36 characters long")
		return v


# ========== API ответы для фронта ==========

class MinecraftUserStats(BaseModel):
	"""Статистика игрока"""
	uuid: str
	name: str
	registered: int
	times_kicked: int
	total_sessions: int
	total_playtime: int  # в миллисекундах
	total_kills: int
	total_deaths: int
	servers: List[str]  # список server_uuid

	class Config:
		from_attributes = True


class MinecraftPlayerProfile(BaseModel):
	"""Профиль игрока"""
	uuid: str
	name: str
	registered: int
	current_nickname: Optional[str] = None
	platform: Optional[int] = None
	last_seen: Optional[int] = None
	total_playtime: int
	total_kills: int
	total_deaths: int
	servers_played: List[str]

	class Config:
		from_attributes = True


class MinecraftSessionResponse(BaseModel):
	"""Информация о сессии"""
	id: int
	server_id: int
	session_start: int
	session_date: str  # дата начала сессии в формате YYYY-MM-DD
	session_date_end: str  # дата конца сессии в формате YYYY-MM-DD
	session_end: Optional[int]
	mob_kills: Optional[int]
	deaths: Optional[int]
	afk_time: Optional[int]
	playtime: Optional[int]  # вычисленное время

	class Config:
		from_attributes = True


class MinecraftKillResponse(BaseModel):
	"""Информация об убийстве"""
	id: int
	killer_uuid: str
	victim_uuid: str
	killer_name: Optional[str] = None
	victim_name: Optional[str] = None
	weapon: Optional[str]
	date: int

	class Config:
		from_attributes = True


class MinecraftServerStats(BaseModel):
	"""Статистика сервера"""
	server_id: int
	server_uuid: str
	name: str
	total_players: int
	total_sessions: int
	average_tps: Optional[float] = None
	current_players: Optional[int] = None
	last_update: Optional[int] = None

	class Config:
		from_attributes = True


class MinecraftTopPlayer(BaseModel):
	"""Игрок в топе"""
	uuid: str
	name: str
	playtime: int
	kills: int
	deaths: int
	kd_ratio: float

	class Config:
		from_attributes = True


class BatchResponse(BaseModel):
	"""Ответ на batch запрос"""
	success: bool
	message: str
	processed: dict  # количество обработанных записей по типам
	errors: Optional[List[str]] = None

