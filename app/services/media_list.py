import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import asc, desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.media_list import MediaListEntry, MediaStatus, MediaType
from app.schemas.media_list import MediaListCreate, MediaListCustomCreate, MediaListFilters, MediaListStats, MediaListUpdate

logger = logging.getLogger(__name__)


async def create_entry(db: AsyncSession, user_id: UUID, data: MediaListCreate) -> MediaListEntry:
    """Create media list entry from search result (external_id required)"""
    from app.services import external_media_api

    # Get metadata from cache using external_id
    metadata = await external_media_api.get_metadata_by_external_id(
        data.external_id, data.media_type
    )

    if not metadata:
        raise ValueError(f"Media with external_id {data.external_id} not found. Use search first.")

    # Build entry with metadata from API
    entry_data = data.model_dump(exclude_unset=True)
    entry_data['title'] = metadata.get('title')
    entry_data['description'] = metadata.get('description')
    entry_data['genres'] = metadata.get('genres')
    entry_data['source_rating'] = metadata.get('source_rating')
    entry_data['year'] = metadata.get('year')
    entry_data['cover_url'] = metadata.get('cover_url')

    entry = MediaListEntry(user_id=user_id, **entry_data)
    db.add(entry)
    try:
        await db.commit()
        await db.refresh(entry)
        return entry
    except IntegrityError:
        await db.rollback()
        raise


async def create_custom_entry(
    db: AsyncSession, user_id: UUID, data: MediaListCustomCreate
) -> MediaListEntry:
    entry = MediaListEntry(user_id=user_id, is_custom=True, **data.model_dump())
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
    updates = data.model_dump(exclude_unset=True)
    if not entry.is_custom:
        updates.pop("title", None)
        updates.pop("cover_url", None)
    for field, value in updates.items():
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
    if filters.q:
        query = query.where(MediaListEntry.title.ilike(f"%{filters.q}%"))

    sort_col = _SORT_COLS.get(filters.sort_by, MediaListEntry.created_at)
    query = query.order_by(_ORDER[filters.order](sort_col).nulls_last())
    query = query.limit(filters.limit).offset(filters.offset)

    result = await db.execute(query)
    return list(result.scalars().all())


async def enrich_metadata(
    db: AsyncSession,
    media_type: Optional[MediaType] = None,
) -> dict:
    """Fetch and fill missing metadata for ALL entries that have external_id but no cover/description"""
    from app.services import external_media_api

    query = select(MediaListEntry).where(
        MediaListEntry.external_id.isnot(None),
        MediaListEntry.cover_url.is_(None),
    )
    if media_type:
        query = query.where(MediaListEntry.media_type == media_type)

    result = await db.execute(query)
    entries = list(result.scalars().all())

    if not entries:
        return {"updated": 0, "skipped": 0}

    updated = 0
    skipped = 0

    # Batch fetch for anime via Shikimori
    anime_entries = [e for e in entries if e.media_type == MediaType.anime]
    other_entries = [e for e in entries if e.media_type != MediaType.anime]

    if anime_entries:
        ids = [e.external_id for e in anime_entries]
        metadata_map = await external_media_api.fetch_shikimori_batch(ids)
        for entry in anime_entries:
            metadata = metadata_map.get(entry.external_id)
            if metadata:
                entry.cover_url = metadata.get("cover_url") or entry.cover_url
                entry.description = metadata.get("description") or entry.description
                entry.genres = metadata.get("genres") or entry.genres
                entry.source_rating = metadata.get("source_rating") or entry.source_rating
                entry.year = metadata.get("year") or entry.year
                updated += 1
            else:
                skipped += 1

    for entry in other_entries:
        metadata = None
        if entry.media_type in (MediaType.movie, MediaType.series):
            # IMDb ID (tt...) or TMDB ID
            if entry.external_id and entry.external_id.startswith("tt"):
                metadata = await external_media_api.get_metadata_by_imdb_id(
                    entry.external_id, entry.media_type
                )
            elif entry.title and entry.year:
                metadata = await external_media_api.get_metadata_by_title_year(
                    entry.title, entry.year
                )
        elif entry.media_type == MediaType.anime:
            metadata = await external_media_api.get_metadata_by_external_id(
                entry.external_id, MediaType.anime
            )

        if metadata:
            entry.cover_url = metadata.get("cover_url") or entry.cover_url
            entry.description = metadata.get("description") or entry.description
            entry.genres = metadata.get("genres") or entry.genres
            entry.source_rating = metadata.get("source_rating") or entry.source_rating
            entry.year = metadata.get("year") or entry.year
            updated += 1
        else:
            skipped += 1

    await db.commit()
    return {"updated": updated, "skipped": skipped}


async def get_stats(
    db: AsyncSession,
    user_id: UUID,
    media_type: Optional[MediaType] = None,
    public_only: bool = False,
) -> MediaListStats:
    query = (
        select(MediaListEntry.status, func.count().label("cnt"))
        .where(MediaListEntry.user_id == user_id)
        .group_by(MediaListEntry.status)
    )
    if media_type is not None:
        query = query.where(MediaListEntry.media_type == media_type)
    if public_only:
        query = query.where(MediaListEntry.is_public)

    result = await db.execute(query)
    rows = result.all()

    by_status = {s.value: 0 for s in MediaStatus}
    total = 0
    for status, cnt in rows:
        total += cnt
        if status is not None:
            by_status[status.value] = cnt

    return MediaListStats(total=total, by_status=by_status)
