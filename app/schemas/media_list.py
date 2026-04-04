from datetime import date, datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator

from app.models.media_list import MediaStatus, MediaType


class MediaListCreate(BaseModel):
    media_type: MediaType
    title: str = Field(..., min_length=1, max_length=500)
    cover_url: Optional[str] = None
    external_id: Optional[str] = None
    status: Optional[MediaStatus] = None
    rating: Optional[int] = Field(None, ge=1, le=10)
    comment: Optional[str] = None
    is_favorite: bool = False
    is_public: bool = True
    started_at: Optional[date] = None
    completed_at: Optional[date] = None
    play_time_hours: Optional[float] = Field(None, ge=0)
    description: Optional[str] = None
    genres: Optional[list[str]] = None
    source_rating: Optional[float] = None
    year: Optional[int] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v, info):
        media_type = info.data.get("media_type")
        if media_type == MediaType.album and v is not None:
            raise ValueError("Albums cannot have a status")
        return v

    @field_validator("play_time_hours")
    @classmethod
    def validate_play_time(cls, v, info):
        media_type = info.data.get("media_type")
        if v is not None and media_type != MediaType.game:
            raise ValueError("play_time_hours is only applicable to games")
        return v

    @field_validator("completed_at")
    @classmethod
    def validate_completed_at(cls, v, info):
        media_type = info.data.get("media_type")
        if media_type == MediaType.album and v is not None:
            raise ValueError("Albums cannot have a completed_at date")
        return v


class MediaListUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    cover_url: Optional[str] = None
    external_id: Optional[str] = None
    status: Optional[MediaStatus] = None
    rating: Optional[int] = Field(None, ge=1, le=10)
    comment: Optional[str] = None
    is_favorite: Optional[bool] = None
    is_public: Optional[bool] = None
    started_at: Optional[date] = None
    completed_at: Optional[date] = None
    play_time_hours: Optional[float] = Field(None, ge=0)
    description: Optional[str] = None
    genres: Optional[list[str]] = None
    source_rating: Optional[float] = None
    year: Optional[int] = None


class MediaListResponse(BaseModel):
    id: UUID
    user_id: UUID
    media_type: MediaType
    title: str
    cover_url: Optional[str]
    external_id: Optional[str]
    status: Optional[MediaStatus]
    rating: Optional[int]
    comment: Optional[str]
    is_favorite: bool
    is_public: bool
    started_at: Optional[date]
    completed_at: Optional[date]
    play_time_hours: Optional[float]
    description: Optional[str]
    genres: Optional[list[str]]
    source_rating: Optional[float]
    year: Optional[int]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MediaSearchResult(BaseModel):
    title: str
    cover_url: Optional[str]
    external_id: Optional[str]
    description: Optional[str]
    genres: Optional[list[str]]
    source_rating: Optional[float]
    year: Optional[int]


class MediaListFilters(BaseModel):
    media_type: Optional[MediaType] = None
    status: Optional[MediaStatus] = None
    is_favorite: Optional[bool] = None
    sort_by: str = Field("created_at", pattern="^(rating|completed_at|created_at|updated_at|title)$")
    order: str = Field("desc", pattern="^(asc|desc)$")
    limit: int = Field(50, ge=1, le=200)
    offset: int = Field(0, ge=0)
