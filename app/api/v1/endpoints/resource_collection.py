from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import List, Optional
from uuid import UUID

from app.api import deps
from app.models.user import User
from app.models.game_server import GameServer
from app.models.resource_collection import ResourceGoal, ResourceProgress
from app.schemas.resource_collection import (
	ResourceCollectionRequest,
	ResourceCollectionResponse,
	ResourceProgressResponse,
	ResourceProgressDetail,
	ResourceGoalCreate,
	ResourceGoalUpdate,
	ResourceGoalResponse,
)
from app.services.resource_collection import process_resource_collection
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


# ========== Публичные эндпоинты ==========

@router.post("/collect", response_model=ResourceCollectionResponse, status_code=status.HTTP_201_CREATED)
async def collect_resources(
	request: ResourceCollectionRequest,
	db: AsyncSession = Depends(deps.get_db)
):
	"""
	Принимает данные о собранных ресурсах от мода.
	Идентификация сервера по server_uuid (UUID из game_servers).
	"""
	success, current_amount, error = await process_resource_collection(db, request)
	
	if not success:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail=error or "Failed to process resource collection"
		)
	
	return ResourceCollectionResponse(
		success=True,
		message="Resource collection processed successfully",
		current_amount=current_amount
	)


@router.get("/servers/{server_id}/progress", response_model=ResourceProgressResponse)
async def get_server_progress(
	server_id: UUID,
	db: AsyncSession = Depends(deps.get_db)
):
	"""Получает прогресс сбора ресурсов для сервера для отображения на сайте"""
	# Получаем сервер
	result = await db.execute(
		select(GameServer).where(GameServer.id == server_id)
	)
	server = result.scalar_one_or_none()
	
	if not server:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Server not found"
		)
	
	# Получаем все активные цели для сервера
	result = await db.execute(
		select(ResourceGoal).where(
			and_(
				ResourceGoal.server_id == server_id,
				ResourceGoal.is_active
			)
		)
	)
	goals = result.scalars().all()
	
	# Получаем весь прогресс для сервера
	result = await db.execute(
		select(ResourceProgress).where(ResourceProgress.server_id == server_id)
	)
	progress_list = result.scalars().all()
	
	# Создаем словари для быстрого поиска
	goals_dict = {goal.resource_type: goal for goal in goals}
	progress_dict = {progress.resource_type: progress for progress in progress_list}
	
	# Формируем список ресурсов с детальной информацией
	resources = []
	
	# Добавляем ресурсы, по которым есть цели
	for goal in goals:
		progress = progress_dict.get(goal.resource_type)
		current_amount = progress.current_amount if progress else 0
		
		# Вычисляем процент выполнения
		progress_percentage = None
		if goal.target_amount > 0:
			progress_percentage = min(100.0, (current_amount / goal.target_amount) * 100.0)
		
		resources.append(ResourceProgressDetail(
			resource_type=goal.resource_type,
			name=goal.name,
			current_amount=current_amount,
			target_amount=goal.target_amount,
			goal_id=goal.id,
			is_active=goal.is_active,
			progress_percentage=round(progress_percentage, 2) if progress_percentage is not None else None,
			updated_at=progress.updated_at if progress else goal.updated_at
		))
	
	# Добавляем ресурсы, по которым есть прогресс, но нет целей
	for resource_type, progress in progress_dict.items():
		if resource_type not in goals_dict:
			resources.append(ResourceProgressDetail(
				resource_type=resource_type,
				current_amount=progress.current_amount,
				target_amount=None,
				goal_id=None,
				is_active=None,
				progress_percentage=None,
				updated_at=progress.updated_at
			))
	
	return ResourceProgressResponse(
		server_id=server.id,
		server_name=server.name,
		resources=resources
	)


# ========== Админские эндпоинты ==========

@router.post("/admin/goals", response_model=ResourceGoalResponse, status_code=status.HTTP_201_CREATED)
async def create_resource_goal(
	goal: ResourceGoalCreate,
	current_user: User = Depends(deps.get_current_admin),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Создание цели сбора ресурсов для сервера. Только для админов."""
	# Проверяем, существует ли сервер
	result = await db.execute(
		select(GameServer).where(GameServer.id == goal.server_id)
	)
	server = result.scalar_one_or_none()
	
	if not server:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Server not found"
		)
	
	# Проверяем, нет ли уже цели для этого сервера и типа ресурса
	result = await db.execute(
		select(ResourceGoal).where(
			and_(
				ResourceGoal.server_id == goal.server_id,
				ResourceGoal.resource_type == goal.resource_type
			)
		)
	)
	existing_goal = result.scalar_one_or_none()
	
	if existing_goal:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail=f"Goal for resource type '{goal.resource_type}' already exists for this server"
		)
	
	# Создаем цель
	new_goal = ResourceGoal(
		server_id=goal.server_id,
		name=goal.name,
		resource_type=goal.resource_type,
		target_amount=goal.target_amount,
		is_active=goal.is_active
	)
	
	db.add(new_goal)
	await db.commit()
	await db.refresh(new_goal)
	
	return new_goal


@router.get("/admin/goals", response_model=List[ResourceGoalResponse])
async def list_resource_goals(
	server_id: Optional[UUID] = Query(None, description="Фильтр по серверу"),
	skip: int = Query(0, ge=0, description="Количество пропущенных записей"),
	limit: int = Query(50, ge=1, le=100, description="Максимальное количество записей"),
	current_user: User = Depends(deps.get_current_admin),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Список целей сбора ресурсов. Только для админов."""
	query = select(ResourceGoal)
	
	if server_id:
		query = query.where(ResourceGoal.server_id == server_id)
	
	query = query.order_by(ResourceGoal.created_at.desc()).offset(skip).limit(limit)
	
	result = await db.execute(query)
	goals = result.scalars().all()
	
	return goals


@router.get("/admin/goals/{goal_id}", response_model=ResourceGoalResponse)
async def get_resource_goal(
	goal_id: UUID,
	current_user: User = Depends(deps.get_current_admin),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Получение цели по ID. Только для админов."""
	result = await db.execute(
		select(ResourceGoal).where(ResourceGoal.id == goal_id)
	)
	goal = result.scalar_one_or_none()
	
	if not goal:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Resource goal not found"
		)
	
	return goal


@router.put("/admin/goals/{goal_id}", response_model=ResourceGoalResponse)
async def update_resource_goal(
	goal_id: UUID,
	goal_update: ResourceGoalUpdate,
	current_user: User = Depends(deps.get_current_admin),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Обновление цели. Только для админов."""
	result = await db.execute(
		select(ResourceGoal).where(ResourceGoal.id == goal_id)
	)
	goal = result.scalar_one_or_none()
	
	if not goal:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Resource goal not found"
		)
	
	# Если меняется server_id, проверяем существование сервера
	if goal_update.server_id is not None:
		result = await db.execute(
			select(GameServer).where(GameServer.id == goal_update.server_id)
		)
		server = result.scalar_one_or_none()
		
		if not server:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="Server not found"
			)
	
	# Если меняется server_id или resource_type, проверяем уникальность
	if goal_update.server_id is not None or goal_update.resource_type is not None:
		new_server_id = goal_update.server_id or goal.server_id
		new_resource_type = goal_update.resource_type or goal.resource_type
		
		result = await db.execute(
			select(ResourceGoal).where(
				and_(
					ResourceGoal.server_id == new_server_id,
					ResourceGoal.resource_type == new_resource_type,
					ResourceGoal.id != goal_id
				)
			)
		)
		existing_goal = result.scalar_one_or_none()
		
		if existing_goal:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail=f"Goal for resource type '{new_resource_type}' already exists for this server"
			)
	
	# Обновляем поля
	if goal_update.server_id is not None:
		goal.server_id = goal_update.server_id
	if goal_update.name is not None:
		goal.name = goal_update.name
	if goal_update.resource_type is not None:
		goal.resource_type = goal_update.resource_type
	if goal_update.target_amount is not None:
		goal.target_amount = goal_update.target_amount
	if goal_update.is_active is not None:
		goal.is_active = goal_update.is_active
	
	await db.commit()
	await db.refresh(goal)
	
	return goal


@router.delete("/admin/goals/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resource_goal(
	goal_id: UUID,
	current_user: User = Depends(deps.get_current_admin),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Удаление цели. Только для админов."""
	result = await db.execute(
		select(ResourceGoal).where(ResourceGoal.id == goal_id)
	)
	goal = result.scalar_one_or_none()
	
	if not goal:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Resource goal not found"
		)
	
	await db.delete(goal)
	await db.commit()
	
	return None

