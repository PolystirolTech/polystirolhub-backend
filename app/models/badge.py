from sqlalchemy import Column, DateTime, ForeignKey, String, Text, UniqueConstraint, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum
from app.db.base_class import Base

class BadgeType(enum.Enum):
	temporary = "temporary"  # Временные (стрик, подписка, топ)
	event = "event"  # Ивентовые (выдаются за участие)
	permanent = "permanent"  # Простые постоянные

class Badge(Base):
	__tablename__ = "badges"

	id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
	name = Column(String, nullable=False, index=True)
	description = Column(Text, nullable=True)
	image_url = Column(String, nullable=False)
	badge_type = Column(SQLEnum(BadgeType, name="badge_type"), nullable=False, default=BadgeType.permanent)
	unicode_char = Column(String, nullable=True)  # Юникод символ в формате "E000" (без префикса \u)
	created_at = Column(DateTime(timezone=True), server_default=func.now())

	user_badges = relationship("UserBadge", back_populates="badge", cascade="all, delete-orphan")

class UserBadge(Base):
	__tablename__ = "user_badges"

	id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
	user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
	badge_id = Column(UUID(as_uuid=True), ForeignKey("badges.id"), nullable=False, index=True)
	received_at = Column(DateTime(timezone=True), server_default=func.now())
	expires_at = Column(DateTime(timezone=True), nullable=True)  # Только для временных бэджиков

	user = relationship("User", back_populates="user_badges")
	badge = relationship("Badge", back_populates="user_badges")

	__table_args__ = (
		UniqueConstraint('user_id', 'badge_id', name='uq_user_badge'),
	)

