from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.api import deps
from app.models.user import User
from uuid import UUID
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class CreateSuperAdminRequest(BaseModel):
	user_id: UUID


class AdminResponse(BaseModel):
	id: UUID
	email: str | None
	username: str | None
	is_admin: bool
	is_super_admin: bool
	created_at: str

	class Config:
		from_attributes = True


class UserResponse(BaseModel):
	id: UUID
	email: str | None
	username: str | None
	avatar: str | None
	is_active: bool
	is_admin: bool
	is_super_admin: bool
	xp: int
	level: int
	created_at: str

	class Config:
		from_attributes = True


@router.get("/check-super-admin")
async def check_super_admin(
	db: AsyncSession = Depends(deps.get_db)
):
	"""Публичный эндпоинт для проверки наличия super admin в БД. Возвращает true/false."""
	result = await db.execute(
		select(func.count(User.id)).where(User.is_super_admin)
	)
	super_admin_count = result.scalar()
	return {"has_super_admin": super_admin_count > 0}


@router.post("/create-super-admin", response_model=AdminResponse)
async def create_super_admin(
	request: CreateSuperAdminRequest,
	db: AsyncSession = Depends(deps.get_db)
):
	"""Создание первого super admin. Доступно только если нет ни одного super admin."""
	# Проверяем, есть ли уже super admin
	result = await db.execute(
		select(func.count(User.id)).where(User.is_super_admin)
	)
	super_admin_count = result.scalar()
	
	if super_admin_count > 0:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="Super admin already exists. This endpoint is only available when no super admin exists."
		)
	
	# Получаем пользователя
	result = await db.execute(select(User).where(User.id == request.user_id))
	user = result.scalars().first()
	
	if not user:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="User not found"
		)
	
	# Назначаем super admin
	user.is_super_admin = True
	user.is_admin = True  # Super admin автоматически является админом
	await db.commit()
	await db.refresh(user)
	
	return AdminResponse(
		id=user.id,
		email=user.email,
		username=user.username,
		is_admin=user.is_admin,
		is_super_admin=user.is_super_admin,
		created_at=user.created_at.isoformat()
	)


@router.post("/promote/{user_id}", response_model=AdminResponse)
async def promote_to_admin(
	user_id: UUID,
	current_user: User = Depends(deps.get_current_super_admin),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Назначение админа. Только super admin может назначать админов."""
	# Получаем пользователя для повышения
	result = await db.execute(select(User).where(User.id == user_id))
	user = result.scalars().first()
	
	if not user:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="User not found"
		)
	
	# Нельзя повысить самого себя (он уже super admin)
	if user.id == current_user.id:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Cannot promote yourself. You are already a super admin."
		)
	
	# Назначаем админом
	user.is_admin = True
	await db.commit()
	await db.refresh(user)
	
	return AdminResponse(
		id=user.id,
		email=user.email,
		username=user.username,
		is_admin=user.is_admin,
		is_super_admin=user.is_super_admin,
		created_at=user.created_at.isoformat()
	)


@router.post("/demote/{user_id}", response_model=AdminResponse)
async def demote_from_admin(
	user_id: UUID,
	current_user: User = Depends(deps.get_current_super_admin),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Снятие админки. Только super admin может снимать админку. Нельзя снять админку у другого super admin."""
	# Получаем пользователя для понижения
	result = await db.execute(select(User).where(User.id == user_id))
	user = result.scalars().first()
	
	if not user:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="User not found"
		)
	
	# Нельзя снять админку у другого super admin
	if user.is_super_admin:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Cannot demote a super admin. Only regular admins can be demoted."
		)
	
	# Нельзя снять админку у самого себя
	if user.id == current_user.id:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Cannot demote yourself. You are a super admin."
		)
	
	# Снимаем админку
	user.is_admin = False
	await db.commit()
	await db.refresh(user)
	
	return AdminResponse(
		id=user.id,
		email=user.email,
		username=user.username,
		is_admin=user.is_admin,
		is_super_admin=user.is_super_admin,
		created_at=user.created_at.isoformat()
	)


@router.get("/list", response_model=list[AdminResponse])
async def list_admins(
	skip: int = Query(0, ge=0, description="Количество пропущенных записей"),
	limit: int = Query(50, ge=1, le=100, description="Максимальное количество записей"),
	current_user: User = Depends(deps.get_current_admin),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Список всех админов. Доступно только для админов."""
	# Получаем всех админов (is_admin=True или is_super_admin=True)
	result = await db.execute(
		select(User).where(
			(User.is_admin) | (User.is_super_admin)
		).order_by(User.created_at)
		.offset(skip)
		.limit(limit)
	)
	admins = result.scalars().all()
	
	return [
		AdminResponse(
			id=admin.id,
			email=admin.email,
			username=admin.username,
			is_admin=admin.is_admin,
			is_super_admin=admin.is_super_admin,
			created_at=admin.created_at.isoformat()
		)
		for admin in admins
	]


@router.get("/users", response_model=list[UserResponse])
async def get_all_users(
	skip: int = Query(0, ge=0, description="Количество пропущенных записей"),
	limit: int = Query(50, ge=1, le=100, description="Максимальное количество записей"),
	current_user: User = Depends(deps.get_current_admin),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Получить список всех пользователей. Доступно только для админов."""
	result = await db.execute(
		select(User).order_by(User.created_at)
		.offset(skip)
		.limit(limit)
	)
	users = result.scalars().all()
	
	return [
		UserResponse(
			id=user.id,
			email=user.email,
			username=user.username,
			avatar=user.avatar,
			is_active=user.is_active,
			is_admin=user.is_admin,
			is_super_admin=user.is_super_admin,
			xp=user.xp,
			level=user.level,
			created_at=user.created_at.isoformat()
		)
		for user in users
	]
