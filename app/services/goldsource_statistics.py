from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import selectinload
from typing import Dict, List, Optional, Tuple
import logging

from app.models.game_server import GameServer
from app.models.user import ExternalLink, OAuthAccount
from app.core.steam import steamidalt_to_64


from app.models.goldsource_statistics import (
	GoldSourceServer as GoldSourceServerModel,
	GoldSourceUser,
	GoldSourceUserInfo,
	GoldSourceSession,
    GoldSourceKill,
    GoldSourceMap,
    GoldSourceFPS
)

from app.schemas.goldsource_statistics import (
	GoldSourceStatisticsBatch,
    GoldSourceServerData,
    GoldSourceUserData
)

logger = logging.getLogger(__name__)


async def validate_server_uuid(db: AsyncSession, server_uuid: str) -> Optional[GameServer]:
	"""Validate server_uuid and return GameServer if found"""
	# Check for goldsource_server with this uuid
	result = await db.execute(
		select(GoldSourceServerModel)
		.options(selectinload(GoldSourceServerModel.game_server))
		.join(GameServer, GoldSourceServerModel.game_server_id == GameServer.id)
		.where(GoldSourceServerModel.server_uuid == server_uuid)
	)
	gs_server = result.scalar_one_or_none()
	
	if gs_server:
		return gs_server.game_server
	
	# If not registered yet, find by ID directly (assuming server_uuid from plugin matches GameServer ID initially or manually set)
    # NOTE: In HL1 plugins, we typically configure the server UUID.
	result = await db.execute(
		select(GameServer).where(GameServer.id == server_uuid)
	)
	game_server = result.scalar_one_or_none()
	
	return game_server

async def get_or_create_goldsource_map(db: AsyncSession, map_name: str) -> int:
    if not map_name:
        return None
    
    result = await db.execute(select(GoldSourceMap).where(GoldSourceMap.map_name == map_name))
    map_obj = result.scalar_one_or_none()
    
    if not map_obj:
        map_obj = GoldSourceMap(map_name=map_name)
        db.add(map_obj)
        await db.flush()
        
    return map_obj.id

async def get_or_create_goldsource_user(db: AsyncSession, user_data: GoldSourceUserData) -> GoldSourceUser:
    steam_id_64 = steamidalt_to_64(user_data.steam_id)
    result = await db.execute(select(GoldSourceUser).where(GoldSourceUser.steam_id == steam_id_64))
    user = result.scalar_one_or_none()
    
    if not user:
        user = GoldSourceUser(
            steam_id=steam_id_64,
            registered=user_data.registered,
            name=user_data.name
        )
        db.add(user)
        await db.flush()
    else:
        # Update name if changed, but NEVER overwrite with "Unknown"
        if user_data.name and user_data.name != "Unknown" and user.name != user_data.name:
            user.name = user_data.name
            
    return user

async def get_or_create_goldsource_server(db: AsyncSession, server_data: GoldSourceServerData, game_server: GameServer) -> GoldSourceServerModel:
    result = await db.execute(select(GoldSourceServerModel).where(GoldSourceServerModel.server_uuid == server_data.server_uuid))
    gs_server = result.scalar_one_or_none()
    
    if not gs_server:
        gs_server = GoldSourceServerModel(
            game_server_id=game_server.id,
            server_uuid=server_data.server_uuid,
            name=server_data.name,
            address=server_data.address,
            max_players=server_data.max_players
        )
        db.add(gs_server)
        await db.flush()
    else:
        gs_server.name = server_data.name
        if server_data.address:
            gs_server.address = server_data.address
        gs_server.max_players = server_data.max_players
        
    return gs_server

async def link_steam_to_user(db: AsyncSession, steam_id: str) -> Optional[str]:
	# Convert to SteamID64 for lookup
	steam_id_64 = steamidalt_to_64(steam_id)
	
	# 1. Check ExternalLink for STEAM platform (manual links)
	result = await db.execute(
		select(ExternalLink).where(
			and_(
				ExternalLink.platform == "STEAM",
				ExternalLink.external_id == steam_id_64
			)
		)
	)
	link = result.scalar_one_or_none()
	
	if link:
		return str(link.user_id)
		
	# 2. Check OAuthAccount for steam provider (logins)
	result = await db.execute(
		select(OAuthAccount).where(
			and_(
				OAuthAccount.provider == "steam",
				OAuthAccount.provider_account_id == steam_id_64
			)
		)
	)
	oauth = result.scalar_one_or_none()
	
	if oauth:
		return str(oauth.user_id)
	
	return None

async def process_goldsource_statistics_batch(
	db: AsyncSession,
	batch: GoldSourceStatisticsBatch
) -> Tuple[bool, Dict[str, int], List[str]]:
    
    errors = []
    processed = {
        "servers": 0,
        "users": 0,
        "sessions": 0,
        "kills": 0,
        "fps": 0,
        "counters": 0
    }
    
    try:
        game_server = await validate_server_uuid(db, batch.server_uuid)
        if not game_server:
            errors.append(f"Server with UUID {batch.server_uuid} not found")
            return False, processed, errors

        # Process servers
        if batch.servers:
            for server_data in batch.servers:
                try:
                    await get_or_create_goldsource_server(db, server_data, game_server)
                    processed["servers"] += 1
                except Exception as e:
                    errors.append(f"Error processing server: {e}")
                    logger.error(f"Error processing server: {e}")

        # Ensure we have the GoldsourceServerModel instance
        result = await db.execute(select(GoldSourceServerModel).where(GoldSourceServerModel.server_uuid == batch.server_uuid))
        gs_server = result.scalar_one_or_none()
        if not gs_server:
             # Auto-create if not in batch but present in DB as GameServer
             gs_server = GoldSourceServerModel(
                 game_server_id=game_server.id,
                 server_uuid=batch.server_uuid,
                 name=game_server.name
             )
             db.add(gs_server)
             await db.flush()

        # Process users
        user_id_map = {} # steam_id -> id
        if batch.users:
            for user_data in batch.users:
                try:
                    user = await get_or_create_goldsource_user(db, user_data)
                    user_id_map[user_data.steam_id] = user.id # Keep original steam_id as key for mapping
                    processed["users"] += 1
                    
                    # Update UserInfo
                    items = await db.execute(
                        select(GoldSourceUserInfo).where(
                            and_(
                                GoldSourceUserInfo.user_id == user.id,
                                GoldSourceUserInfo.server_id == gs_server.id
                            )
                        )
                    )
                    user_info = items.scalar_one_or_none()
                    if not user_info:
                        user_info = GoldSourceUserInfo(
                            user_id=user.id,
                            server_id=gs_server.id,
                            first_seen=user_data.registered,
                            last_seen=user_data.registered
                        )
                        db.add(user_info)
                    else:
                        if user_data.registered > user_info.last_seen:
                            user_info.last_seen = user_data.registered
                            
                except Exception as e:
                    errors.append(f"Error processing user {user_data.steam_id}: {e}")
                    logger.error(f"Error processing user {user_data.steam_id}: {e}")

        # Process sessions
        if batch.sessions:
            for session_data in batch.sessions:
                try:
                    if session_data.steam_id not in user_id_map:
                         # Implies user wasn't in users list, try to fetch or create minimal
                         user = await get_or_create_goldsource_user(db, GoldSourceUserData(
                             steam_id=session_data.steam_id,
                             name="Unknown",
                             registered=session_data.session_start
                         ))
                         user_id_map[session_data.steam_id] = user.id

                    map_id = await get_or_create_goldsource_map(db, session_data.map_name)

                    # Check for existing session
                    result = await db.execute(
                        select(GoldSourceSession).where(
                            and_(
                                GoldSourceSession.user_id == user_id_map[session_data.steam_id],
                                GoldSourceSession.server_id == gs_server.id,
                                GoldSourceSession.session_start == session_data.session_start
                            )
                        )
                    )
                    session = result.scalar_one_or_none()
                    
                    if not session:
                        session = GoldSourceSession(
                            user_id=user_id_map[session_data.steam_id],
                            server_id=gs_server.id,
                            map_id=map_id,
                            session_start=session_data.session_start,
                            session_end=session_data.session_end,
                            kills=session_data.kills,
                            deaths=session_data.deaths,
                            headshots=session_data.headshots
                        )
                        db.add(session)
                        
                        # Use existing quest logic for server_join
                        try:
                            from app.services.quest_progress import update_progress as update_quest_progress
                            real_user_id = await link_steam_to_user(db, session_data.steam_id)
                            if real_user_id:
                                await update_quest_progress("server_join", real_user_id, 1, db)
                        except Exception as e:
                            logger.error(f"Error updating quest progress for server_join: {e}")

                    else:
                        session.session_end = session_data.session_end
                        session.kills = session_data.kills
                        session.deaths = session_data.deaths
                        session.headshots = session_data.headshots
                        
                    processed["sessions"] += 1
                except Exception as e:
                    errors.append(f"Error processing session: {e}")
                    logger.error(f"Error processing session: {e}")

        # Process kills
        if batch.kills:
            for kill_data in batch.kills:
                try:
                    victim_id = user_id_map.get(kill_data.victim_steam_id)
                    if not victim_id:
                         # Lazy load
                         user = await get_or_create_goldsource_user(db, GoldSourceUserData(
                             steam_id=kill_data.victim_steam_id,
                             name="Unknown",
                             registered=kill_data.date
                         ))
                         victim_id = user.id
                         user_id_map[kill_data.victim_steam_id] = victim_id
                    
                    killer_id = None
                    if kill_data.killer_steam_id:
                        killer_id = user_id_map.get(kill_data.killer_steam_id)
                        if not killer_id:
                            # Lazy load
                            user = await get_or_create_goldsource_user(db, GoldSourceUserData(
                                steam_id=kill_data.killer_steam_id,
                                name="Unknown",
                                registered=kill_data.date
                            ))
                            killer_id = user.id
                            user_id_map[kill_data.killer_steam_id] = killer_id
                            
                    kill = GoldSourceKill(
                        killer_id=killer_id,
                        victim_id=victim_id,
                        server_id=gs_server.id,
                        weapon=kill_data.weapon,
                        headshot=kill_data.headshot,
                        date=kill_data.date
                    )
                    db.add(kill)
                    processed["kills"] += 1
                except Exception as e:
                    errors.append(f"Error processing kill: {e}")

        # Process FPS
        if batch.fps:
            for fps_data in batch.fps:
                try:
                     map_id = None
                     if fps_data.map_name:
                         map_id = await get_or_create_goldsource_map(db, fps_data.map_name)

                     stmt = insert(GoldSourceFPS).values({
                         "server_id": gs_server.id,
                         "date": fps_data.date,
                         "fps": fps_data.fps,
                         "players_online": fps_data.players_online,
                         "map_id": map_id
                     })
                     stmt = stmt.on_conflict_do_update(
                         index_elements=["server_id", "date"],
                         set_={
                             "fps": stmt.excluded.fps,
                             "players_online": stmt.excluded.players_online,
                             "map_id": stmt.excluded.map_id
                         }
                     )
                     await db.execute(stmt)
                     processed["fps"] += 1
                except Exception as e:
                     errors.append(f"Error processing fps: {e}")

        # Process Counters
        if batch.counters:
            for counter_data in batch.counters:
                try:
                     user_id = await link_steam_to_user(db, counter_data.steam_id)
                     if not user_id:
                         continue
                     
                     from app.services.user_counters import increment_counter
                     from app.services.quest_progress import update_progress as update_quest_progress
                     from app.services.badge_progress import update_progress as update_badge_progress
                     
                     for counter_key, increment_value in counter_data.counters.items():
                         if increment_value and increment_value > 0:
                             await increment_counter(user_id, counter_key, increment_value, db)
                             await update_quest_progress(counter_key, user_id, increment_value, db)
                             await update_badge_progress(counter_key, user_id, increment_value, db)

                     processed["counters"] += 1
                except Exception as e:
                    errors.append(f"Error processing counters: {e}")

        await db.commit()
        return True, processed, errors

    except Exception as e:
        await db.rollback()
        errors.append(f"Fatal error: {e}")
        logger.error(f"Fatal error processing goldsource batch: {e}", exc_info=True)
        return False, processed, errors
