from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Boolean, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.db.base_class import Base

class ResourceGoal(Base):
	"""Цели сбора ресурсов для серверов"""
	__tablename__ = "resource_goals"

	id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
	server_id = Column(UUID(as_uuid=True), ForeignKey("game_servers.id"), nullable=False, index=True)
	name = Column(String, nullable=False)
	resource_type = Column(String, nullable=False, index=True)
	target_amount = Column(Integer, nullable=False)
	is_active = Column(Boolean, default=True, nullable=False)
	created_at = Column(DateTime(timezone=True), server_default=func.now())
	updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

	server = relationship("GameServer", back_populates="resource_goals")

	__table_args__ = (
		Index('ix_resource_goals_server_resource', 'server_id', 'resource_type'),
	)


class ResourceProgress(Base):
	"""Текущий прогресс сбора ресурсов по серверам"""
	__tablename__ = "resource_progress"

	id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
	server_id = Column(UUID(as_uuid=True), ForeignKey("game_servers.id"), nullable=False, index=True)
	resource_type = Column(String, nullable=False, index=True)
	current_amount = Column(Integer, default=0, nullable=False)
	updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

	server = relationship("GameServer", back_populates="resource_progress")

	__table_args__ = (
		UniqueConstraint('server_id', 'resource_type', name='uq_resource_progress_server_resource'),
		Index('ix_resource_progress_server_resource', 'server_id', 'resource_type'),
	)

