import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import asc, desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.media_list import MediaListEntry
from app.schemas.media_list import MediaListCreate, MediaListFilters, MediaListUpdate

logger = logging.getLogger(__name__)


async def create_entry(db: AsyncSession, user_id: UUID, data: MediaListCreate) -> MediaListEntry:
    entry = MediaListEntry(user_id=user_id, **data.model_dump())
    db.add(entry)
    try:
        await db.commit()
        await db.refresh(entry)
        return entry
    except IntegrityError:
        await db.rollback()
        raise


async def get_entry(db: AsyncSession, entry_id: UUID, user_id: UUID) -> Optional[MediaListEntry]:
    result = await db.execute(
        select(MediaListEntry).where(
            MediaListEntry.id == entry_id,
            MediaListEntry.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def update_entry(
    db: AsyncSession, entry: MediaListEntry, data: MediaListUpdate
) -> MediaListEntry:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)
    try:
        await db.commit()
        await db.refresh(entry)
        return entry
    except IntegrityError:
        await db.rollback()
        raise


async def delete_entry(db: AsyncSession, entry: MediaListEntry) -> None:
    await db.delete(entry)
    await db.commit()


async def toggle_favorite(db: AsyncSession, entry: MediaListEntry) -> MediaListEntry:
    entry.is_favorite = not entry.is_favorite
    await db.commit()
    await db.refresh(entry)
    return entry


async def get_user_list(
    db: AsyncSession,
    user_id: UUID,
    filters: MediaListFilters,
    public_only: bool = False,
) -> list[MediaListEntry]:
    _ORDER = {"asc": asc, "desc": desc}
    _SORT_COLS = {
        "rating": MediaListEntry.rating,
        "completed_at": MediaListEntry.completed_at,
        "created_at": MediaListEntry.created_at,
        "updated_at": MediaListEntry.updated_at,
        "title": MediaListEntry.title,
    }

    query = select(MediaListEntry).where(MediaListEntry.user_id == user_id)

    if public_only:
        query = query.where(MediaListEntry.is_public)
    if filters.media_type is not None:
        query = query.where(MediaListEntry.media_type == filters.media_type)
    if filters.status is not None:
        query = query.where(MediaListEntry.status == filters.status)
    if filters.is_favorite is not None:
        query = query.where(MediaListEntry.is_favorite == filters.is_favorite)

    sort_col = _SORT_COLS.get(filters.sort_by, MediaListEntry.created_at)
    query = query.order_by(_ORDER[filters.order](sort_col))
    query = query.limit(filters.limit).offset(filters.offset)

    result = await db.execute(query)
    return list(result.scalars().all())
