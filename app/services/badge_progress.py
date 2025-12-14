"""
Сервис для работы с прогрессом и выдачей бейджей.
"""
from typing import Optional
from uuid import UUID
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, delete
import logging

from app.models.badge import Badge, UserBadge, UserBadgeProgress
from app.models.user import ExternalLink
from app.core.progression import award_xp
from app.core.currency import add_currency

logger = logging.getLogger(__name__)


async def get_user_id_from_minecraft_uuid(
	minecraft_uuid: str,
	db: AsyncSession
) -> Optional[UUID]:
	"""
	Получает User.id из Minecraft UUID через ExternalLink.
	
	Args:
		minecraft_uuid: UUID игрока Minecraft
		db: Асинхронная сессия базы данных
		
	Returns:
		UUID пользователя или None, если связь не найдена
	"""
	result = await db.execute(
		select(ExternalLink).where(
			and_(
				ExternalLink.platform == "MC",
				ExternalLink.external_id == minecraft_uuid
			)
		)
	)
	link = result.scalar_one_or_none()
	
	if link:
		return link.user_id
	
	return None


async def update_progress(
	condition_key: str,
	user_id: UUID,
	increment: int,
	db: AsyncSession
) -> None:
	"""
	Обновляет прогресс по condition_key для всех активных бейджей пользователя.
	
	Args:
		condition_key: Идентификатор условия
		user_id: UUID пользователя
		increment: Значение для увеличения прогресса
		db: Асинхронная сессия базы данных
	"""
	if increment == 0:
		return
	
	# Находим все бейджи с таким condition_key
	result = await db.execute(
		select(Badge).where(Badge.condition_key == condition_key)
	)
	badges = result.scalars().all()
	
	if not badges:
		return
	
	# Обновляем прогресс для каждого бейджа
	for badge in badges:
		# Получаем или создаем UserBadgeProgress
		progress_result = await db.execute(
			select(UserBadgeProgress).where(
				and_(
					UserBadgeProgress.user_id == user_id,
					UserBadgeProgress.badge_id == badge.id
				)
			)
		)
		progress = progress_result.scalar_one_or_none()
		
		if not progress:
			progress = UserBadgeProgress(
				user_id=user_id,
				badge_id=badge.id,
				progress=0
			)
			db.add(progress)
		
		# Обновляем прогресс только если еще не завершено
		if progress.completed_at is None:
			progress.progress += increment
			
			# Проверяем достижение цели
			if badge.target_value and progress.progress >= badge.target_value:
				progress.completed_at = datetime.now(timezone.utc)
				await db.flush()
				
				# Проверяем, нет ли уже такого бейджа
				existing_badge_result = await db.execute(
					select(UserBadge).where(
						and_(
							UserBadge.user_id == user_id,
							UserBadge.badge_id == badge.id
						)
					)
				)
				existing_badge = existing_badge_result.scalar_one_or_none()
				
				# Выдаем бейдж только если его еще нет
				if not existing_badge:
					await award_badge(user_id, badge.id, None, db, is_first_time=True)
	
	await db.commit()


async def check_badge_completion(
	user_id: UUID,
	badge_id: UUID,
	db: AsyncSession
) -> bool:
	"""
	Проверяет достижение цели для конкретного бейджа.
	
	Args:
		user_id: UUID пользователя
		badge_id: UUID бейджа
		db: Асинхронная сессия базы данных
		
	Returns:
		True если цель достигнута, False иначе
	"""
	# Получаем бейдж
	badge_result = await db.execute(
		select(Badge).where(Badge.id == badge_id)
	)
	badge = badge_result.scalar_one_or_none()
	
	if not badge or not badge.target_value:
		return False
	
	# Получаем прогресс
	progress_result = await db.execute(
		select(UserBadgeProgress).where(
			and_(
				UserBadgeProgress.user_id == user_id,
				UserBadgeProgress.badge_id == badge_id
			)
		)
	)
	progress = progress_result.scalar_one_or_none()
	
	if not progress:
		return False
	
	return progress.progress >= badge.target_value


async def award_badge(
	user_id: UUID,
	badge_id: UUID,
	expires_at: Optional[datetime],
	db: AsyncSession,
	is_first_time: bool = True
) -> Optional[UserBadge]:
	"""
	Выдает бейдж пользователю с наградами.
	
	Args:
		user_id: UUID пользователя
		badge_id: UUID бейджа
		expires_at: Дата истечения (для temporary бейджей)
		db: Асинхронная сессия базы данных
		is_first_time: Выдавать ли награды (True при первом получении)
		
	Returns:
		UserBadge или None если бейдж уже есть
	"""
	# Проверяем, нет ли уже такого бейджа
	now = datetime.now(timezone.utc)
	existing_result = await db.execute(
		select(UserBadge).where(
			and_(
				UserBadge.user_id == user_id,
				UserBadge.badge_id == badge_id
			)
		)
	)
	existing = existing_result.scalar_one_or_none()
	
	if existing:
		# Если бейдж уже есть и не истек - возвращаем его
		if existing.expires_at is None or existing.expires_at > now:
			return existing
		# Если истек - удаляем его, чтобы выдать новый
		await db.execute(
			delete(UserBadge).where(UserBadge.id == existing.id)
		)
		await db.commit()
	
	# Получаем бейдж для наград
	badge_result = await db.execute(
		select(Badge).where(Badge.id == badge_id)
	)
	badge = badge_result.scalar_one_or_none()
	
	if not badge:
		raise ValueError(f"Badge with id {badge_id} not found")
	
	# Выдаем награды при первом получении
	if is_first_time:
		if badge.reward_xp > 0:
			try:
				await award_xp(db, user_id, badge.reward_xp)
			except Exception as e:
				logger.error(f"Failed to award XP for badge {badge_id}: {e}")
		
		if badge.reward_balance > 0:
			try:
				await add_currency(db, user_id, badge.reward_balance)
			except Exception as e:
				logger.error(f"Failed to award currency for badge {badge_id}: {e}")
	
	# Создаем UserBadge
	user_badge = UserBadge(
		user_id=user_id,
		badge_id=badge_id,
		expires_at=expires_at
	)
	db.add(user_badge)
	await db.commit()
	await db.refresh(user_badge)
	
	# Создаем уведомление при первом получении баджа
	if is_first_time:
		try:
			from app.services.notifications import create_notification
			await create_notification(
				db=db,
				user_id=user_id,
				notification_type="badge_earned",
				title="Новый бадж!",
				message=badge.name,
				reward_xp=badge.reward_xp,
				reward_balance=badge.reward_balance,
				meta_data={
					"badge_id": str(badge.id),
					"badge_name": badge.name
				}
			)
		except Exception as e:
			logger.error(f"Failed to create badge_earned notification for user {user_id}, badge {badge_id}: {e}", exc_info=True)
		
		# Создаем событие активности
		try:
			from app.services.activity import create_activity
			from app.models.activity import ActivityType
			from app.models.user import User
			
			# Получаем пользователя для имени
			user_result = await db.execute(select(User).where(User.id == user_id))
			user = user_result.scalar_one_or_none()
			username = user.username if user else "Игрок"
			
			await create_activity(
				db=db,
				activity_type=ActivityType.badge_earned,
				title=f"{username} получил бейдж",
				description=f"Бейдж: {badge.name}",
				user_id=user_id,
				meta_data={
					"badge_id": str(badge.id),
					"badge_name": badge.name,
					"badge_type": badge.badge_type.value if badge.badge_type else None
				}
			)
		except Exception as e:
			logger.error(f"Failed to create badge_earned activity for user {user_id}, badge {badge_id}: {e}", exc_info=True)
	
	return user_badge


async def extend_or_award_badge(
	user_id: UUID,
	badge_id: UUID,
	db: AsyncSession
) -> UserBadge:
	"""
	Продлевает существующий бейдж или выдает новый.
	Для temporary бейджей: expires_at = now() + 1 час
	Для permanent бейджей: expires_at = None
	Награды выдаются только при первом получении.
	
	Args:
		user_id: UUID пользователя
		badge_id: UUID бейджа
		db: Асинхронная сессия базы данных
		
	Returns:
		UserBadge
	"""
	# Получаем бейдж для определения типа
	badge_result = await db.execute(
		select(Badge).where(Badge.id == badge_id)
	)
	badge = badge_result.scalar_one_or_none()
	
	if not badge:
		raise ValueError(f"Badge with id {badge_id} not found")
	
	# Определяем expires_at
	now = datetime.now(timezone.utc)
	if badge.badge_type.value == "temporary":
		expires_at = now + timedelta(hours=1)
	else:
		expires_at = None
	
	# Проверяем наличие существующего бейджа
	existing_result = await db.execute(
		select(UserBadge).where(
			and_(
				UserBadge.user_id == user_id,
				UserBadge.badge_id == badge_id
			)
		)
	)
	existing = existing_result.scalar_one_or_none()
	
	if existing:
		# Если бейдж существует и не истек - продлеваем
		if existing.expires_at is None or existing.expires_at > now:
			if badge.badge_type.value == "temporary" and existing.expires_at:
				# Продлеваем temporary бейдж
				existing.expires_at = now + timedelta(hours=1)
				await db.commit()
				await db.refresh(existing)
				logger.info(f"Extended badge {badge_id} for user {user_id} until {existing.expires_at}")
			# Для permanent бейджей просто возвращаем (не нужно продлевать)
			return existing
		# Если истек - выдаем новый (награды не выдаем, т.к. это продление)
		logger.info(f"Badge {badge_id} expired for user {user_id}, awarding new one")
		return await award_badge(user_id, badge_id, expires_at, db, is_first_time=False)
	else:
		# Выдаем новый бейдж (награды выдаем)
		return await award_badge(user_id, badge_id, expires_at, db, is_first_time=True)


async def check_periodic_badges(db: AsyncSession) -> None:
	"""
	Проверяет все периодические бейджи (с auto_check=True).
	Вызывается из cron задачи.
	
	Args:
		db: Асинхронная сессия базы данных
	"""
	# Находим все бейджи с auto_check=True
	result = await db.execute(
		select(Badge).where(Badge.auto_check)
	)
	badges = result.scalars().all()
	
	logger.info(f"Found {len(badges)} periodic badges to check")
	
	for badge in badges:
		try:
			# Импортируем обработчики условий
			from app.services.badge_conditions import CONDITION_HANDLERS
			
			handler_class = CONDITION_HANDLERS.get(badge.condition_key)
			if not handler_class:
				logger.warning(f"No handler found for condition_key: {badge.condition_key}")
				continue
			
			logger.info(f"Checking badge {badge.id} ({badge.name}) with condition_key: {badge.condition_key}")
			handler = handler_class()
			# Для периодических проверок используем специальный метод
			if hasattr(handler, 'check_and_extend_or_award'):
				await handler.check_and_extend_or_award(db, badge.id)
				logger.info(f"Successfully processed badge {badge.id}")
			else:
				logger.warning(f"Handler for {badge.condition_key} doesn't have check_and_extend_or_award method")
		except Exception as e:
			logger.error(f"Error checking periodic badge {badge.id}: {e}", exc_info=True)

