import csv
import io
from datetime import date
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.media_list import MediaListEntry, MediaStatus, MediaType
from app.services import external_media_api

TITLE_TYPE_MAP = {
    # camelCase (old IMDb export format)
    "movie": MediaType.movie,
    "short": MediaType.movie,
    "tvmovie": MediaType.movie,
    "video": MediaType.movie,
    "tvseries": MediaType.series,
    "tvminiseries": MediaType.series,
    "tvshort": MediaType.series,
    "tvspecial": MediaType.series,
    # spaced (newer IMDb export format)
    "tv series": MediaType.series,
    "tv mini series": MediaType.series,
    "tv mini-series": MediaType.series,
    "tv movie": MediaType.movie,
    "tv short": MediaType.series,
    "tv special": MediaType.series,
    "tv episode": MediaType.series,
}


def _parse_date(s: str) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _read_csv(data: bytes) -> list[dict]:
    return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))


async def import_imdb_ratings(
    db: AsyncSession, user_id: UUID, csv_content: bytes
) -> dict:
    return await _import_rows(
        db, user_id, _read_csv(csv_content), default_status=MediaStatus.completed
    )


async def import_imdb_watchlist(
    db: AsyncSession, user_id: UUID, csv_content: bytes
) -> dict:
    return await _import_rows(
        db, user_id, _read_csv(csv_content), default_status=MediaStatus.planned
    )


async def _import_rows(
    db: AsyncSession,
    user_id: UUID,
    rows: list[dict],
    default_status: MediaStatus,
) -> dict:
    imported = 0
    skipped = 0
    errors = []

    for row in rows:
        imdb_id = row.get("Const", "").strip()
        title = row.get("Title", "").strip()
        if not title:
            skipped += 1
            continue

        title_type = row.get("Title Type", "").strip().lower()
        media_type = TITLE_TYPE_MAP.get(title_type, MediaType.movie)

        year_str = row.get("Year", "").strip()
        year = int(year_str) if year_str.isdigit() else None

        rating_str = row.get("Your Rating", "").strip()
        rating = int(rating_str) if rating_str.isdigit() and 1 <= int(rating_str) <= 10 else None

        date_str = row.get("Date Rated", "").strip()
        completed_at = _parse_date(date_str) if default_status == MediaStatus.completed else None

        cover_url = description = genres = source_rating = None

        if imdb_id:
            metadata = await external_media_api.get_metadata_by_imdb_id(imdb_id, media_type)
            if metadata:
                title = metadata.get("title") or title
                cover_url = metadata.get("cover_url")
                description = metadata.get("description")
                genres = metadata.get("genres")
                source_rating = metadata.get("source_rating")
                year = metadata.get("year") or year

        existing = await db.execute(
            select(MediaListEntry).where(
                MediaListEntry.user_id == user_id,
                MediaListEntry.media_type == media_type,
                MediaListEntry.title == title,
            )
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue

        entry = MediaListEntry(
            user_id=user_id,
            media_type=media_type,
            title=title,
            external_id=imdb_id or None,
            year=year,
            status=default_status,
            rating=rating,
            completed_at=completed_at,
            cover_url=cover_url,
            description=description,
            genres=genres,
            source_rating=source_rating,
            is_public=True,
        )
        try:
            async with db.begin_nested():
                db.add(entry)
                await db.flush()
            imported += 1
        except Exception as e:
            errors.append(f"{title}: {e}")
            skipped += 1

    await db.commit()
    return {"imported": imported, "skipped": skipped, "errors": errors}
