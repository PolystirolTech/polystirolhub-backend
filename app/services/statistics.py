from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import selectinload
from typing import Dict, List, Optional, Tuple
import logging

from app.models.game_server import GameServer
from app.models.user import ExternalLink
from app.models.statistics import (
	MinecraftServer as MinecraftServerModel,
	MinecraftUser,
	MinecraftUserInfo,
	MinecraftSession,
	MinecraftNickname,
	MinecraftKill,
	MinecraftPing,
	MinecraftPlatform,
	MinecraftPluginVersion,
	MinecraftTPS,
	MinecraftWorld,
	MinecraftWorldTime,
	MinecraftJoinAddress,
	MinecraftVersionProtocol,
	MinecraftGeolocation,
)
from app.schemas.statistics import (
	MinecraftStatisticsBatch,
	MinecraftServerData,
	MinecraftUserData,
	MinecraftWorldData,
)

logger = logging.getLogger(__name__)


async def validate_server_uuid(db: AsyncSession, server_uuid: str) -> Optional[GameServer]:
	"""Валидирует server_uuid и возвращает GameServer если найден"""
	# Проверяем наличие minecraft_server с таким server_uuid
	result = await db.execute(
		select(MinecraftServerModel)
		.options(selectinload(MinecraftServerModel.game_server))
		.join(GameServer, MinecraftServerModel.game_server_id == GameServer.id)
		.where(MinecraftServerModel.server_uuid == server_uuid)
	)
	mc_server = result.scalar_one_or_none()
	
	if mc_server:
		return mc_server.game_server
	
	# Если minecraft_server не найден, ищем game_server по UUID
	# (на случай если сервер еще не был зарегистрирован в статистике)
	result = await db.execute(
		select(GameServer).where(GameServer.id == server_uuid)
	)
	game_server = result.scalar_one_or_none()
	
	return game_server


async def get_or_create_minecraft_user(
	db: AsyncSession,
	user_data: MinecraftUserData
) -> MinecraftUser:
	"""Получает или создает запись minecraft_user"""
	result = await db.execute(
		select(MinecraftUser).where(MinecraftUser.uuid == user_data.uuid)
	)
	user = result.scalar_one_or_none()
	
	if not user:
		user = MinecraftUser(
			uuid=user_data.uuid,
			registered=user_data.registered,
			name=user_data.name,
			times_kicked=user_data.times_kicked
		)
		db.add(user)
		await db.flush()
	
	return user


async def get_or_create_minecraft_server(
	db: AsyncSession,
	server_data: MinecraftServerData,
	game_server: GameServer
) -> MinecraftServerModel:
	"""Получает или создает запись minecraft_server"""
	result = await db.execute(
		select(MinecraftServerModel).where(
			MinecraftServerModel.server_uuid == server_data.server_uuid
		)
	)
	mc_server = result.scalar_one_or_none()
	
	if not mc_server:
		mc_server = MinecraftServerModel(
			game_server_id=game_server.id,
			server_uuid=server_data.server_uuid,
			name=server_data.name,
			web_address=server_data.web_address,
			is_installed=server_data.is_installed,
			is_proxy=server_data.is_proxy,
			max_players=server_data.max_players,
			plan_version=server_data.plan_version
		)
		db.add(mc_server)
		await db.flush()
	else:
		# Обновляем данные если нужно
		mc_server.name = server_data.name
		mc_server.web_address = server_data.web_address
		mc_server.is_installed = server_data.is_installed
		mc_server.is_proxy = server_data.is_proxy
		mc_server.max_players = server_data.max_players
		mc_server.plan_version = server_data.plan_version
	
	return mc_server


async def get_or_create_join_address(
	db: AsyncSession,
	join_address: str
) -> int:
	"""Получает или создает join_address и возвращает id"""
	if not join_address:
		return 1  # Default join_address_id
	
	result = await db.execute(
		select(MinecraftJoinAddress).where(
			MinecraftJoinAddress.join_address == join_address
		)
	)
	addr = result.scalar_one_or_none()
	
	if not addr:
		addr = MinecraftJoinAddress(join_address=join_address)
		db.add(addr)
		await db.flush()
	
	return addr.id


async def get_or_create_world(
	db: AsyncSession,
	world_data: MinecraftWorldData
) -> int:
	"""Получает или создает мир и возвращает id"""
	result = await db.execute(
		select(MinecraftWorld).where(
			and_(
				MinecraftWorld.world_name == world_data.world_name,
				MinecraftWorld.server_uuid == world_data.server_uuid
			)
		)
	)
	world = result.scalar_one_or_none()
	
	if not world:
		world = MinecraftWorld(
			world_name=world_data.world_name,
			server_uuid=world_data.server_uuid
		)
		db.add(world)
		await db.flush()
	
	return world.id


async def link_player_to_user(
	db: AsyncSession,
	player_uuid: str,
	player_name: Optional[str] = None
) -> Optional[str]:
	"""Связывает UUID игрока с User через ExternalLink. Возвращает user_id или None"""
	# Проверяем наличие связи
	result = await db.execute(
		select(ExternalLink).where(
			and_(
				ExternalLink.platform == "MC",
				ExternalLink.external_id == player_uuid
			)
		)
	)
	link = result.scalar_one_or_none()
	
	if link:
		return str(link.user_id)
	
	return None


async def process_statistics_batch(
	db: AsyncSession,
	batch: MinecraftStatisticsBatch
) -> Tuple[bool, Dict[str, int], List[str]]:
	"""
	Обрабатывает batch статистики от игрового сервера.
	
	Returns:
		Tuple[success: bool, processed: Dict[str, int], errors: List[str]]
	"""
	errors = []
	processed = {
		"servers": 0,
		"users": 0,
		"user_info": 0,
		"sessions": 0,
		"nicknames": 0,
		"kills": 0,
		"pings": 0,
		"platforms": 0,
		"plugin_versions": 0,
		"tps": 0,
		"worlds": 0,
		"world_times": 0,
		"version_protocols": 0,
		"geolocations": 0
	}
	
	try:
		# Валидируем server_uuid
		game_server = await validate_server_uuid(db, batch.server_uuid)
		if not game_server:
			errors.append(f"Server with UUID {batch.server_uuid} not found")
			return False, processed, errors
		
		# Обрабатываем servers
		if batch.servers:
			for server_data in batch.servers:
				try:
					await get_or_create_minecraft_server(db, server_data, game_server)
					processed["servers"] += 1
				except Exception as e:
					errors.append(f"Error processing server: {e}")
					logger.error(f"Error processing server {server_data.server_uuid}: {e}")
		
		# Обрабатываем users
		user_id_map = {}  # uuid -> MinecraftUser.id
		if batch.users:
			for user_data in batch.users:
				try:
					user = await get_or_create_minecraft_user(db, user_data)
					user_id_map[user_data.uuid] = user.id
					processed["users"] += 1
				except Exception as e:
					errors.append(f"Error processing user {user_data.uuid}: {e}")
					logger.error(f"Error processing user {user_data.uuid}: {e}")
		
		# Получаем minecraft_server для дальнейших операций
		result = await db.execute(
			select(MinecraftServerModel).where(
				MinecraftServerModel.server_uuid == batch.server_uuid
			)
		)
		mc_server = result.scalar_one_or_none()
		
		if not mc_server:
			# Создаем базовую запись если её нет
			mc_server = MinecraftServerModel(
				game_server_id=game_server.id,
				server_uuid=batch.server_uuid,
				name=game_server.name,
				is_installed=True,
				is_proxy=False,
				max_players=-1,
				plan_version="Unknown"
			)
			db.add(mc_server)
			await db.flush()
		
		# Обрабатываем user_info
		if batch.user_info:
			for info_data in batch.user_info:
				try:
					if info_data.uuid not in user_id_map:
						user = await get_or_create_minecraft_user(
							db,
							MinecraftUserData(
								uuid=info_data.uuid,
								registered=info_data.registered,
								name="",  # Будет обновлено из users если есть
								times_kicked=0
							)
						)
						user_id_map[info_data.uuid] = user.id
					
					# Проверяем существование user_info
					result = await db.execute(
						select(MinecraftUserInfo).where(
							and_(
								MinecraftUserInfo.user_id == user_id_map[info_data.uuid],
								MinecraftUserInfo.server_id == mc_server.id
							)
						)
					)
					user_info = result.scalar_one_or_none()
					
					if not user_info:
						user_info = MinecraftUserInfo(
							user_id=user_id_map[info_data.uuid],
							server_id=mc_server.id,
							join_address=info_data.join_address,
							registered=info_data.registered,
							opped=info_data.opped,
							banned=info_data.banned
						)
						db.add(user_info)
					else:
						user_info.join_address = info_data.join_address
						user_info.registered = info_data.registered
						user_info.opped = info_data.opped
						user_info.banned = info_data.banned
					
					processed["user_info"] += 1
				except Exception as e:
					errors.append(f"Error processing user_info for {info_data.uuid}: {e}")
					logger.error(f"Error processing user_info for {info_data.uuid}: {e}")
		
		# Обрабатываем sessions
		session_id_map = {}  # (user_id, session_start) -> session_id
		if batch.sessions:
			for session_data in batch.sessions:
				try:
					if session_data.uuid not in user_id_map:
						user = await get_or_create_minecraft_user(
							db,
							MinecraftUserData(
								uuid=session_data.uuid,
								registered=session_data.session_start,
								name="",
								times_kicked=0
							)
						)
						user_id_map[session_data.uuid] = user.id
					
					join_address_id = await get_or_create_join_address(
						db,
						session_data.join_address or ""
					)
					
					# Проверяем существование сессии
					result = await db.execute(
						select(MinecraftSession).where(
							and_(
								MinecraftSession.user_id == user_id_map[session_data.uuid],
								MinecraftSession.server_id == mc_server.id,
								MinecraftSession.session_start == session_data.session_start
							)
						)
					)
					session = result.scalar_one_or_none()
					
					if not session:
						session = MinecraftSession(
							user_id=user_id_map[session_data.uuid],
							server_id=mc_server.id,
							session_start=session_data.session_start,
							session_end=session_data.session_end,
							mob_kills=session_data.mob_kills,
							deaths=session_data.deaths,
							afk_time=session_data.afk_time,
							join_address_id=join_address_id
						)
						db.add(session)
						await db.flush()
					else:
						session.session_end = session_data.session_end
						session.mob_kills = session_data.mob_kills
						session.deaths = session_data.deaths
						session.afk_time = session_data.afk_time
					
					session_key = (user_id_map[session_data.uuid], session_data.session_start)
					session_id_map[session_key] = session.id
					processed["sessions"] += 1
				except Exception as e:
					errors.append(f"Error processing session for {session_data.uuid}: {e}")
					logger.error(f"Error processing session for {session_data.uuid}: {e}")
		
		# Обрабатываем nicknames (batch insert)
		if batch.nicknames:
			try:
				nickname_mappings = []
				for nickname_data in batch.nicknames:
					nickname_mappings.append({
						"uuid": nickname_data.uuid,
						"nickname": nickname_data.nickname,
						"server_uuid": nickname_data.server_uuid,
						"last_used": nickname_data.last_used
					})
				
				await db.execute(
					insert(MinecraftNickname)
					.values(nickname_mappings)
					.on_conflict_do_nothing()
				)
				processed["nicknames"] = len(nickname_mappings)
			except Exception as e:
				errors.append(f"Error processing nicknames: {e}")
				logger.error(f"Error processing nicknames: {e}")
		
		# Обрабатываем kills
		if batch.kills:
			for kill_data in batch.kills:
				try:
					kill = MinecraftKill(
						killer_uuid=kill_data.killer_uuid,
						victim_uuid=kill_data.victim_uuid,
						server_uuid=kill_data.server_uuid,
						weapon=kill_data.weapon,
						date=kill_data.date,
						session_id=kill_data.session_id
					)
					db.add(kill)
					processed["kills"] += 1
				except Exception as e:
					errors.append(f"Error processing kill: {e}")
					logger.error(f"Error processing kill: {e}")
		
		# Обрабатываем pings
		if batch.pings:
			for ping_data in batch.pings:
				try:
					if ping_data.uuid not in user_id_map:
						user = await get_or_create_minecraft_user(
							db,
							MinecraftUserData(
								uuid=ping_data.uuid,
								registered=ping_data.date,
								name="",
								times_kicked=0
							)
						)
						user_id_map[ping_data.uuid] = user.id
					
					ping = MinecraftPing(
						user_id=user_id_map[ping_data.uuid],
						server_id=mc_server.id,
						date=ping_data.date,
						max_ping=ping_data.max_ping,
						min_ping=ping_data.min_ping,
						avg_ping=ping_data.avg_ping
					)
					db.add(ping)
					processed["pings"] += 1
				except Exception as e:
					errors.append(f"Error processing ping for {ping_data.uuid}: {e}")
					logger.error(f"Error processing ping for {ping_data.uuid}: {e}")
		
		# Обрабатываем platforms
		if batch.platforms:
			for platform_data in batch.platforms:
				try:
					# Используем upsert
					stmt = insert(MinecraftPlatform).values({
						"uuid": platform_data.uuid,
						"platform": platform_data.platform,
						"bedrock_username": platform_data.bedrock_username,
						"java_username": platform_data.java_username,
						"linked_player": platform_data.linked_player,
						"language_code": platform_data.language_code,
						"version": platform_data.version
					})
					stmt = stmt.on_conflict_do_update(
						index_elements=["uuid"],
						set_={
							"platform": stmt.excluded.platform,
							"bedrock_username": stmt.excluded.bedrock_username,
							"java_username": stmt.excluded.java_username,
							"linked_player": stmt.excluded.linked_player,
							"language_code": stmt.excluded.language_code,
							"version": stmt.excluded.version
						}
					)
					await db.execute(stmt)
					processed["platforms"] += 1
				except Exception as e:
					errors.append(f"Error processing platform for {platform_data.uuid}: {e}")
					logger.error(f"Error processing platform for {platform_data.uuid}: {e}")
		
		# Обрабатываем plugin_versions
		if batch.plugin_versions:
			for plugin_data in batch.plugin_versions:
				try:
					plugin = MinecraftPluginVersion(
						server_id=mc_server.id,
						plugin_name=plugin_data.plugin_name,
						version=plugin_data.version,
						modified=plugin_data.modified
					)
					db.add(plugin)
					processed["plugin_versions"] += 1
				except Exception as e:
					errors.append(f"Error processing plugin_version: {e}")
					logger.error(f"Error processing plugin_version: {e}")
		
		# Обрабатываем tps
		if batch.tps:
			for tps_data in batch.tps:
				try:
					stmt = insert(MinecraftTPS).values({
						"server_id": mc_server.id,
						"date": tps_data.date,
						"tps": tps_data.tps,
						"players_online": tps_data.players_online,
						"cpu_usage": tps_data.cpu_usage,
						"ram_usage": tps_data.ram_usage,
						"entities": tps_data.entities,
						"chunks_loaded": tps_data.chunks_loaded,
						"free_disk_space": tps_data.free_disk_space
					})
					stmt = stmt.on_conflict_do_update(
						index_elements=["server_id", "date"],
						set_={
							"tps": stmt.excluded.tps,
							"players_online": stmt.excluded.players_online,
							"cpu_usage": stmt.excluded.cpu_usage,
							"ram_usage": stmt.excluded.ram_usage,
							"entities": stmt.excluded.entities,
							"chunks_loaded": stmt.excluded.chunks_loaded,
							"free_disk_space": stmt.excluded.free_disk_space
						}
					)
					await db.execute(stmt)
					processed["tps"] += 1
				except Exception as e:
					errors.append(f"Error processing tps: {e}")
					logger.error(f"Error processing tps: {e}")
		
		# Обрабатываем worlds
		world_id_map = {}  # (world_name, server_uuid) -> world_id
		if batch.worlds:
			for world_data in batch.worlds:
				try:
					world_id = await get_or_create_world(db, world_data)
					world_id_map[(world_data.world_name, world_data.server_uuid)] = world_id
					processed["worlds"] += 1
				except Exception as e:
					errors.append(f"Error processing world {world_data.world_name}: {e}")
					logger.error(f"Error processing world {world_data.world_name}: {e}")
		
		# Обрабатываем world_times
		if batch.world_times:
			for world_time_data in batch.world_times:
				try:
					if world_time_data.uuid not in user_id_map:
						user = await get_or_create_minecraft_user(
							db,
							MinecraftUserData(
								uuid=world_time_data.uuid,
								registered=0,
								name="",
								times_kicked=0
							)
						)
						user_id_map[world_time_data.uuid] = user.id
					
					world_time = MinecraftWorldTime(
						user_id=user_id_map[world_time_data.uuid],
						world_id=world_time_data.world_id,
						server_id=mc_server.id,
						session_id=world_time_data.session_id,
						survival_time=world_time_data.survival_time,
						creative_time=world_time_data.creative_time,
						adventure_time=world_time_data.adventure_time,
						spectator_time=world_time_data.spectator_time
					)
					db.add(world_time)
					processed["world_times"] += 1
				except Exception as e:
					errors.append(f"Error processing world_time for {world_time_data.uuid}: {e}")
					logger.error(f"Error processing world_time for {world_time_data.uuid}: {e}")
		
		# Обрабатываем version_protocols
		if batch.version_protocols:
			for version_data in batch.version_protocols:
				try:
					stmt = insert(MinecraftVersionProtocol).values({
						"uuid": version_data.uuid,
						"protocol_version": version_data.protocol_version
					})
					stmt = stmt.on_conflict_do_update(
						index_elements=["uuid"],
						set_={
							"protocol_version": stmt.excluded.protocol_version
						}
					)
					await db.execute(stmt)
					processed["version_protocols"] += 1
				except Exception as e:
					errors.append(f"Error processing version_protocol for {version_data.uuid}: {e}")
					logger.error(f"Error processing version_protocol for {version_data.uuid}: {e}")
		
		# Обрабатываем geolocations
		if batch.geolocations:
			for geo_data in batch.geolocations:
				try:
					if geo_data.uuid not in user_id_map:
						user = await get_or_create_minecraft_user(
							db,
							MinecraftUserData(
								uuid=geo_data.uuid,
								registered=geo_data.last_used,
								name="",
								times_kicked=0
							)
						)
						user_id_map[geo_data.uuid] = user.id
					
					# Проверяем существование геолокации
					result = await db.execute(
						select(MinecraftGeolocation).where(
							MinecraftGeolocation.user_id == user_id_map[geo_data.uuid]
						)
					)
					geo = result.scalar_one_or_none()
					
					if not geo:
						geo = MinecraftGeolocation(
							user_id=user_id_map[geo_data.uuid],
							geolocation=geo_data.geolocation,
							last_used=geo_data.last_used
						)
						db.add(geo)
					else:
						geo.geolocation = geo_data.geolocation
						geo.last_used = geo_data.last_used
					
					processed["geolocations"] += 1
				except Exception as e:
					errors.append(f"Error processing geolocation for {geo_data.uuid}: {e}")
					logger.error(f"Error processing geolocation for {geo_data.uuid}: {e}")
		
		# Коммитим все изменения
		await db.commit()
		
		return True, processed, errors
		
	except Exception as e:
		await db.rollback()
		errors.append(f"Fatal error processing batch: {e}")
		logger.error(f"Fatal error processing statistics batch: {e}", exc_info=True)
		return False, processed, errors

