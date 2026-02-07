from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select, desc
from sqlalchemy.orm import selectinload
from app.api import deps
from app.models.user import User, OAuthAccount, ExternalLink, UserCounter
from app.models.quest import UserQuest
from app.models.badge import UserBadge, UserBadgeProgress
from app.models.notification import Notification
from app.models.activity import Activity
from app.db.redis import delete_refresh_token, get_cache, set_cache, acquire_lock, release_lock
from app.schemas.user import LeaderboardPlayer, UserProfile, UserProfileHeader, LinkedAccountInfo, BadgePreview
from app.core.progression import award_xp, get_progression_info
from app.services.statistics import get_minecraft_player_stats
from app.services.goldsource_statistics import get_goldsource_player_stats
from uuid import UUID
import json
import asyncio
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class AwardXPRequest(BaseModel):
	xp_amount: int


@router.get("/me/progression")
async def get_progression(
	current_user: User = Depends(deps.get_current_user),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Получить текущий уровень, XP и прогресс до следующего уровня"""
	progression = get_progression_info(current_user.xp)
	return progression


@router.get("/me/balance")
async def get_balance(
	current_user: User = Depends(deps.get_current_user),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Получить текущий баланс пользователя"""
	return {"balance": current_user.balance}


@router.post("/me/award-xp")
async def award_xp_to_user(
	request: AwardXPRequest,
	current_user: User = Depends(deps.get_current_user),
	db: AsyncSession = Depends(deps.get_db),
	_ = Depends(deps.require_debug_mode)
):
	"""Начислить XP текущему пользователю (дэбаг)"""
	try:
		result = await award_xp(db, current_user.id, request.xp_amount)
		return result
	except ValueError as e:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=str(e)
		)


@router.post("/me/reset-progression")
async def reset_progression(
	current_user: User = Depends(deps.get_current_user),
	db: AsyncSession = Depends(deps.get_db),
	_ = Depends(deps.require_debug_mode)
):
	"""Сбросить XP и уровень до начальных значений (дэбаг)"""
	try:
		# Сбрасываем XP и уровень
		current_user.xp = 0
		current_user.level = 1
		await db.commit()
		await db.refresh(current_user)
		
		progression = get_progression_info(0)
		return {
			"message": "Progression reset successfully",
			"progression": progression
		}
	except Exception as e:
		await db.rollback()
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=f"Failed to reset progression: {str(e)}"
		)


@router.delete("/me")
async def delete_current_user(
	request: Request,
	response: Response,
	current_user: User = Depends(deps.get_current_user),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Delete current user account and all associated data"""
	# Delete refresh token from Redis if exists
	refresh_token_value = request.cookies.get("refresh_token")
	if refresh_token_value:
		await delete_refresh_token(refresh_token_value)
	
	# Delete all related data first (cascade doesn't work with delete().where())
	await db.execute(delete(OAuthAccount).where(OAuthAccount.user_id == current_user.id))
	await db.execute(delete(ExternalLink).where(ExternalLink.user_id == current_user.id))
	await db.execute(delete(UserQuest).where(UserQuest.user_id == current_user.id))
	await db.execute(delete(UserBadge).where(UserBadge.user_id == current_user.id))
	await db.execute(delete(UserBadgeProgress).where(UserBadgeProgress.user_id == current_user.id))
	await db.execute(delete(Notification).where(Notification.user_id == current_user.id))
	await db.execute(delete(Activity).where(Activity.user_id == current_user.id))
	await db.execute(delete(UserCounter).where(UserCounter.user_id == current_user.id))
	
	# Clear selected_badge_id before deleting user (it's a foreign key)
	current_user.selected_badge_id = None
	await db.flush()
	
	# Delete user from database
	await db.execute(delete(User).where(User.id == current_user.id))
	await db.commit()
	
	# Clear cookies
	response.delete_cookie(key="access_token")
	response.delete_cookie(key="refresh_token")
	
	return {"message": "Account deleted successfully"}


@router.get("/leaderboard", response_model=list[LeaderboardPlayer])
async def get_leaderboard(
	db: AsyncSession = Depends(deps.get_db)
):
	"""Получить топ 5 игроков по уровню. Результат кэшируется на 1 минуту."""
	cache_key = "leaderboard:top5"
	lock_key = "leaderboard:lock"
	cache_ttl = 60  # 1 минута
	
	# Проверяем кэш
	cached_data = await get_cache(cache_key)
	if cached_data:
		try:
			players_data = json.loads(cached_data)
			return [LeaderboardPlayer(**player) for player in players_data]
		except (json.JSONDecodeError, Exception) as e:
			logger.warning(f"Failed to parse cached leaderboard data: {e}")
	
	# Кэш истек или отсутствует, пытаемся получить блокировку
	lock_acquired = await acquire_lock(lock_key, timeout=5)
	
	if lock_acquired:
		try:
			# Выполняем запрос к БД
			result = await db.execute(
				select(User)
				.where(User.is_active)
				.order_by(desc(User.level), desc(User.xp))
				.limit(5)
			)
			players = result.scalars().all()
			
			# Формируем список для кэша
			players_data = [
				{
					"id": str(player.id),
					"username": player.username,
					"level": player.level,
					"xp": player.xp,
					"avatar": player.avatar,
					"selected_badge_id": str(player.selected_badge_id) if player.selected_badge_id else None
				}
				for player in players
			]
			
			# Сохраняем в кэш
			await set_cache(cache_key, json.dumps(players_data), cache_ttl)
			
			# Проверяем изменения в лидерборде
			if players:
				first_place_user = players[0]
				previous_leader_key = "leaderboard:previous_leader"
				previous_leader_data = await get_cache(previous_leader_key)
				
				if previous_leader_data:
					try:
						previous_leader = json.loads(previous_leader_data)
						previous_leader_id = previous_leader.get("id")
						
						# Если первый игрок изменился
						if previous_leader_id != str(first_place_user.id):
							try:
								from app.services.activity import create_activity
								from app.models.activity import ActivityType
								
								# Создаем событие о смене первого места
								await create_activity(
									db=db,
									activity_type=ActivityType.leaderboard_first_place,
									title=f"{first_place_user.username or 'Игрок'} занял первое место в топе",
									description=f"Уровень {first_place_user.level}, {first_place_user.xp} XP",
									user_id=first_place_user.id,
									meta_data={
										"user_id": str(first_place_user.id),
										"username": first_place_user.username,
										"level": first_place_user.level,
										"xp": first_place_user.xp,
										"previous_leader_id": previous_leader_id
									}
								)
								
								# Также создаем событие об изменении в топе
								await create_activity(
									db=db,
									activity_type=ActivityType.leaderboard_changed,
									title="Изменение в топе игроков",
									description=f"{first_place_user.username or 'Игрок'} теперь на первом месте",
									user_id=first_place_user.id,
									meta_data={
										"user_id": str(first_place_user.id),
										"username": first_place_user.username,
										"level": first_place_user.level,
										"xp": first_place_user.xp,
										"previous_leader_id": previous_leader_id
									}
								)
							except Exception as e:
								logger.error(f"Failed to create leaderboard activity: {e}", exc_info=True)
					except (json.JSONDecodeError, Exception) as e:
						logger.warning(f"Failed to parse previous leader data: {e}")
				
				# Сохраняем текущего лидера для следующей проверки
				current_leader_data = {
					"id": str(first_place_user.id),
					"username": first_place_user.username,
					"level": first_place_user.level,
					"xp": first_place_user.xp
				}
				await set_cache(previous_leader_key, json.dumps(current_leader_data), 86400)  # 24 часа
			
			# Возвращаем результат
			return [LeaderboardPlayer(**player) for player in players_data]
		except Exception as e:
			logger.error(f"Failed to fetch leaderboard from database: {e}")
			# Освобождаем блокировку при ошибке
			await release_lock(lock_key)
			# Fallback: возвращаем пустой список или делаем прямой запрос
			result = await db.execute(
				select(User)
				.where(User.is_active)
				.order_by(desc(User.level), desc(User.xp))
				.limit(5)
			)
			players = result.scalars().all()
			return [
				LeaderboardPlayer(
					id=player.id,
					username=player.username,
					level=player.level,
					xp=player.xp,
					avatar=player.avatar,
					selected_badge_id=player.selected_badge_id
				)
				for player in players
			]
		finally:
			await release_lock(lock_key)
	else:
		# Блокировка не получена, значит обновление уже идет
		# Ждем немного и проверяем кэш снова
		await asyncio.sleep(0.1)
		for _ in range(10):  # Проверяем до 10 раз
			cached_data = await get_cache(cache_key)
			if cached_data:
				try:
					players_data = json.loads(cached_data)
					return [LeaderboardPlayer(**player) for player in players_data]
				except (json.JSONDecodeError, Exception):
					pass
			await asyncio.sleep(0.1)
		
		# Если данные так и не появились, делаем прямой запрос к БД
		logger.warning("Cache not available after lock wait, falling back to direct DB query")
		result = await db.execute(
			select(User)
			.where(User.is_active)
			.order_by(desc(User.level), desc(User.xp))
			.limit(5)
		)
		players = result.scalars().all()
		return [
			LeaderboardPlayer(
				id=player.id,
				username=player.username,
				level=player.level,
				xp=player.xp,
				avatar=player.avatar,
				selected_badge_id=player.selected_badge_id
			)
			for player in players
		]

@router.get("/{user_identifier}/profile", response_model=UserProfile)
async def get_user_profile(
    user_identifier: str,
    db: AsyncSession = Depends(deps.get_db)
):
    """Get comprehensive user profile by UUID or username"""
    
    # Try to parse as UUID, otherwise treat as username
    try:
        user_uuid = UUID(user_identifier)
        query = select(User).options(selectinload(User.external_links)).where(User.id == user_uuid)
    except ValueError:
        query = select(User).options(selectinload(User.external_links)).where(User.username == user_identifier)

    # 1. Get User
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # 2. Get Progression
    progression = get_progression_info(user.xp)
    
    # 3. Get Linked Accounts
    linked_accounts = []
    minecraft_uuids = []
    steam_ids = []
    added_accounts = set()  # Set of (platform, external_id) to prevent duplicates
    
    for link in user.external_links:
        linked_accounts.append(LinkedAccountInfo(
            platform=link.platform,
            nickname=link.platform_username or "Unknown",
            external_id=link.external_id
        ))
        added_accounts.add((link.platform, link.external_id))
        
        if link.platform == "MC":
            minecraft_uuids.append(link.external_id)
        elif link.platform == "STEAM":
            steam_ids.append(link.external_id)
            
    # Also check OAuth accounts
    result = await db.execute(
        select(OAuthAccount).where(OAuthAccount.user_id == user.id)
    )
    oauth_accounts = result.scalars().all()
    
    for oauth in oauth_accounts:
        platform = oauth.provider.upper()
        external_id = oauth.provider_account_id
        
        if (platform, external_id) not in added_accounts:
            # If it's Steam, we want to fetch stats for it
            if platform == "STEAM":
                if external_id not in steam_ids:
                    steam_ids.append(external_id)
            
            linked_accounts.append(LinkedAccountInfo(
                platform=platform,
                nickname=oauth.provider_username or "Unknown",
                external_id=external_id
            ))
            added_accounts.add((platform, external_id))

    # 4. Get Badges (last 5)
    result = await db.execute(
        select(UserBadge)
        .options(selectinload(UserBadge.badge))
        .where(UserBadge.user_id == user.id)
        .order_by(UserBadge.received_at.desc())
        .limit(5)
    )
    user_badges = result.scalars().all()
    
    badge_previews = [
        BadgePreview(
            id=ub.badge.id,
            name=ub.badge.name,
            image_url=ub.badge.image_url,
            description=ub.badge.description,
            received_at=ub.received_at
        )
        for ub in user_badges
    ]
    
    # 5. Get Statistics
    minecraft_stats = []
    for uuid in minecraft_uuids:
        stats = await get_minecraft_player_stats(db, uuid)
        if stats:
            minecraft_stats.append(stats)
            
    goldsource_stats = []
    for steam_id in steam_ids:
        stats = await get_goldsource_player_stats(db, steam_id)
        if stats:
            goldsource_stats.append(stats)
            
    # Assemble Header
    header = UserProfileHeader(
        id=user.id,
        username=user.username,
        avatar=user.avatar,
        background=user.background,
        level=user.level,
        xp=user.xp,
        xp_progress=progression["xp_progress"],
        xp_for_next_level=progression["xp_for_next_level"],
        progress_percent=progression["progress_percent"],
        linked_accounts=linked_accounts
    )
    
    return UserProfile(
        header=header,
        badges=badge_previews,
        minecraft_stats=minecraft_stats,
        goldsource_stats=goldsource_stats
    )
