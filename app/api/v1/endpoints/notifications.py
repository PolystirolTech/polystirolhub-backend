from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List
from app.api import deps
from app.models.user import User
from app.models.notification import Notification
from app.schemas.notification import NotificationResponse

router = APIRouter()


@router.get("/recent", response_model=List[NotificationResponse])
async def get_recent_notifications(
	current_user: User = Depends(deps.get_current_user),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Получить 3 последних уведомления текущего пользователя"""
	result = await db.execute(
		select(Notification)
		.where(Notification.user_id == current_user.id)
		.order_by(desc(Notification.created_at))
		.limit(3)
	)
	notifications = result.scalars().all()
	return [NotificationResponse.model_validate(notification) for notification in notifications]


@router.get("", response_model=List[NotificationResponse])
async def get_all_notifications(
	skip: int = Query(0, ge=0, description="Количество пропущенных записей"),
	limit: int = Query(50, ge=1, le=100, description="Максимальное количество записей"),
	current_user: User = Depends(deps.get_current_user),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Получить все уведомления текущего пользователя с пагинацией"""
	result = await db.execute(
		select(Notification)
		.where(Notification.user_id == current_user.id)
		.order_by(desc(Notification.created_at))
		.offset(skip)
		.limit(limit)
	)
	notifications = result.scalars().all()
	return [NotificationResponse.model_validate(notification) for notification in notifications]
