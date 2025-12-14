"""
Сервис для создания и получения событий активности.
"""
from typing import Optional, Dict, Any, List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload
import logging

from app.models.activity import Activity, ActivityType

logger = logging.getLogger(__name__)


async def create_activity(
	db: AsyncSession,
	activity_type: ActivityType,
	title: str,
	description: Optional[str] = None,
	user_id: Optional[UUID] = None,
	server_id: Optional[UUID] = None,
	meta_data: Optional[Dict[str, Any]] = None
) -> Optional[Activity]:
	"""
	Создает событие активности.
	
	Args:
		db: Асинхронная сессия базы данных
		activity_type: Тип события
		title: Заголовок события
		description: Описание события
		user_id: UUID пользователя (если применимо)
		server_id: UUID сервера (если применимо)
		meta_data: Дополнительные метаданные
		
	Returns:
		Activity или None если создание не удалось
	"""
	try:
		activity = Activity(
			activity_type=activity_type,
			title=title,
			description=description,
			user_id=user_id,
			server_id=server_id,
			meta_data=meta_data
		)
		db.add(activity)
		await db.commit()
		await db.refresh(activity)
		return activity
	except Exception as e:
		logger.error(f"Failed to create activity: {e}", exc_info=True)
		await db.rollback()
		return None


async def get_activity_feed(
	db: AsyncSession,
	limit: int = 50,
	offset: int = 0,
	activity_type: Optional[ActivityType] = None
) -> List[Activity]:
	"""
	Получает ленту активности.
	
	Args:
		db: Асинхронная сессия базы данных
		limit: Количество событий
		offset: Смещение для пагинации
		activity_type: Фильтр по типу события (опционально)
		
	Returns:
		Список событий активности, отсортированных по created_at DESC
	"""
	try:
		query = select(Activity).options(
			selectinload(Activity.user),
			selectinload(Activity.server)
		).order_by(desc(Activity.created_at))
		
		if activity_type:
			query = query.where(Activity.activity_type == activity_type)
		
		query = query.limit(limit).offset(offset)
		
		result = await db.execute(query)
		return list(result.scalars().all())
	except Exception as e:
		logger.error(f"Failed to get activity feed: {e}", exc_info=True)
		return []
