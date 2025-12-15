from sqlalchemy import Column, DateTime, ForeignKey, String, Text, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM as PG_ENUM
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum
from app.db.base_class import Base

class ActivityType(enum.Enum):
	badge_earned = "badge_earned"
	achievement_unlocked = "achievement_unlocked"
	quest_completed = "quest_completed"
	level_up = "level_up"
	leaderboard_first_place = "leaderboard_first_place"
	leaderboard_changed = "leaderboard_changed"
	daily_quests_refreshed = "daily_quests_refreshed"
	server_status_changed = "server_status_changed"
	new_user = "new_user"

class Activity(Base):
	__tablename__ = "activities"

	id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
	activity_type = Column(PG_ENUM(ActivityType, name="activity_type", create_type=False), nullable=False, index=True)
	user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
	server_id = Column(UUID(as_uuid=True), ForeignKey("game_servers.id"), nullable=True, index=True)
	title = Column(String, nullable=False)
	description = Column(Text, nullable=True)
	meta_data = Column(JSONB, nullable=True)
	created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

	user = relationship("User", back_populates="activities")
	server = relationship("GameServer", back_populates="activities")

	__table_args__ = (
		Index('ix_activities_created_at', func.desc('created_at')),
		Index('ix_activities_type_created', 'activity_type', func.desc('created_at')),
	)
