from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, BigInteger
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.db.base_class import Base

class User(Base):
	__tablename__ = "users"

	id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
	email = Column(String, unique=True, index=True, nullable=True)
	username = Column(String, unique=True, index=True, nullable=True)
	avatar = Column(String, nullable=True)
	is_active = Column(Boolean, default=True)
	is_admin = Column(Boolean, default=False, nullable=False)
	is_super_admin = Column(Boolean, default=False, nullable=False)
	xp = Column(Integer, default=0, nullable=False)
	level = Column(Integer, default=1, nullable=False)
	balance = Column(Integer, default=0, nullable=False)
	created_at = Column(DateTime(timezone=True), server_default=func.now())

	oauth_accounts = relationship("OAuthAccount", back_populates="user", cascade="all, delete-orphan")
	external_links = relationship("ExternalLink", back_populates="user", cascade="all, delete-orphan")
	user_badges = relationship("UserBadge", back_populates="user", cascade="all, delete-orphan")
	user_quests = relationship("UserQuest", back_populates="user", cascade="all, delete-orphan")
	user_badge_progress = relationship("UserBadgeProgress", back_populates="user", cascade="all, delete-orphan")
	notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
	activities = relationship("Activity", back_populates="user", cascade="all, delete-orphan")
	user_counters = relationship("UserCounter", back_populates="user", cascade="all, delete-orphan")
	selected_badge_id = Column(UUID(as_uuid=True), ForeignKey("badges.id"), nullable=True)

class OAuthAccount(Base):
	__tablename__ = "oauth_accounts"

	id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
	user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
	provider = Column(String, nullable=False)  # twitch, discord, steam
	provider_account_id = Column(String, nullable=False)
	provider_username = Column(String, nullable=True)  # username from provider
	provider_avatar = Column(String, nullable=True)  # avatar URL from provider
	access_token = Column(String, nullable=False)
	refresh_token = Column(String, nullable=True)
	expires_at = Column(DateTime(timezone=True), nullable=True)
	created_at = Column(DateTime(timezone=True), server_default=func.now())

	user = relationship("User", back_populates="oauth_accounts")

class ExternalLink(Base):
	__tablename__ = "external_links"

	id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
	user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
	platform = Column(String, nullable=False)
	external_id = Column(String, nullable=False)
	platform_username = Column(String, nullable=True)
	created_at = Column(DateTime(timezone=True), server_default=func.now())

	user = relationship("User", back_populates="external_links")

	__table_args__ = (
		UniqueConstraint('platform', 'external_id', name='uq_platform_external_id'),
	)

class UserCounter(Base):
	"""Счетчики пользователя для ачивок (Minecraft статистика)"""
	__tablename__ = "user_counters"

	id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
	user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
	counter_key = Column(String, nullable=False, index=True)  # "blocks_traveled", "messages_sent"
	value = Column(BigInteger, default=0, nullable=False)
	updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

	user = relationship("User", back_populates="user_counters")

	__table_args__ = (
		UniqueConstraint('user_id', 'counter_key', name='uq_user_counter'),
	)
