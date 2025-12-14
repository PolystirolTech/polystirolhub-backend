"""
Сервис для работы с прогрессом и выдачей наград за квесты.
"""
from typing import Optional
from uuid import UUID
from datetime import datetime, date, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
import random
import logging

from app.models.quest import Quest, UserQuest, QuestType
from app.models.user import OAuthAccount, ExternalLink
from app.models.statistics import MinecraftSession, MinecraftUser
from app.core.progression import award_xp
from app.core.currency import add_currency
from app.services.user_counters import get_counter

logger = logging.getLogger(__name__)


async def update_progress(
	condition_key: str,
	user_id: UUID,
	increment: int,
	db: AsyncSession,
	absolute_value: Optional[int] = None
) -> None:
	"""
	Обновляет прогресс по condition_key для всех активных квестов пользователя.
	
	Args:
		condition_key: Идентификатор условия
		user_id: UUID пользователя
		increment: Значение для увеличения прогресса (используется если absolute_value=None)
		absolute_value: Абсолютное значение для установки прогресса (если указано, используется вместо increment)
		db: Асинхронная сессия базы данных
	"""
	# Находим все активные квесты с таким condition_key
	result = await db.execute(
		select(Quest).where(
			and_(
				Quest.condition_key == condition_key,
				Quest.is_active
			)
		)
	)
	quests = result.scalars().all()
	
	if not quests:
		return
	
	today = date.today()
	
	# Обновляем прогресс для каждого квеста
	for quest in quests:
		if quest.quest_type == QuestType.daily:
			# Для daily квестов проверяем quest_date (сегодняшняя дата)
			user_quest_result = await db.execute(
				select(UserQuest).where(
					and_(
						UserQuest.user_id == user_id,
						UserQuest.quest_id == quest.id,
						UserQuest.quest_date == today
					)
				)
			)
			user_quest = user_quest_result.scalar_one_or_none()
			
			# Если нет UserQuest для сегодня - создаем его
			if not user_quest:
				user_quest = UserQuest(
					user_id=user_id,
					quest_id=quest.id,
					progress=0,
					quest_date=today
				)
				db.add(user_quest)
		else:
			# Для achievement квестов quest_date всегда NULL
			user_quest_result = await db.execute(
				select(UserQuest).where(
					and_(
						UserQuest.user_id == user_id,
						UserQuest.quest_id == quest.id,
						UserQuest.quest_date.is_(None)
					)
				)
			)
			user_quest = user_quest_result.scalar_one_or_none()
			
			# Если нет UserQuest - создаем его при первом обновлении
			if not user_quest:
				user_quest = UserQuest(
					user_id=user_id,
					quest_id=quest.id,
					progress=0,
					quest_date=None
				)
				db.add(user_quest)
		
		# Обновляем прогресс только если еще не завершено
		if user_quest.completed_at is None:
			# Для счетчиков (blocks_traveled, messages_sent и т.д.) читаем значение из UserCounters
			# Это обеспечивает синхронизацию между счетчиками и прогрессом квестов
			counter_value = await get_counter(user_id, condition_key, db)
			
			if counter_value > 0:
				# Используем значение из счетчика как источник истины
				user_quest.progress = counter_value
			elif absolute_value is not None:
				# Устанавливаем абсолютное значение (но не меньше текущего)
				user_quest.progress = max(user_quest.progress, absolute_value)
			else:
				# Увеличиваем на increment (для не-счетчиков)
				user_quest.progress += increment
			
			# Проверяем достижение цели
			if quest.target_value and user_quest.progress >= quest.target_value:
				now = datetime.now(timezone.utc)
				user_quest.completed_at = now
				user_quest.claimed_at = now  # Награда выдается автоматически
				await db.flush()
				
				# Выдаем награды (XP и валюта)
				if quest.reward_xp > 0:
					try:
						await award_xp(db, user_id, quest.reward_xp)
						logger.info(f"Awarded {quest.reward_xp} XP for quest {quest.id} (user {user_id})")
					except Exception as e:
						logger.error(f"Failed to award XP for quest {quest.id}: {e}", exc_info=True)
				
				if quest.reward_balance > 0:
					try:
						await add_currency(db, user_id, quest.reward_balance)
						logger.info(f"Awarded {quest.reward_balance} currency for quest {quest.id} (user {user_id})")
					except Exception as e:
						logger.error(f"Failed to award currency for quest {quest.id}: {e}", exc_info=True)
				
				# Создаем уведомление для achievement квестов
				if quest.quest_type == QuestType.achievement:
					try:
						from app.services.notifications import create_notification
						await create_notification(
							db=db,
							user_id=user_id,
							notification_type="achievement_unlocked",
							title="Достижение разблокировано!",
							message=quest.name,
							reward_xp=quest.reward_xp,
							reward_balance=quest.reward_balance,
							meta_data={
								"quest_id": str(quest.id),
								"quest_name": quest.name
							}
						)
					except Exception as e:
						logger.error(f"Failed to create achievement_unlocked notification for user {user_id}, quest {quest.id}: {e}", exc_info=True)
				
				# Создаем события активности
				try:
					from app.services.activity import create_activity
					from app.models.activity import ActivityType
					from app.models.user import User
					
					# Получаем пользователя для имени
					user_result = await db.execute(select(User).where(User.id == user_id))
					user = user_result.scalar_one_or_none()
					username = user.username if user else "Игрок"
					
					# Создаем событие для achievement квестов
					if quest.quest_type == QuestType.achievement:
						await create_activity(
							db=db,
							activity_type=ActivityType.achievement_unlocked,
							title=f"{username} получил достижение",
							description=f"Достижение: {quest.name}",
							user_id=user_id,
							meta_data={
								"quest_id": str(quest.id),
								"quest_name": quest.name,
								"reward_xp": quest.reward_xp,
								"reward_balance": quest.reward_balance
							}
						)
					
					# Создаем событие для всех завершенных квестов
					await create_activity(
						db=db,
						activity_type=ActivityType.quest_completed,
						title=f"{username} завершил квест",
						description=f"Квест: {quest.name}",
						user_id=user_id,
						meta_data={
							"quest_id": str(quest.id),
							"quest_name": quest.name,
							"quest_type": quest.quest_type.value,
							"reward_xp": quest.reward_xp,
							"reward_balance": quest.reward_balance
						}
					)
				except Exception as e:
					logger.error(f"Failed to create activity for quest completion for user {user_id}, quest {quest.id}: {e}", exc_info=True)
	
	await db.commit()


async def check_quest_completion(
	user_id: UUID,
	quest_id: UUID,
	db: AsyncSession
) -> bool:
	"""
	Проверяет достижение цели для конкретного квеста.
	
	Args:
		user_id: UUID пользователя
		quest_id: UUID квеста
		db: Асинхронная сессия базы данных
		
	Returns:
		True если цель достигнута, False иначе
	"""
	# Получаем квест
	quest_result = await db.execute(
		select(Quest).where(Quest.id == quest_id)
	)
	quest = quest_result.scalar_one_or_none()
	
	if not quest or not quest.target_value:
		return False
	
	# Получаем UserQuest
	if quest.quest_type == QuestType.daily:
		today = date.today()
		user_quest_result = await db.execute(
			select(UserQuest).where(
				and_(
					UserQuest.user_id == user_id,
					UserQuest.quest_id == quest_id,
					UserQuest.quest_date == today
				)
			)
		)
	else:
		user_quest_result = await db.execute(
			select(UserQuest).where(
				and_(
					UserQuest.user_id == user_id,
					UserQuest.quest_id == quest_id,
					UserQuest.quest_date.is_(None)
				)
			)
		)
	
	user_quest = user_quest_result.scalar_one_or_none()
	
	if not user_quest:
		return False
	
	return user_quest.progress >= quest.target_value


async def initialize_daily_quests_for_user(
	user_id: UUID,
	db: AsyncSession,
	target_date: Optional[date] = None
) -> None:
	"""
	Создает UserQuest записи для 3 случайно выбранных активных daily квестов для пользователя.
	
	Args:
		user_id: UUID пользователя
		db: Асинхронная сессия базы данных
		target_date: Дата для квестов (по умолчанию сегодня)
	"""
	if target_date is None:
		target_date = date.today()
	
	# Получаем все активные daily квесты
	result = await db.execute(
		select(Quest).where(
			and_(
				Quest.quest_type == QuestType.daily,
				Quest.is_active
			)
		)
	)
	all_daily_quests = result.scalars().all()
	
	if not all_daily_quests:
		logger.warning(f"No active daily quests found for user {user_id}")
		return
	
	# Проверяем, какие квесты уже есть у пользователя на эту дату
	existing_result = await db.execute(
		select(UserQuest.quest_id).where(
			and_(
				UserQuest.user_id == user_id,
				UserQuest.quest_date == target_date
			)
		)
	)
	existing_quest_ids = {row[0] for row in existing_result.all()}
	
	# Фильтруем квесты, которых еще нет
	available_quests = [q for q in all_daily_quests if q.id not in existing_quest_ids]
	
	if not available_quests:
		logger.info(f"User {user_id} already has all daily quests for {target_date}")
		return
	
	# Выбираем 3 случайных квеста (или все доступные, если их меньше 3)
	num_quests = min(3, len(available_quests))
	selected_quests = random.sample(available_quests, num_quests)
	
	# Создаем UserQuest записи
	for quest in selected_quests:
		user_quest = UserQuest(
			user_id=user_id,
			quest_id=quest.id,
			progress=0,
			quest_date=target_date
		)
		db.add(user_quest)
	
	await db.commit()
	logger.info(f"Initialized {len(selected_quests)} daily quests for user {user_id} on {target_date}")
	
	# Проверяем выполнение условий для только что созданных daily квестов
	await check_initial_quest_conditions(user_id, selected_quests, db)


async def initialize_achievement_quests_for_user(
	user_id: UUID,
	db: AsyncSession
) -> None:
	"""
	Создает UserQuest записи для всех активных achievement квестов для пользователя.
	
	Args:
		user_id: UUID пользователя
		db: Асинхронная сессия базы данных
	"""
	# Получаем все активные achievement квесты
	result = await db.execute(
		select(Quest).where(
			and_(
				Quest.quest_type == QuestType.achievement,
				Quest.is_active
			)
		)
	)
	all_achievement_quests = result.scalars().all()
	
	if not all_achievement_quests:
		logger.warning(f"No active achievement quests found for user {user_id}")
		return
	
	# Проверяем, какие achievement квесты уже есть у пользователя
	existing_result = await db.execute(
		select(UserQuest.quest_id).where(
			and_(
				UserQuest.user_id == user_id,
				UserQuest.quest_date.is_(None)
			)
		)
	)
	existing_quest_ids = {row[0] for row in existing_result.all()}
	
	# Фильтруем квесты, которых еще нет
	available_quests = [q for q in all_achievement_quests if q.id not in existing_quest_ids]
	
	if not available_quests:
		logger.info(f"User {user_id} already has all achievement quests")
		return
	
	# Создаем UserQuest записи для всех доступных achievement квестов
	for quest in available_quests:
		user_quest = UserQuest(
			user_id=user_id,
			quest_id=quest.id,
			progress=0,
			quest_date=None
		)
		db.add(user_quest)
	
	await db.commit()
	logger.info(f"Initialized {len(available_quests)} achievement quests for user {user_id}")
	
	# Проверяем выполнение условий для только что созданных квестов
	await check_initial_quest_conditions(user_id, available_quests, db)


async def check_initial_quest_conditions(
	user_id: UUID,
	quests: list[Quest],
	db: AsyncSession
) -> None:
	"""
	Проверяет текущее состояние условий для квестов и обновляет прогресс.
	
	Args:
		user_id: UUID пользователя
		quests: Список квестов для проверки
		db: Асинхронная сессия базы данных
	"""
	for quest in quests:
		try:
			if quest.condition_key == "link_all_platforms":
				# Проверяем количество привязанных OAuth провайдеров
				result = await db.execute(
					select(OAuthAccount).where(
						and_(
							OAuthAccount.user_id == user_id,
							OAuthAccount.provider.in_(["twitch", "discord", "steam"])
						)
					)
				)
				linked_providers = result.scalars().all()
				linked_count = len(linked_providers)
				
				if linked_count > 0:
					await update_progress("link_all_platforms", user_id, 0, db, absolute_value=linked_count)
					logger.info(f"Checked link_all_platforms for user {user_id}: {linked_count} platforms linked")
			
			elif quest.condition_key == "playtime_daily":
				# Проверяем время игры за сегодня
				# Сначала нужно получить Minecraft UUID пользователя через ExternalLink
				external_link_result = await db.execute(
					select(ExternalLink).where(
						and_(
							ExternalLink.user_id == user_id,
							ExternalLink.platform == "MC"
						)
					)
				)
				external_link = external_link_result.scalar_one_or_none()
				
				if external_link:
					# Получаем MinecraftUser по UUID
					mc_user_result = await db.execute(
						select(MinecraftUser).where(MinecraftUser.uuid == external_link.external_id)
					)
					mc_user = mc_user_result.scalar_one_or_none()
					
					if mc_user:
						# Вычисляем playtime за сегодня
						today = date.today()
						today_start = int(datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc).timestamp() * 1000)
						today_end = int(datetime.combine(today, datetime.max.time()).replace(tzinfo=timezone.utc).timestamp() * 1000)
						
						# Суммируем playtime за сегодня
						playtime_result = await db.execute(
							select(func.sum(
								func.coalesce(MinecraftSession.session_end, func.extract('epoch', func.now()) * 1000) -
								MinecraftSession.session_start - func.coalesce(MinecraftSession.afk_time, 0)
							)).where(
								and_(
									MinecraftSession.user_id == mc_user.id,
									MinecraftSession.session_start >= today_start,
									MinecraftSession.session_start <= today_end
								)
							)
						)
						total_playtime_ms = playtime_result.scalar_one() or 0
						total_playtime_seconds = max(0, int(total_playtime_ms // 1000))
						
						if total_playtime_seconds > 0:
							await update_progress("playtime_daily", user_id, 0, db, absolute_value=total_playtime_seconds)
							logger.info(f"Checked playtime_daily for user {user_id}: {total_playtime_seconds} seconds")
			
			# Для других условий (server_join, deaths_in_session, blocks_traveled, messages_sent)
			# проверка не нужна при инициализации, т.к. они событийные
			
		except Exception as e:
			logger.error(f"Error checking initial condition for quest {quest.id} ({quest.condition_key}): {e}", exc_info=True)

