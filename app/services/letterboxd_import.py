import csv
import io
import zipfile
from datetime import date
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.media_list import MediaListEntry, MediaStatus, MediaType
from app.services import external_media_api


def _parse_date(s: str) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _read_csv(data: bytes) -> list[dict]:
    return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))


async def import_letterboxd_zip(
    db: AsyncSession, user_id: UUID, zip_content: bytes
) -> dict:
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_content))
    except zipfile.BadZipFile:
        raise ValueError("Invalid ZIP file")

    names = zf.namelist()

    # Build ratings lookup: (name, year_str) -> rating (Letterboxd uses 0.5–5.0 scale)
    ratings_map: dict[tuple, int] = {}
    if "ratings.csv" in names:
        for row in _read_csv(zf.read("ratings.csv")):
            name = row.get("Name", "").strip()
            year = row.get("Year", "").strip()
            rating_str = row.get("Rating", "").strip()
            if name and rating_str:
                try:
                    lb_rating = float(rating_str)
                    ratings_map[(name, year)] = round(lb_rating * 2)
                except ValueError:
                    pass

    # Build reviews lookup: (name, year_str) -> review text
    reviews_map: dict[tuple, str] = {}
    if "reviews.csv" in names:
        for row in _read_csv(zf.read("reviews.csv")):
            name = row.get("Name", "").strip()
            year = row.get("Year", "").strip()
            review = row.get("Review", "").strip()
            if name and review:
                reviews_map[(name, year)] = review

    entries_to_process: list[tuple[dict, MediaStatus]] = []

    if "watched.csv" in names:
        for row in _read_csv(zf.read("watched.csv")):
            entries_to_process.append((row, MediaStatus.completed))

    if "watchlist.csv" in names:
        for row in _read_csv(zf.read("watchlist.csv")):
            entries_to_process.append((row, MediaStatus.planned))

    imported = 0
    skipped = 0
    errors = []

    for row, default_status in entries_to_process:
        name = row.get("Name", "").strip()
        if not name:
            skipped += 1
            continue

        year_str = row.get("Year", "").strip()
        year = int(year_str) if year_str.isdigit() else None

        date_str = row.get("Date", "").strip()
        completed_at = _parse_date(date_str) if default_status == MediaStatus.completed else None

        rating = ratings_map.get((name, year_str))
        comment = reviews_map.get((name, year_str))

        cover_url = description = genres = source_rating = None
        media_type = MediaType.movie
        metadata = await external_media_api.get_metadata_by_title_year(name, year)
        if metadata:
            name = metadata.get("title") or name
            cover_url = metadata.get("cover_url")
            description = metadata.get("description")
            genres = metadata.get("genres")
            source_rating = metadata.get("source_rating")
            year = metadata.get("year") or year
            raw_type = metadata.get("media_type")
            if isinstance(raw_type, str):
                raw_type = MediaType(raw_type)
            media_type = raw_type or MediaType.movie

        existing = await db.execute(
            select(MediaListEntry).where(
                MediaListEntry.user_id == user_id,
                MediaListEntry.media_type == media_type,
                MediaListEntry.title == name,
            )
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue

        entry = MediaListEntry(
            user_id=user_id,
            media_type=media_type,
            title=name,
            external_id=metadata.get("external_id") if metadata else None,
            year=year,
            status=default_status,
            rating=rating,
            completed_at=completed_at,
            comment=comment,
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
            errors.append(f"{name}: {e}")
            skipped += 1

    await db.commit()
    return {"imported": imported, "skipped": skipped, "errors": errors}
