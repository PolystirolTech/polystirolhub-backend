from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import List, Optional
from uuid import UUID
from datetime import datetime, timezone

from app.api import deps
from app.models.statistics import (
	MinecraftServer as MinecraftServerModel,
	MinecraftUser,
	MinecraftUserInfo,
	MinecraftSession,
	MinecraftKill,
	MinecraftPlatform,
	MinecraftNickname,
	MinecraftTPS,
)
from app.schemas.statistics import (
	MinecraftStatisticsBatch,
	BatchResponse,
	MinecraftPlayerProfile,
	MinecraftSessionResponse,
	MinecraftKillResponse,
	MinecraftServerStats,
	MinecraftTopPlayer,
)
from app.services.statistics import process_statistics_batch
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


# ========== Эндпоинты для игровых серверов (отправка данных) ==========

@router.post("/minecraft/batch", response_model=BatchResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(deps.verify_ingest_token)])
async def receive_statistics_batch(
	batch: MinecraftStatisticsBatch,
	db: AsyncSession = Depends(deps.get_db)
):
	"""
	Принимает batch статистики от игрового сервера.
	Идентификация сервера по server_uuid (UUID из game_servers).
	"""
	success, processed, errors = await process_statistics_batch(db, batch)
	
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


# ========== Эндпоинты для фронта (получение данных) ==========

@router.get("/minecraft/players/{player_uuid}", response_model=MinecraftPlayerProfile)
async def get_player_profile(
	player_uuid: str,
	server_id: Optional[UUID] = Query(None),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Получает профиль игрока по UUID. Если передан server_id, статистика фильтруется по конкретному серверу."""
	if len(player_uuid) != 36:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Invalid player UUID format"
		)
	
	# Получаем игрока
	result = await db.execute(
		select(MinecraftUser).where(MinecraftUser.uuid == player_uuid)
	)
	user = result.scalar_one_or_none()
	
	if not user:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Player not found"
		)
	
	# Получаем последний ник
	result = await db.execute(
		select(MinecraftNickname)
		.where(MinecraftNickname.uuid == player_uuid)
		.order_by(MinecraftNickname.last_used.desc())
		.limit(1)
	)
	last_nickname = result.scalar_one_or_none()
	
	# Получаем платформу
	result = await db.execute(
		select(MinecraftPlatform).where(MinecraftPlatform.uuid == player_uuid)
	)
	platform = result.scalar_one_or_none()
	
	# Вычисляем общее время игры
	playtime_query = select(func.sum(
		func.coalesce(MinecraftSession.session_end, func.extract('epoch', func.now()) * 1000) -
		MinecraftSession.session_start - func.coalesce(MinecraftSession.afk_time, 0)
	)).where(MinecraftSession.user_id == user.id)

	# Фильтруем по серверу если передан
	if server_id:
		# Нам нужен внутренний id сервера в таблице minecraft_servers
		mc_server_result = await db.execute(
			select(MinecraftServerModel.id).where(MinecraftServerModel.game_server_id == server_id)
		)
		internal_server_id = mc_server_result.scalar_one_or_none()
		if internal_server_id:
			playtime_query = playtime_query.where(MinecraftSession.server_id == internal_server_id)
		else:
			# Если сервер не найден в minecraft_servers, возвращаем 0
			total_playtime = 0
			total_kills = 0
			total_deaths = 0
			return MinecraftPlayerProfile(
				uuid=user.uuid,
				name=user.name,
				registered=user.registered,
				current_nickname=last_nickname.nickname if last_nickname else user.name,
				platform=platform.platform if platform else None,
				last_seen=None,
				total_playtime=0,
				total_kills=0,
				total_deaths=0,
				servers_played=[]
			)

	result = await db.execute(playtime_query)
	total_playtime = result.scalar_one() or 0
	
	# Получаем количество убийств и смертей
	kills_query = select(func.count(MinecraftKill.id)).where(MinecraftKill.killer_uuid == player_uuid)
	deaths_query = select(func.count(MinecraftKill.id)).where(MinecraftKill.victim_uuid == player_uuid)

	if server_id:
		# Для убийств используем server_uuid
		mc_server_result = await db.execute(
			select(MinecraftServerModel.server_uuid).where(MinecraftServerModel.game_server_id == server_id)
		)
		server_uuid = mc_server_result.scalar_one_or_none()
		if server_uuid:
			kills_query = kills_query.where(MinecraftKill.server_uuid == server_uuid)
			deaths_query = deaths_query.where(MinecraftKill.server_uuid == server_uuid)
		else:
			# Уже обработано выше, но для чистоты
			pass

	result = await db.execute(kills_query)
	total_kills = result.scalar_one() or 0
	
	result = await db.execute(deaths_query)
	total_deaths = result.scalar_one() or 0
	
	# Получаем список серверов
	result = await db.execute(
		select(MinecraftUserInfo.server_id)
		.where(MinecraftUserInfo.user_id == user.id)
		.distinct()
	)
	server_ids = [row[0] for row in result.all()]
	
	result = await db.execute(
		select(MinecraftServerModel.server_uuid)
		.where(MinecraftServerModel.id.in_(server_ids))
	)
	servers_played = [row[0] for row in result.all()]
	
	# Последний раз видели
	last_seen = None
	last_seen_query = select(func.max(MinecraftSession.session_end)).where(MinecraftSession.user_id == user.id)
	
	if server_id:
		# Используем полученный ранее internal_server_id если он есть
		mc_server_result = await db.execute(
			select(MinecraftServerModel.id).where(MinecraftServerModel.game_server_id == server_id)
		)
		internal_server_id = mc_server_result.scalar_one_or_none()
		if internal_server_id:
			last_seen_query = last_seen_query.where(MinecraftSession.server_id == internal_server_id)

	result = await db.execute(last_seen_query)
	last_seen = result.scalar_one()
	
	return MinecraftPlayerProfile(
		uuid=user.uuid,
		name=user.name,
		registered=user.registered,
		current_nickname=last_nickname.nickname if last_nickname else user.name,
		platform=platform.platform if platform else None,
		last_seen=last_seen,
		total_playtime=int(total_playtime),
		total_kills=total_kills,
		total_deaths=total_deaths,
		servers_played=servers_played
	)


@router.get("/minecraft/servers/{server_id}/stats", response_model=MinecraftServerStats)
async def get_server_stats(
	server_id: UUID,
	db: AsyncSession = Depends(deps.get_db)
):
	"""Получает статистику сервера по ID из game_servers"""
	# Получаем minecraft_server с загрузкой game_server
	result = await db.execute(
		select(MinecraftServerModel)
		.options(selectinload(MinecraftServerModel.game_server))
		.where(MinecraftServerModel.game_server_id == server_id)
	)
	mc_server = result.scalar_one_or_none()
	
	if not mc_server or not mc_server.game_server:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Server not found in statistics"
		)
	
	# Количество уникальных игроков
	result = await db.execute(
		select(func.count(func.distinct(MinecraftUserInfo.user_id)))
		.where(MinecraftUserInfo.server_id == mc_server.id)
	)
	total_players = result.scalar_one() or 0
	
	# Количество сессий
	result = await db.execute(
		select(func.count(MinecraftSession.id))
		.where(MinecraftSession.server_id == mc_server.id)
	)
	total_sessions = result.scalar_one() or 0
	
	# Средний TPS (последние записи)
	result = await db.execute(
		select(func.avg(MinecraftTPS.tps))
		.where(MinecraftTPS.server_id == mc_server.id)
	)
	average_tps = result.scalar_one()
	
	# Текущее количество игроков (последняя запись TPS)
	result = await db.execute(
		select(MinecraftTPS.players_online)
		.where(MinecraftTPS.server_id == mc_server.id)
		.order_by(MinecraftTPS.date.desc())
		.limit(1)
	)
	current_players = result.scalar_one()
	
	# Последнее обновление
	result = await db.execute(
		select(func.max(MinecraftTPS.date))
		.where(MinecraftTPS.server_id == mc_server.id)
	)
	last_update = result.scalar_one()
	
	return MinecraftServerStats(
		server_id=mc_server.id,
		server_uuid=mc_server.server_uuid,
		name=mc_server.game_server.name,
		total_players=total_players,
		total_sessions=total_sessions,
		average_tps=float(average_tps) if average_tps else None,
		current_players=current_players,
		last_update=int(last_update) if last_update else None
	)


@router.get("/minecraft/players/{player_uuid}/sessions", response_model=List[MinecraftSessionResponse])
async def get_player_sessions(
	player_uuid: str,
	server_id: Optional[UUID] = Query(None),
	limit: int = 50,
	offset: int = 0,
	db: AsyncSession = Depends(deps.get_db)
):
	"""Получает сессии игрока"""
	if len(player_uuid) != 36:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Invalid player UUID format"
		)
	
	# Получаем игрока
	result = await db.execute(
		select(MinecraftUser).where(MinecraftUser.uuid == player_uuid)
	)
	user = result.scalar_one_or_none()
	
	if not user:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Player not found"
		)
	
	# Получаем сессии
	query = select(MinecraftSession).where(MinecraftSession.user_id == user.id)
	
	if server_id:
		mc_server_result = await db.execute(
			select(MinecraftServerModel.id).where(MinecraftServerModel.game_server_id == server_id)
		)
		internal_server_id = mc_server_result.scalar_one_or_none()
		if internal_server_id:
			query = query.where(MinecraftSession.server_id == internal_server_id)
		else:
			return []

	result = await db.execute(
		query.order_by(MinecraftSession.session_start.desc())
		.limit(limit)
		.offset(offset)
	)
	sessions = result.scalars().all()
	
	return [
		MinecraftSessionResponse(
			id=session.id,
			server_id=session.server_id,
			session_start=session.session_start,
			session_end=session.session_end,
			session_date=datetime.fromtimestamp(session.session_start / 1000, tz=timezone.utc).strftime("%Y-%m-%d"),
			session_date_end=datetime.fromtimestamp(session.session_end / 1000, tz=timezone.utc).strftime("%Y-%m-%d"),
			mob_kills=session.mob_kills,
			deaths=session.deaths,
			afk_time=session.afk_time,
			playtime=(
				(session.session_end or 0) - session.session_start - (session.afk_time or 0)
				if session.session_end
				else None
			)
		)
		for session in sessions
	]


@router.get("/minecraft/servers/{server_id}/players", response_model=List[MinecraftTopPlayer])
async def get_server_top_players(
	server_id: UUID,
	offset: int = Query(0, ge=0, description="Количество пропущенных записей"),
	limit: int = Query(50, ge=1, le=100, description="Максимальное количество записей"),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Получает топ игроков сервера"""
	# Получаем minecraft_server
	result = await db.execute(
		select(MinecraftServerModel)
		.where(MinecraftServerModel.game_server_id == server_id)
	)
	mc_server = result.scalar_one_or_none()
	
	if not mc_server:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Server not found in statistics"
		)
	
	# Подзапрос для времени игры (фильтр по id сервера)
	playtime_subq = (
		select(
			MinecraftSession.user_id,
			func.sum(
				func.coalesce(MinecraftSession.session_end, func.extract('epoch', func.now()) * 1000) -
				MinecraftSession.session_start - func.coalesce(MinecraftSession.afk_time, 0)
			).label("total_playtime")
		)
		.where(MinecraftSession.server_id == mc_server.id)
		.group_by(MinecraftSession.user_id)
		.subquery()
	)

	# Подзапрос для убийств (фильтр по uuid сервера)
	kills_subq = (
		select(
			MinecraftKill.killer_uuid,
			func.count(MinecraftKill.id).label("total_kills")
		)
		.where(MinecraftKill.server_uuid == mc_server.server_uuid)
		.group_by(MinecraftKill.killer_uuid)
		.subquery()
	)

	# Подзапрос для смертей (фильтр по uuid сервера)
	deaths_subq = (
		select(
			MinecraftKill.victim_uuid,
			func.count(MinecraftKill.id).label("total_deaths")
		)
		.where(MinecraftKill.server_uuid == mc_server.server_uuid)
		.group_by(MinecraftKill.victim_uuid)
		.subquery()
	)

	# Основной запрос
	result = await db.execute(
		select(
			MinecraftUser.uuid,
			MinecraftUser.name,
			func.coalesce(playtime_subq.c.total_playtime, 0).label("playtime"),
			func.coalesce(kills_subq.c.total_kills, 0).label("kills"),
			func.coalesce(deaths_subq.c.total_deaths, 0).label("deaths")
		)
		.join(playtime_subq, MinecraftUser.id == playtime_subq.c.user_id)
		.outerjoin(kills_subq, MinecraftUser.uuid == kills_subq.c.killer_uuid)
		.outerjoin(deaths_subq, MinecraftUser.uuid == deaths_subq.c.victim_uuid)
		.order_by(func.coalesce(playtime_subq.c.total_playtime, 0).desc())
		.offset(offset)
		.limit(limit)
	)
	
	players = []
	for row in result.all():
		kills = row.kills or 0
		deaths = row.deaths or 0
		kd_ratio = kills / deaths if deaths > 0 else float(kills)
		
		players.append(MinecraftTopPlayer(
			uuid=row.uuid,
			name=row.name,
			playtime=int(row.playtime or 0),
			kills=kills,
			deaths=deaths,
			kd_ratio=round(kd_ratio, 2)
		))
	
	return players


@router.get("/minecraft/players/{player_uuid}/kills", response_model=List[MinecraftKillResponse])
async def get_player_kills(
	player_uuid: str,
	server_id: Optional[UUID] = Query(None),
	limit: int = 50,
	offset: int = 0,
	db: AsyncSession = Depends(deps.get_db)
):
	"""Получает убийства игрока (где он убийца)"""
	if len(player_uuid) != 36:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Invalid player UUID format"
		)
	
	# Получаем убийства
	query = select(MinecraftKill).where(MinecraftKill.killer_uuid == player_uuid)
	
	if server_id:
		mc_server_result = await db.execute(
			select(MinecraftServerModel.server_uuid).where(MinecraftServerModel.game_server_id == server_id)
		)
		server_uuid = mc_server_result.scalar_one_or_none()
		if server_uuid:
			query = query.where(MinecraftKill.server_uuid == server_uuid)
		else:
			return []

	result = await db.execute(
		query.order_by(MinecraftKill.date.desc())
		.limit(limit)
		.offset(offset)
	)
	kills = result.scalars().all()
	
	# Получаем имена для UUID
	all_uuids = set()
	for kill in kills:
		all_uuids.add(kill.killer_uuid)
		all_uuids.add(kill.victim_uuid)
	
	result = await db.execute(
		select(MinecraftUser.uuid, MinecraftUser.name)
		.where(MinecraftUser.uuid.in_(all_uuids))
	)
	name_map = {row.uuid: row.name for row in result.all()}
	
	return [
		MinecraftKillResponse(
			id=kill.id,
			killer_uuid=kill.killer_uuid,
			victim_uuid=kill.victim_uuid,
			killer_name=name_map.get(kill.killer_uuid),
			victim_name=name_map.get(kill.victim_uuid),
			weapon=kill.weapon,
			date=kill.date
		)
		for kill in kills
	]
