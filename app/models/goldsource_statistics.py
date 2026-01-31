from sqlalchemy import Column, ForeignKey, Integer, String, BigInteger, Double, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.base_class import Base

# ========== GoldSource System Tables ==========

class GoldSourceServer(Base):
	"""Link GoldSource servers with game_servers"""
	__tablename__ = "goldsource_servers"

	id = Column(Integer, primary_key=True, autoincrement=True)
	game_server_id = Column(UUID(as_uuid=True), ForeignKey("game_servers.id"), nullable=False, unique=True, index=True)
	server_uuid = Column(String(36), nullable=False, unique=True, index=True)  # UUID of the server from the plugin
	name = Column(String(100), nullable=False)
	address = Column(String(64), nullable=True) # IP:Port
	max_players = Column(Integer, default=32, nullable=False)
	
	game_server = relationship("GameServer", backref="goldsource_server")


class GoldSourceUser(Base):
	"""Basic info about GoldSource players"""
	__tablename__ = "goldsource_users"

	id = Column(Integer, primary_key=True, autoincrement=True)
	steam_id = Column(String(32), nullable=False, unique=True, index=True) # STEAM_0:X:XXXXX
	registered = Column(BigInteger, nullable=False)  # timestamp in ms
	name = Column(String(64), nullable=False, index=True)
	
class GoldSourceUserInfo(Base):
	"""Player info on a specific server"""
	__tablename__ = "goldsource_user_info"

	id = Column(Integer, primary_key=True, autoincrement=True)
	user_id = Column(Integer, ForeignKey("goldsource_users.id"), nullable=False, index=True)
	server_id = Column(Integer, ForeignKey("goldsource_servers.id"), nullable=False, index=True)
	first_seen = Column(BigInteger, nullable=False)
	last_seen = Column(BigInteger, nullable=False)
	
	user = relationship("GoldSourceUser", backref="user_info")
	server = relationship("GoldSourceServer", backref="user_info")


class GoldSourceSession(Base):
	"""Game sessions"""
	__tablename__ = "goldsource_sessions"

	id = Column(Integer, primary_key=True, autoincrement=True)
	user_id = Column(Integer, ForeignKey("goldsource_users.id"), nullable=False, index=True)
	server_id = Column(Integer, ForeignKey("goldsource_servers.id"), nullable=False, index=True)
	map_id = Column(Integer, ForeignKey("goldsource_maps.id"), nullable=True)
	session_start = Column(BigInteger, nullable=False)  # timestamp in ms
	session_end = Column(BigInteger, nullable=True)  # timestamp in ms
	kills = Column(Integer, default=0, nullable=False)
	deaths = Column(Integer, default=0, nullable=False)
	headshots = Column(Integer, default=0, nullable=False)
	
	user = relationship("GoldSourceUser", backref="sessions")
	server = relationship("GoldSourceServer", backref="sessions")
	map = relationship("GoldSourceMap", backref="sessions")


class GoldSourceMap(Base):
	"""Maps on servers"""
	__tablename__ = "goldsource_maps"

	id = Column(Integer, primary_key=True, autoincrement=True)
	map_name = Column(String(64), nullable=False, unique=True)


class GoldSourceKill(Base):
	"""Kills logs"""
	__tablename__ = "goldsource_kills"

	id = Column(Integer, primary_key=True, autoincrement=True)
	killer_id = Column(Integer, ForeignKey("goldsource_users.id"), nullable=True, index=True) # Nullable for environmental kills
	victim_id = Column(Integer, ForeignKey("goldsource_users.id"), nullable=False, index=True)
	server_id = Column(Integer, ForeignKey("goldsource_servers.id"), nullable=False, index=True)
	weapon = Column(String(32), nullable=True)
	headshot = Column(Boolean, default=False, nullable=False)
	date = Column(BigInteger, nullable=False, index=True)  # timestamp in ms
	session_id = Column(Integer, ForeignKey("goldsource_sessions.id"), nullable=True)

	killer = relationship("GoldSourceUser", foreign_keys=[killer_id], backref="goldsource_kills_made")
	victim = relationship("GoldSourceUser", foreign_keys=[victim_id], backref="goldsource_deaths")
	server = relationship("GoldSourceServer")
	session = relationship("GoldSourceSession")


class GoldSourceFPS(Base):
	"""Server performance (FPS)"""
	__tablename__ = "goldsource_fps"

	server_id = Column(Integer, ForeignKey("goldsource_servers.id"), primary_key=True, nullable=False)
	date = Column(BigInteger, primary_key=True, nullable=False, index=True)  # timestamp in ms
	fps = Column(Double, nullable=True)
	players_online = Column(Integer, nullable=True)
	map_id = Column(Integer, ForeignKey("goldsource_maps.id"), nullable=True)

	server = relationship("GoldSourceServer", backref="fps_data")
	map = relationship("GoldSourceMap")

class GoldSourceMapTime(Base):
	"""Time spent on maps"""
	__tablename__ = "goldsource_map_times"
	
	id = Column(Integer, primary_key=True, autoincrement=True)
	user_id = Column(Integer, ForeignKey("goldsource_users.id"), nullable=False, index=True)
	map_id = Column(Integer, ForeignKey("goldsource_maps.id"), nullable=False, index=True)
	server_id = Column(Integer, ForeignKey("goldsource_servers.id"), nullable=False, index=True)
	time_played = Column(BigInteger, default=0, nullable=False) # ms

	user = relationship("GoldSourceUser", backref="map_times")
	map = relationship("GoldSourceMap")
	server = relationship("GoldSourceServer")
