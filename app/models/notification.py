from sqlalchemy import Column, DateTime, ForeignKey, String, Text, Integer, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.db.base_class import Base

class Notification(Base):
	__tablename__ = "notifications"

	id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
	user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
	notification_type = Column(String, nullable=False)  # "level_up", "achievement_unlocked", "badge_earned"
	title = Column(String, nullable=False)
	message = Column(Text, nullable=True)
	reward_xp = Column(Integer, default=0, nullable=False)
	reward_balance = Column(Integer, default=0, nullable=False)
	meta_data = Column(JSONB, nullable=True)
	created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

	user = relationship("User", back_populates="notifications")

	__table_args__ = (
		Index('ix_notifications_user_created', 'user_id', func.desc('created_at')),
	)
