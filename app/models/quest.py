from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Date, Boolean, Text, UniqueConstraint, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum
from app.db.base_class import Base

class QuestType(enum.Enum):
	daily = "daily"
	achievement = "achievement"

class Quest(Base):
	__tablename__ = "quests"

	id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
	name = Column(String, nullable=False, index=True)
	description = Column(Text, nullable=True)
	quest_type = Column(SQLEnum(QuestType, name="quest_type"), nullable=False)
	condition_key = Column(String, nullable=False, index=True)
	target_value = Column(Integer, nullable=False)
	reward_xp = Column(Integer, default=0, nullable=False)
	reward_balance = Column(Integer, default=0, nullable=False)
	is_active = Column(Boolean, default=True, nullable=False, index=True)
	created_at = Column(DateTime(timezone=True), server_default=func.now())

	user_quests = relationship("UserQuest", back_populates="quest", cascade="all, delete-orphan")

class UserQuest(Base):
	__tablename__ = "user_quests"

	id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
	user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
	quest_id = Column(UUID(as_uuid=True), ForeignKey("quests.id"), nullable=False, index=True)
	progress = Column(Integer, default=0, nullable=False)
	completed_at = Column(DateTime(timezone=True), nullable=True)
	claimed_at = Column(DateTime(timezone=True), nullable=True)
	quest_date = Column(Date, nullable=True, index=True)  # Для daily квестов

	user = relationship("User", back_populates="user_quests")
	quest = relationship("Quest", back_populates="user_quests")

	__table_args__ = (
		UniqueConstraint('user_id', 'quest_id', 'quest_date', name='uq_user_quest_date'),
	)

