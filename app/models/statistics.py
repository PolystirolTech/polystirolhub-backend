from sqlalchemy import Column, ForeignKey, Integer, String, Text, BigInteger, Double, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.base_class import Base

# ========== Системные таблицы ==========

class MinecraftServer(Base):
	"""Связь Minecraft серверов с game_servers"""
	__tablename__ = "minecraft_servers"

	id = Column(Integer, primary_key=True, autoincrement=True)
	game_server_id = Column(UUID(as_uuid=True), ForeignKey("game_servers.id"), nullable=False, unique=True, index=True)
	server_uuid = Column(String(36), nullable=False, unique=True, index=True)  # UUID сервера из игры
	name = Column(String(100), nullable=False)
	web_address = Column(String(100), nullable=True)
	is_installed = Column(Boolean, default=True, nullable=False)
	is_proxy = Column(Boolean, default=False, nullable=False)
	max_players = Column(Integer, default=-1, nullable=False)
	plan_version = Column(String(18), default='Old', nullable=False)

	game_server = relationship("GameServer", backref="minecraft_server")


class MinecraftUser(Base):
	"""Базовая информация об игроках Minecraft"""
	__tablename__ = "minecraft_users"

	id = Column(Integer, primary_key=True, autoincrement=True)
	uuid = Column(String(36), nullable=False, unique=True, index=True)
	registered = Column(BigInteger, nullable=False)  # timestamp в миллисекундах
	name = Column(String(36), nullable=False, index=True)
	times_kicked = Column(Integer, default=0, nullable=False)


class MinecraftUserInfo(Base):
	"""Информация об игроке на конкретном сервере"""
	__tablename__ = "minecraft_user_info"

	id = Column(Integer, primary_key=True, autoincrement=True)
	user_id = Column(Integer, ForeignKey("minecraft_users.id"), nullable=False, index=True)
	server_id = Column(Integer, ForeignKey("minecraft_servers.id"), nullable=False, index=True)
	join_address = Column(String(191), nullable=True)
	registered = Column(BigInteger, nullable=False)  # timestamp в миллисекундах
	opped = Column(Boolean, default=False, nullable=False)
	banned = Column(Boolean, default=False, nullable=False)

	user = relationship("MinecraftUser", backref="user_info")
	server = relationship("MinecraftServer", backref="user_info")


class MinecraftSession(Base):
	"""Игровые сессии"""
	__tablename__ = "minecraft_sessions"

	id = Column(Integer, primary_key=True, autoincrement=True)
	user_id = Column(Integer, ForeignKey("minecraft_users.id"), nullable=False, index=True)
	server_id = Column(Integer, ForeignKey("minecraft_servers.id"), nullable=False, index=True)
	session_start = Column(BigInteger, nullable=False)  # timestamp в миллисекундах
	session_end = Column(BigInteger, nullable=True)  # timestamp в миллисекундах
	mob_kills = Column(Integer, nullable=True)
	deaths = Column(Integer, nullable=True)
	afk_time = Column(BigInteger, nullable=True)  # время в миллисекундах
	join_address_id = Column(Integer, ForeignKey("minecraft_join_address.id"), default=1, nullable=False)

	user = relationship("MinecraftUser", backref="sessions")
	server = relationship("MinecraftServer", backref="sessions")
	join_address_rel = relationship("MinecraftJoinAddress", backref="sessions")


class MinecraftNickname(Base):
	"""История ников игроков"""
	__tablename__ = "minecraft_nicknames"

	id = Column(Integer, primary_key=True, autoincrement=True)
	uuid = Column(String(36), nullable=False, index=True)
	nickname = Column(String(75), nullable=False)
	server_uuid = Column(String(36), nullable=False, index=True)
	last_used = Column(BigInteger, nullable=False)  # timestamp в миллисекундах


class MinecraftKill(Base):
	"""Убийства игроков"""
	__tablename__ = "minecraft_kills"

	id = Column(Integer, primary_key=True, autoincrement=True)
	killer_uuid = Column(String(36), nullable=False, index=True)
	victim_uuid = Column(String(36), nullable=False, index=True)
	server_uuid = Column(String(36), nullable=False, index=True)
	weapon = Column(String(30), nullable=True)
	date = Column(BigInteger, nullable=False, index=True)  # timestamp в миллисекундах
	session_id = Column(Integer, ForeignKey("minecraft_sessions.id"), nullable=True)

	session = relationship("MinecraftSession", backref="kills")


class MinecraftPing(Base):
	"""Пинг игроков"""
	__tablename__ = "minecraft_ping"

	id = Column(Integer, primary_key=True, autoincrement=True)
	user_id = Column(Integer, ForeignKey("minecraft_users.id"), nullable=False, index=True)
	server_id = Column(Integer, ForeignKey("minecraft_servers.id"), nullable=False, index=True)
	date = Column(BigInteger, nullable=False, index=True)  # timestamp в миллисекундах
	max_ping = Column(Integer, nullable=True)
	min_ping = Column(Integer, nullable=True)
	avg_ping = Column(Double, nullable=True)

	user = relationship("MinecraftUser", backref="pings")
	server = relationship("MinecraftServer", backref="pings")


class MinecraftPlatform(Base):
	"""Платформы игроков (Java/Bedrock)"""
	__tablename__ = "minecraft_platforms"

	id = Column(Integer, primary_key=True, autoincrement=True)
	uuid = Column(String(36), nullable=False, unique=True, index=True)
	platform = Column(Integer, nullable=False)  # 0 = Java, 1 = Bedrock
	bedrock_username = Column(String(32), nullable=True)
	java_username = Column(String(16), nullable=True)
	linked_player = Column(String(16), nullable=True)
	language_code = Column(String(8), nullable=True)
	version = Column(String(16), nullable=True)


class MinecraftPluginVersion(Base):
	"""Версии плагинов на серверах"""
	__tablename__ = "minecraft_plugin_versions"

	id = Column(Integer, primary_key=True, autoincrement=True)
	server_id = Column(Integer, ForeignKey("minecraft_servers.id"), nullable=False, index=True)
	plugin_name = Column(String(100), nullable=False)
	version = Column(String(255), nullable=True)
	modified = Column(BigInteger, default=0, nullable=False)

	server = relationship("MinecraftServer", backref="plugin_versions")


class MinecraftTPS(Base):
	"""Производительность серверов (TPS и метрики)"""
	__tablename__ = "minecraft_tps"

	server_id = Column(Integer, ForeignKey("minecraft_servers.id"), primary_key=True, nullable=False)
	date = Column(BigInteger, primary_key=True, nullable=False, index=True)  # timestamp в миллисекундах
	tps = Column(Double, nullable=True)
	players_online = Column(Integer, nullable=True)
	cpu_usage = Column(Double, nullable=True)
	ram_usage = Column(BigInteger, nullable=True)
	entities = Column(Integer, nullable=True)
	chunks_loaded = Column(Integer, nullable=True)
	free_disk_space = Column(BigInteger, nullable=True)

	server = relationship("MinecraftServer", backref="tps_data")


class MinecraftWorld(Base):
	"""Миры на серверах"""
	__tablename__ = "minecraft_worlds"

	id = Column(Integer, primary_key=True, autoincrement=True)
	world_name = Column(String(100), nullable=False)
	server_uuid = Column(String(36), nullable=False, index=True)


class MinecraftWorldTime(Base):
	"""Время игроков в разных режимах игры"""
	__tablename__ = "minecraft_world_times"

	id = Column(Integer, primary_key=True, autoincrement=True)
	user_id = Column(Integer, ForeignKey("minecraft_users.id"), nullable=False, index=True)
	world_id = Column(Integer, ForeignKey("minecraft_worlds.id"), nullable=False, index=True)
	server_id = Column(Integer, ForeignKey("minecraft_servers.id"), nullable=False, index=True)
	session_id = Column(Integer, ForeignKey("minecraft_sessions.id"), nullable=True)
	survival_time = Column(BigInteger, default=0, nullable=False)  # время в миллисекундах
	creative_time = Column(BigInteger, default=0, nullable=False)
	adventure_time = Column(BigInteger, default=0, nullable=False)
	spectator_time = Column(BigInteger, default=0, nullable=False)

	user = relationship("MinecraftUser", backref="world_times")
	world = relationship("MinecraftWorld", backref="world_times")
	server = relationship("MinecraftServer", backref="world_times")
	session = relationship("MinecraftSession", backref="world_times")


class MinecraftJoinAddress(Base):
	"""Адреса подключений"""
	__tablename__ = "minecraft_join_address"

	id = Column(Integer, primary_key=True, autoincrement=True)
	join_address = Column(String(191), nullable=False, unique=True, index=True)


class MinecraftVersionProtocol(Base):
	"""Версии протокола"""
	__tablename__ = "minecraft_version_protocol"

	id = Column(Integer, primary_key=True, autoincrement=True)
	uuid = Column(String(36), nullable=False, unique=True, index=True)
	protocol_version = Column(Integer, nullable=False)


class MinecraftGeolocation(Base):
	"""Геолокации игроков"""
	__tablename__ = "minecraft_geolocations"

	id = Column(Integer, primary_key=True, autoincrement=True)
	user_id = Column(Integer, ForeignKey("minecraft_users.id"), nullable=False, index=True)
	geolocation = Column(String(50), nullable=True)
	last_used = Column(BigInteger, default=0, nullable=False)  # timestamp в миллисекундах

	user = relationship("MinecraftUser", backref="geolocations")


class MinecraftSettings(Base):
	"""Настройки серверов"""
	__tablename__ = "minecraft_settings"

	id = Column(Integer, primary_key=True, autoincrement=True)
	server_uuid = Column(String(39), nullable=False, unique=True, index=True)
	updated = Column(BigInteger, nullable=False)
	content = Column(Text, nullable=True)

