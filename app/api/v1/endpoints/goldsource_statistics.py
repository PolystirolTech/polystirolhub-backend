from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
from typing import List
from uuid import UUID

from app.api import deps
from app.models.goldsource_statistics import (
	GoldSourceServer as GoldSourceServerModel,
	GoldSourceUser,
	GoldSourceUserInfo,
	GoldSourceSession,
    GoldSourceKill,
    GoldSourceFPS
)
from app.schemas.goldsource_statistics import (
	GoldSourceStatisticsBatch,
	BatchResponse,
	GoldSourcePlayerProfile,
    GoldSourceServerStats,
    GoldSourceTopPlayer
)
from app.services.goldsource_statistics import process_goldsource_statistics_batch
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# ========== Endpoints for game servers (ingestion) ==========

@router.post("/goldsource/batch", response_model=BatchResponse, status_code=status.HTTP_201_CREATED)
async def receive_goldsource_statistics_batch(
	batch: GoldSourceStatisticsBatch,
	db: AsyncSession = Depends(deps.get_db)
):
	"""
	Accepts statistics batch from GoldSource server.
	Identified by server_uuid.
	"""
	success, processed, errors = await process_goldsource_statistics_batch(db, batch)
	
	if success and not errors:
		return BatchResponse(
			success=True,
			message="Statistics batch processed successfully",
			processed=processed
		)
	elif success:
		return BatchResponse(
			success=True,
			message="Statistics batch processed with some errors",
			processed=processed,
			errors=errors
		)
	else:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail={
				"message": "Failed to process statistics batch",
				"errors": errors,
				"processed": processed
			}
		)

# ========== Endpoints for frontend (retrieval) ==========

@router.get("/goldsource/players/{steam_id}", response_model=GoldSourcePlayerProfile)
async def get_player_profile(
	steam_id: str,
	db: AsyncSession = Depends(deps.get_db)
):
	"""Get player profile by SteamID"""
	
	result = await db.execute(
		select(GoldSourceUser).where(GoldSourceUser.steam_id == steam_id)
	)
	user = result.scalar_one_or_none()
	
	if not user:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Player not found"
		)
		
	# Total playtime
	result = await db.execute(
		select(func.sum(
			func.coalesce(GoldSourceSession.session_end, func.extract('epoch', func.now()) * 1000) -
			GoldSourceSession.session_start
		))
		.where(GoldSourceSession.user_id == user.id)
	)
	total_playtime = result.scalar_one() or 0
	
	# Kills/Deaths/Headshots
	result = await db.execute(
		select(
			func.count(GoldSourceKill.id).filter(GoldSourceKill.killer_id == user.id).label("kills"),
			func.count(GoldSourceKill.id).filter(GoldSourceKill.victim_id == user.id).label("deaths"),
            func.count(GoldSourceKill.id).filter(and_(GoldSourceKill.killer_id == user.id, GoldSourceKill.headshot.is_(True))).label("headshots")
		)
	)
	stats = result.first()
	total_kills = stats.kills or 0
	total_deaths = stats.deaths or 0
	total_headshots = stats.headshots or 0
	
	# Servers played
	result = await db.execute(
		select(GoldSourceUserInfo.server_id)
		.where(GoldSourceUserInfo.user_id == user.id)
		.distinct()
	)
	server_ids = [row[0] for row in result.all()]
	
	result = await db.execute(
		select(GoldSourceServerModel.server_uuid)
		.where(GoldSourceServerModel.id.in_(server_ids))
	)
	servers_played = [row[0] for row in result.all()]
	
	return GoldSourcePlayerProfile(
		steam_id=user.steam_id,
		name=user.name,
		registered=int(user.registered), # Ensure int
		total_playtime=int(total_playtime),
		total_kills=total_kills,
		total_deaths=total_deaths,
        total_headshots=total_headshots,
		servers_played=servers_played
	)

@router.get("/goldsource/servers/{server_id}/stats", response_model=GoldSourceServerStats)
async def get_server_stats(
	server_id: UUID,
	db: AsyncSession = Depends(deps.get_db)
):
	"""Get server stats by GameServer ID"""
	result = await db.execute(
		select(GoldSourceServerModel)
		.options(selectinload(GoldSourceServerModel.game_server))
		.where(GoldSourceServerModel.game_server_id == server_id)
	)
	gs_server = result.scalar_one_or_none()
	
	if not gs_server:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Server not found"
		)
	
	# Total players
	result = await db.execute(
		select(func.count(func.distinct(GoldSourceUserInfo.user_id)))
		.where(GoldSourceUserInfo.server_id == gs_server.id)
	)
	total_players = result.scalar_one() or 0
	
	# Total sessions
	result = await db.execute(
		select(func.count(GoldSourceSession.id))
		.where(GoldSourceSession.server_id == gs_server.id)
	)
	total_sessions = result.scalar_one() or 0
	
	# Avg FPS
	result = await db.execute(
		select(func.avg(GoldSourceFPS.fps))
		.where(GoldSourceFPS.server_id == gs_server.id)
	)
	average_fps = result.scalar_one()
	
	# Current players (last FPS record)
	result = await db.execute(
		select(GoldSourceFPS)
		.options(selectinload(GoldSourceFPS.map))
		.where(GoldSourceFPS.server_id == gs_server.id)
		.order_by(GoldSourceFPS.date.desc())
		.limit(1)
	)
	last_fps = result.scalar_one_or_none()
	
	current_players = last_fps.players_online if last_fps else 0
	current_map = last_fps.map.map_name if last_fps and last_fps.map else None
	last_update = last_fps.date if last_fps else None
	
	return GoldSourceServerStats(
		server_id=gs_server.id,
		server_uuid=gs_server.server_uuid,
		name=gs_server.game_server.name,
		total_players=total_players,
		total_sessions=total_sessions,
		average_fps=float(average_fps) if average_fps else None,
		current_players=current_players,
		current_map=current_map,
		last_update=int(last_update) if last_update else None
	)

@router.get("/goldsource/servers/{server_id}/players", response_model=List[GoldSourceTopPlayer])
async def get_server_top_players(
	server_id: UUID,
	offset: int = Query(0, ge=0),
	limit: int = Query(50, ge=1, le=100),
	db: AsyncSession = Depends(deps.get_db)
):
    """Get top players for server"""
    result = await db.execute(
        select(GoldSourceServerModel)
        .where(GoldSourceServerModel.game_server_id == server_id)
    )
    gs_server = result.scalar_one_or_none()
    
    if not gs_server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Server not found"
        )
        
    # Playtime subquery
    playtime_subq = (
        select(
            GoldSourceSession.user_id,
            func.sum(
                func.coalesce(GoldSourceSession.session_end, func.extract('epoch', func.now()) * 1000) -
                GoldSourceSession.session_start
            ).label("total_playtime")
        )
        .where(GoldSourceSession.server_id == gs_server.id)
        .group_by(GoldSourceSession.user_id)
        .subquery()
    )

    # Kills
    kills_subq = (
        select(
            GoldSourceKill.killer_id,
            func.count(GoldSourceKill.id).label("total_kills"),
            func.count(GoldSourceKill.id).filter(GoldSourceKill.headshot.is_(True)).label("total_headshots")
        )
        .where(GoldSourceKill.server_id == gs_server.id)
        .group_by(GoldSourceKill.killer_id)
        .subquery()
    )

    # Deaths
    deaths_subq = (
        select(
            GoldSourceKill.victim_id,
            func.count(GoldSourceKill.id).label("total_deaths")
        )
        .where(GoldSourceKill.server_id == gs_server.id)
        .group_by(GoldSourceKill.victim_id)
        .subquery()
    )
    
    # Main query
    result = await db.execute(
        select(
            GoldSourceUser.steam_id,
            GoldSourceUser.name,
            func.coalesce(playtime_subq.c.total_playtime, 0).label("playtime"),
            func.coalesce(kills_subq.c.total_kills, 0).label("kills"),
            func.coalesce(deaths_subq.c.total_deaths, 0).label("deaths"),
            func.coalesce(kills_subq.c.total_headshots, 0).label("headshots")
        )
        .join(playtime_subq, GoldSourceUser.id == playtime_subq.c.user_id)
        .outerjoin(kills_subq, GoldSourceUser.id == kills_subq.c.killer_id)
        .outerjoin(deaths_subq, GoldSourceUser.id == deaths_subq.c.victim_id)
        .order_by(func.coalesce(playtime_subq.c.total_playtime, 0).desc())
        .offset(offset)
        .limit(limit)
    )
    
    players = []
    for row in result.all():
        kills = row.kills or 0
        deaths = row.deaths or 0
        headshots = row.headshots or 0
        kd_ratio = kills / deaths if deaths > 0 else float(kills)
        hs_percentage = (headshots / kills * 100) if kills > 0 else 0.0
        
        players.append(GoldSourceTopPlayer(
            steam_id=row.steam_id,
            name=row.name,
            playtime=int(row.playtime or 0),
            kills=kills,
            deaths=deaths,
            kd_ratio=round(kd_ratio, 2),
            headshot_percentage=round(hs_percentage, 1)
        ))
        
    return players
