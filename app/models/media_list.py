import enum
import uuid
from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, ENUM as PG_ENUM, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base_class import Base


class MediaType(enum.Enum):
    anime = "anime"
    movie = "movie"
    series = "series"
    game = "game"
    album = "album"


class MediaStatus(enum.Enum):
    planned = "planned"
    in_progress = "in_progress"
    completed = "completed"
    dropped = "dropped"


class MediaListEntry(Base):
    __tablename__ = "media_list"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    media_type = Column(PG_ENUM(MediaType, name="media_type", create_type=True), nullable=False)
    title = Column(String, nullable=False)
    cover_url = Column(String, nullable=True)
    external_id = Column(String, nullable=True)

    # Null for albums
    status = Column(PG_ENUM(MediaStatus, name="media_status", create_type=True), nullable=True)

    rating = Column(SmallInteger, nullable=True)  # 1–10
    comment = Column(Text, nullable=True)
    is_favorite = Column(Boolean, default=False, nullable=False)
    is_public = Column(Boolean, default=True, nullable=False)

    started_at = Column(Date, nullable=True)
    completed_at = Column(Date, nullable=True)  # Null for albums

    # Only for games
    play_time_hours = Column(Float, nullable=True)

    # External API metadata
    description = Column(Text, nullable=True)
    genres = Column(JSON, nullable=True)  # Array of genre strings
    source_rating = Column(Float, nullable=True)  # 0-10, from external API
    year = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="media_list")

    __table_args__ = (
        UniqueConstraint("user_id", "title", "media_type", name="uq_media_list_user_title_type"),
        Index("ix_media_list_user_type", "user_id", "media_type"),
        Index("ix_media_list_user_favorite", "user_id", "is_favorite"),
    )
