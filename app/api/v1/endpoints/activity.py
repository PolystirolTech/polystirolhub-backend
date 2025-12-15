from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.api import deps
from app.services.activity import get_activity_feed
from app.models.activity import ActivityType
from app.schemas.activity import ActivityResponse, ServerInfo
from app.schemas.user import UserBase

router = APIRouter()


@router.get("", response_model=list[ActivityResponse])
async def get_activity(
	limit: int = Query(default=50, ge=1, le=100),
	offset: int = Query(default=0, ge=0),
	activity_type: Optional[str] = Query(default=None),
	db: AsyncSession = Depends(deps.get_db)
):
	"""
	Получить ленту активности. Публичный endpoint.
	
	Args:
		limit: Количество событий (1-100)
		offset: Смещение для пагинации
		activity_type: Фильтр по типу события (опционально)
		db: Сессия базы данных
		
	Returns:
		Список событий активности, отсортированных по дате создания (DESC)
	"""
	activity_type_enum = None
	if activity_type:
		try:
			activity_type_enum = ActivityType(activity_type)
		except ValueError:
			# Если передан неверный тип, игнорируем фильтр
			pass
	
	activities = await get_activity_feed(
		db=db,
		limit=limit,
		offset=offset,
		activity_type=activity_type_enum
	)
	
	# Преобразуем в ответы
	result = []
	for activity in activities:
		user_data = None
		if activity.user:
			user_data = UserBase(
				email=activity.user.email,
				username=activity.user.username,
				avatar=activity.user.avatar,
				is_active=activity.user.is_active,
				is_admin=activity.user.is_admin,
				is_super_admin=activity.user.is_super_admin,
				xp=activity.user.xp,
				level=activity.user.level,
				selected_badge_id=activity.user.selected_badge_id
			)
		
		server_data = None
		if activity.server:
			server_data = ServerInfo(
				id=activity.server.id,
				name=activity.server.name,
				status=activity.server.status.value
			)
		
		result.append(ActivityResponse(
			id=activity.id,
			activity_type=activity.activity_type.value,
			title=activity.title,
			description=activity.description,
			meta_data=activity.meta_data,
			user=user_data,
			server=server_data,
			created_at=activity.created_at
		))
	
	return result
