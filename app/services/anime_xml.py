import xml.etree.ElementTree as ET
from datetime import date
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.media_list import MediaListEntry, MediaStatus, MediaType
from app.services import external_media_api

STATUS_TO_MAL = {
    MediaStatus.in_progress: "Watching",
    MediaStatus.completed: "Completed",
    MediaStatus.dropped: "Dropped",
    MediaStatus.planned: "Plan to Watch",
}

MAL_TO_STATUS = {
    "Watching": MediaStatus.in_progress,
    "Completed": MediaStatus.completed,
    "On-Hold": MediaStatus.planned,
    "Dropped": MediaStatus.dropped,
    "Plan to Watch": MediaStatus.planned,
    # Shikimori variants
    "watching": MediaStatus.in_progress,
    "completed": MediaStatus.completed,
    "on_hold": MediaStatus.planned,
    "dropped": MediaStatus.dropped,
    "planned": MediaStatus.planned,
}


def _date_str(d: Optional[date]) -> str:
    return d.strftime("%Y-%m-%d") if d else "0000-00-00"


def _parse_date(s: str) -> Optional[date]:
    if not s or s == "0000-00-00":
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


async def export_anime_xml(db: AsyncSession, user_id: UUID, username: str) -> str:
    result = await db.execute(
        select(MediaListEntry).where(
            MediaListEntry.user_id == user_id,
            MediaListEntry.media_type == MediaType.anime,
        )
    )
    entries = list(result.scalars().all())

    counts = {s: 0 for s in MediaStatus}
    for e in entries:
        if e.status:
            counts[e.status] += 1

    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append("<myanimelist>")
    lines.append("  <myinfo>")
    lines.append(f"    <user_name>{username}</user_name>")
    lines.append("    <user_export_type>1</user_export_type>")
    lines.append(f"    <user_total_anime>{len(entries)}</user_total_anime>")
    lines.append(f"    <user_total_watching>{counts[MediaStatus.in_progress]}</user_total_watching>")
    lines.append(f"    <user_total_completed>{counts[MediaStatus.completed]}</user_total_completed>")
    lines.append("    <user_total_onhold>0</user_total_onhold>")
    lines.append(f"    <user_total_dropped>{counts[MediaStatus.dropped]}</user_total_dropped>")
    lines.append(f"    <user_total_plantowatch>{counts[MediaStatus.planned]}</user_total_plantowatch>")
    lines.append("  </myinfo>")

    for entry in entries:
        mal_status = STATUS_TO_MAL.get(entry.status, "Plan to Watch")
        score = entry.rating or 0
        lines.append("  <anime>")
        lines.append(f"    <series_animedb_id>{entry.external_id or 0}</series_animedb_id>")
        lines.append(f"    <series_title><![CDATA[{entry.title}]]></series_title>")
        lines.append(f"    <my_score>{score}</my_score>")
        lines.append(f"    <my_status>{mal_status}</my_status>")
        lines.append(f"    <my_start_date>{_date_str(entry.started_at)}</my_start_date>")
        lines.append(f"    <my_finish_date>{_date_str(entry.completed_at)}</my_finish_date>")
        lines.append(f"    <my_comments><![CDATA[{entry.comment or ''}]]></my_comments>")
        lines.append("    <update_on_import>1</update_on_import>")
        lines.append("  </anime>")

    lines.append("</myanimelist>")
    return "\n".join(lines)


async def import_anime_xml(
    db: AsyncSession, user_id: UUID, xml_content: bytes
) -> dict:
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        raise ValueError(f"Invalid XML: {e}")

    # Parse all entries from XML first
    parsed = []
    for anime_el in root.findall("anime"):
        def get_text(tag: str, el=anime_el) -> str:
            child = el.find(tag)
            return (child.text or "").strip() if child is not None else ""

        title = get_text("series_title")
        if not title:
            continue

        external_id_raw = get_text("series_animedb_id")
        external_id = external_id_raw if external_id_raw and external_id_raw != "0" else None
        parsed.append({
            "title": title,
            "external_id": external_id,
            "status": MAL_TO_STATUS.get(get_text("my_status"), MediaStatus.planned),
            "rating": (lambda s: int(s) if s.isdigit() and 1 <= int(s) <= 10 else None)(get_text("my_score")),
            "started_at": _parse_date(get_text("my_start_date")),
            "completed_at": _parse_date(get_text("my_finish_date")),
            "comment": get_text("my_comments") or None,
        })

    # Batch-fetch all metadata from Shikimori (50 IDs per request)
    external_ids = [item["external_id"] for item in parsed if item.get("external_id")]
    metadata_map = await external_media_api.fetch_shikimori_batch(external_ids)

    for item in parsed:
        metadata = metadata_map.get(item.get("external_id") or "")
        if metadata:
            item["title"] = metadata.get("title") or item["title"]
            item["cover_url"] = metadata.get("cover_url")
            item["description"] = metadata.get("description")
            item["genres"] = metadata.get("genres")
            item["source_rating"] = metadata.get("source_rating")
            item["year"] = metadata.get("year")

    imported = 0
    skipped = 0
    errors = []

    for item in parsed:
        title = item["title"]

        existing = await db.execute(
            select(MediaListEntry).where(
                MediaListEntry.user_id == user_id,
                MediaListEntry.media_type == MediaType.anime,
                MediaListEntry.title == title,
            )
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue

        entry = MediaListEntry(
            user_id=user_id,
            media_type=MediaType.anime,
            title=title,
            external_id=item.get("external_id"),
            status=item["status"],
            rating=item["rating"],
            started_at=item["started_at"],
            completed_at=item["completed_at"],
            comment=item["comment"],
            cover_url=item.get("cover_url"),
            description=item.get("description"),
            genres=item.get("genres"),
            source_rating=item.get("source_rating"),
            year=item.get("year"),
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
