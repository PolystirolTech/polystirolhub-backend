"""
Обработчики условий для бейджей.
"""
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
import logging

from app.models.user import User
from app.models.badge import Badge, UserBadge
from app.services.badge_progress import extend_or_award_badge

logger = logging.getLogger(__name__)


class BaseConditionHandler:
	"""Базовый класс для обработчиков условий."""
	
	async def calculate_progress(
		self,
		user_id: UUID,
		config: Dict[str, Any],
		db: AsyncSession
	) -> int:
		"""
		Вычисляет текущий прогресс пользователя.
		
		Args:
			user_id: UUID пользователя
			config: Конфигурация условия
			db: Асинхронная сессия базы данных
			
		Returns:
			Текущее значение прогресса
		"""
		raise NotImplementedError("Subclasses must implement calculate_progress")


class XPLeaderHandler(BaseConditionHandler):
	"""Обработчик для проверки лидера по XP."""
	
	async def get_leader(self, db: AsyncSession) -> Optional[User]:
		"""
		Находит лидера по XP.
		
		Args:
			db: Асинхронная сессия базы данных
			
		Returns:
			User с максимальным XP или None
		"""
		result = await db.execute(
			select(User)
			.order_by(desc(User.xp))
			.limit(1)
		)
		return result.scalar_one_or_none()
	
	async def check_and_extend_or_award(
		self,
		db: AsyncSession,
		badge_id: UUID
	) -> None:
		"""
		Проверяет и продлевает/выдает бейдж лидеру по XP.
		
		Args:
			db: Асинхронная сессия базы данных
			badge_id: UUID бейджа
		"""
		leader = await self.get_leader(db)
		if not leader:
			logger.warning(f"No leader found for badge {badge_id}")
			return
		
		logger.info(f"XP leader found: user_id={leader.id}, username={leader.username}, xp={leader.xp}")
		
		try:
			user_badge = await extend_or_award_badge(leader.id, badge_id, db)
			if user_badge:
				logger.info(f"Badge {badge_id} awarded/extended to leader {leader.id}. Expires at: {user_badge.expires_at}")
			else:
				logger.warning(f"Failed to award badge {badge_id} to leader {leader.id}")
		except Exception as e:
			logger.error(f"Error awarding badge {badge_id} to XP leader {leader.id}: {e}", exc_info=True)
	
	async def calculate_progress(
		self,
		user_id: UUID,
		config: Dict[str, Any],
		db: AsyncSession
	) -> int:
		"""Не используется для лидеров, т.к. лидер определяется через SQL запрос."""
		result = await db.execute(
			select(User.xp).where(User.id == user_id)
		)
		xp = result.scalar_one()
		return xp if xp else 0


class DeathsInSessionHandler(BaseConditionHandler):
	"""Обработчик для проверки смертей в сессии."""
	
	async def calculate_progress(
		self,
		user_id: UUID,
		config: Dict[str, Any],
		db: AsyncSession
	) -> int:
		"""
		Вычисляет количество смертей в текущей сессии.
		Это событийный обработчик, прогресс передается напрямую через update_progress.
		
		Args:
			user_id: UUID пользователя
			config: Конфигурация условия (может содержать session_id)
			db: Асинхронная сессия базы данных
			
		Returns:
			Количество смертей (обычно передается из события)
		"""
		# Для событийных условий прогресс обычно передается напрямую
		# Этот метод может использоваться для проверки текущего состояния
		return 0


class PlaytimeLeaderSeasonHandler(BaseConditionHandler):
	"""Заглушка для лидерства по времени игры в сезоне."""
	
	async def calculate_progress(
		self,
		user_id: UUID,
		config: Dict[str, Any],
		db: AsyncSession
	) -> int:
		"""
		Заглушка - пока не реализовано.
		
		Args:
			user_id: UUID пользователя
			config: Конфигурация условия
			db: Асинхронная сессия базы данных
			
		Returns:
			0 (не реализовано)
		"""
		logger.warning("PlaytimeLeaderSeasonHandler is not implemented yet")
		return 0


class MessagesSentHandler(BaseConditionHandler):
	"""Заглушка для количества сообщений в чате."""
	
	async def calculate_progress(
		self,
		user_id: UUID,
		config: Dict[str, Any],
		db: AsyncSession
	) -> int:
		"""
		Заглушка - статистика сообщений пока не считается.
		
		Args:
			user_id: UUID пользователя
			config: Конфигурация условия
			db: Асинхронная сессия базы данных
			
		Returns:
			0 (не реализовано)
		"""
		logger.warning("MessagesSentHandler is not implemented yet - message statistics not tracked")
		return 0


# Реестр обработчиков условий
CONDITION_HANDLERS: Dict[str, type] = {
	"xp_leader": XPLeaderHandler,
	"deaths_in_session": DeathsInSessionHandler,
	"playtime_leader_season": PlaytimeLeaderSeasonHandler,
	"messages_sent": MessagesSentHandler,
}

