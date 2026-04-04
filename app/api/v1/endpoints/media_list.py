from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.models.media_list import MediaStatus, MediaType
from app.models.user import User
from app.schemas.media_list import (
    MediaListCreate,
    MediaListFilters,
    MediaListResponse,
    MediaListStats,
    MediaListUpdate,
    MediaSearchResult,
)
from app.services import media_list as svc
from app.services import external_media_api as ext_svc
from app.services import anime_xml as xml_svc

router = APIRouter()


def _filters_from_query(
    media_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    is_favorite: Optional[bool] = Query(None),
    q: Optional[str] = Query(None, max_length=200),
    sort_by: str = Query("created_at", pattern="^(rating|completed_at|created_at|updated_at|title)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> MediaListFilters:
    media_type_enum = None
    if media_type:
        try:
            media_type_enum = MediaType(media_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid media_type: {media_type}")

    status_enum = None
    if status:
        try:
            status_enum = MediaStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    return MediaListFilters(
        media_type=media_type_enum,
        status=status_enum,
        is_favorite=is_favorite,
        q=q,
        sort_by=sort_by,
        order=order,
        limit=limit,
        offset=offset,
    )


@router.get("/search", response_model=list[MediaSearchResult])
async def search_media(
    q: str = Query(..., min_length=1, max_length=100, description="Search query"),
    type: str = Query(..., description="Media type: anime, movie, series, game, album"),
):
    """Search external APIs for media by query and type"""
    try:
        media_type = MediaType(type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid media type: {type}")

    results = await ext_svc.search_media(q, media_type)
    return results


@router.post("", response_model=MediaListResponse, status_code=status.HTTP_201_CREATED)
async def create_entry(
    data: MediaListCreate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    try:
        return await svc.create_entry(db, current_user.id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Entry with this title and type already exists")


@router.get("", response_model=list[MediaListResponse])
async def get_my_list(
    filters: MediaListFilters = Depends(_filters_from_query),
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    return await svc.get_user_list(db, current_user.id, filters)


@router.get("/stats", response_model=MediaListStats)
async def get_stats(
    media_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Count entries by status for the current user (no pagination)"""
    media_type_enum = None
    if media_type:
        try:
            media_type_enum = MediaType(media_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid media_type: {media_type}")
    return await svc.get_stats(db, current_user.id, media_type_enum)


@router.get("/anime/export")
async def export_anime(
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Export anime list in MAL/Shikimori XML format"""
    xml_content = await xml_svc.export_anime_xml(db, current_user.id, current_user.username)
    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="animelist_{current_user.username}.xml"'},
    )


@router.post("/anime/import")
async def import_anime(
    file: UploadFile,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Import anime list from MAL/Shikimori XML file"""
    if not file.filename or not file.filename.lower().endswith(".xml"):
        raise HTTPException(status_code=400, detail="File must be an XML file")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10 MB limit
        raise HTTPException(status_code=400, detail="File too large (max 10 MB)")
    try:
        result = await xml_svc.import_anime_xml(db, current_user.id, content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@router.get("/{entry_id}", response_model=MediaListResponse)
async def get_entry(
    entry_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    entry = await svc.get_entry(db, entry_id, current_user.id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    return entry


@router.patch("/{entry_id}", response_model=MediaListResponse)
async def update_entry(
    entry_id: UUID,
    data: MediaListUpdate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    entry = await svc.get_entry(db, entry_id, current_user.id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    try:
        return await svc.update_entry(db, entry, data)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Entry with this title and type already exists")


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entry(
    entry_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    entry = await svc.get_entry(db, entry_id, current_user.id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    await svc.delete_entry(db, entry)


@router.post("/{entry_id}/favorite", response_model=MediaListResponse)
async def toggle_favorite(
    entry_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    entry = await svc.get_entry(db, entry_id, current_user.id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    return await svc.toggle_favorite(db, entry)


# --- Public endpoints ---

@router.get("/users/{username}", response_model=list[MediaListResponse])
async def get_public_list(
    username: str,
    filters: MediaListFilters = Depends(_filters_from_query),
    db: AsyncSession = Depends(deps.get_db),
):
    result = await db.execute(
        select(User).where(User.username == username)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return await svc.get_user_list(db, user.id, filters, public_only=True)
