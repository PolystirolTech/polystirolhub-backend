"""
Сервис для создания уведомлений.
"""
from typing import Optional, Dict, Any
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.models.notification import Notification

logger = logging.getLogger(__name__)


async def create_notification(
	db: AsyncSession,
	user_id: UUID,
	notification_type: str,
	title: str,
	message: Optional[str] = None,
	reward_xp: int = 0,
	reward_balance: int = 0,
	meta_data: Optional[Dict[str, Any]] = None
) -> Optional[Notification]:
	"""
	Создает уведомление для пользователя.
	
	Args:
		db: Асинхронная сессия базы данных
		user_id: UUID пользователя
		notification_type: Тип уведомления ("level_up", "achievement_unlocked", "badge_earned")
		title: Заголовок уведомления
		message: Описание уведомления
		reward_xp: Полученный XP
		reward_balance: Полученная валюта
		meta_data: Дополнительные метаданные
		
	Returns:
		Notification или None если создание не удалось
	"""
	try:
		notification = Notification(
			user_id=user_id,
			notification_type=notification_type,
			title=title,
			message=message,
			reward_xp=reward_xp,
			reward_balance=reward_balance,
			meta_data=meta_data
		)
		db.add(notification)
		await db.commit()
		await db.refresh(notification)
		return notification
	except Exception as e:
		logger.error(f"Failed to create notification for user {user_id}: {e}", exc_info=True)
		await db.rollback()
		return None
