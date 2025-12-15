from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select, desc
from app.api import deps
from app.models.user import User, OAuthAccount
from app.db.redis import delete_refresh_token, get_cache, set_cache, acquire_lock, release_lock
from app.schemas.user import LeaderboardPlayer
from app.core.progression import award_xp, get_progression_info
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
	
	# Delete all OAuth accounts first (cascade doesn't work with delete().where())
	await db.execute(delete(OAuthAccount).where(OAuthAccount.user_id == current_user.id))
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
