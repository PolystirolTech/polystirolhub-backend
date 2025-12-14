from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum
from app.db.base_class import Base

class ServerStatus(enum.Enum):
	active = "active"  # Работает
	disabled = "disabled"  # Выключен
	maintenance = "maintenance"  # Обслуживание

class GameType(Base):
	__tablename__ = "game_types"

	id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
	name = Column(String, unique=True, index=True, nullable=False)
	created_at = Column(DateTime(timezone=True), server_default=func.now())

	game_servers = relationship("GameServer", back_populates="game_type", cascade="all, delete-orphan")

class GameServer(Base):
	__tablename__ = "game_servers"

	id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
	game_type_id = Column(UUID(as_uuid=True), ForeignKey("game_types.id"), nullable=False, index=True)
	name = Column(String, nullable=False, index=True)
	banner_url = Column(String, nullable=True)
	description = Column(Text, nullable=True)
	mods = Column(ARRAY(String), nullable=False, default=[])
	ip = Column(String, nullable=False)
	port = Column(Integer, nullable=True)
	resource_pack_url = Column(String, nullable=True)  # Публичный URL ресурс-пака с баджами
	resource_pack_hash = Column(String, nullable=True)  # SHA1 хэш ресурс-пака
	status = Column(SQLEnum(ServerStatus, name="server_status"), nullable=False, default=ServerStatus.active, index=True)
	created_at = Column(DateTime(timezone=True), server_default=func.now())
	updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

	game_type = relationship("GameType", back_populates="game_servers")
