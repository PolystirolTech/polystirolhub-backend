from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, and_, or_
from sqlalchemy.orm import selectinload
from typing import Optional
from datetime import datetime, timezone
from app.api import deps
from app.models.user import User, ExternalLink
from app.models.badge import Badge as BadgeModel, UserBadge, BadgeType
from app.models.statistics import MinecraftUser
from app.schemas.badge import (
	Badge,
	UserBadgeWithBadge,
	AwardBadgeRequest
)
from app.core.storage import get_badges_storage, get_resource_packs_storage
from app.core.config import settings
from app.models.game_server import GameServer
from app.services.resource_pack_generator import generate_unicode_char, generate_resource_pack
from uuid import UUID
import logging
import uuid

logger = logging.getLogger(__name__)

router = APIRouter()

# ========== Публичные эндпоинты ==========

@router.get("/badges", response_model=list[Badge])
async def get_badges(
	db: AsyncSession = Depends(deps.get_db)
):
	"""Публичный список всех доступных бэджиков"""
	result = await db.execute(
		select(BadgeModel).order_by(BadgeModel.created_at.desc())
	)
	badges = result.scalars().all()
	return badges

# ========== Пользовательские эндпоинты ==========
# ВАЖНО: /badges/me должен быть объявлен ДО /badges/{badge_id}, иначе FastAPI будет интерпретировать "me" как badge_id

@router.get("/badges/me", response_model=list[UserBadgeWithBadge])
async def get_my_badges(
	current_user: User = Depends(deps.get_current_user),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Получить список моих бэджиков"""
	logger.info(f"get_my_badges called for user {current_user.id}")
	try:
		now = datetime.now(timezone.utc)
		
		result = await db.execute(
			select(UserBadge)
			.options(selectinload(UserBadge.badge))
			.where(
				and_(
					UserBadge.user_id == current_user.id,
					or_(
						UserBadge.expires_at.is_(None),
						UserBadge.expires_at > now
					)
				)
			)
			.order_by(UserBadge.received_at.desc())
		)
		user_badges = result.scalars().all()
		
		logger.info(f"Found {len(user_badges)} badges for user {current_user.id}")
		
		# Если список пустой, возвращаем пустой список (явно сериализованный)
		if not user_badges:
			logger.info("Returning empty list")
			return []
		
		# Сериализуем через Pydantic для правильной конвертации enum
		result_list = []
		for ub in user_badges:
			try:
				# Явно конвертируем данные для избежания проблем с UUID и enum
				badge_data = {
					"id": str(ub.id),
					"user_id": str(ub.user_id),
					"badge_id": str(ub.badge_id),
					"received_at": ub.received_at,
					"expires_at": ub.expires_at,
					"badge": {
						"id": str(ub.badge.id),
						"name": ub.badge.name,
						"description": ub.badge.description,
						"image_url": ub.badge.image_url,
						"badge_type": ub.badge.badge_type.value if hasattr(ub.badge.badge_type, 'value') else str(ub.badge.badge_type),
						"created_at": ub.badge.created_at
					}
				}
				result_list.append(UserBadgeWithBadge.model_validate(badge_data))
			except Exception as e:
				logger.error(f"Error serializing user badge {ub.id}: {e}", exc_info=True)
				logger.error(f"Badge data: id={ub.id}, user_id={ub.user_id}, badge_id={ub.badge_id}")
				if ub.badge:
					logger.error(f"Badge: id={ub.badge.id}, badge_type={ub.badge.badge_type}, type={type(ub.badge.badge_type)}")
				raise HTTPException(
					status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
					detail=f"Error serializing badge: {str(e)}"
				)
		
		logger.info(f"Returning {len(result_list)} serialized badges")
		return result_list
	except HTTPException:
		raise
	except Exception as e:
		logger.error(f"Unexpected error in get_my_badges: {e}", exc_info=True)
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=f"Internal server error: {str(e)}"
		)

@router.patch("/badges/me/select")
async def select_badge(
	badge_id: UUID = Query(..., description="ID бэйджа для выбора"),
	current_user: User = Depends(deps.get_current_user),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Выбрать бэйджик для отображения"""
	# Проверяем, что бэйджик есть у пользователя
	result = await db.execute(
		select(UserBadge).where(
			and_(
				UserBadge.user_id == current_user.id,
				UserBadge.badge_id == badge_id
			)
		)
	)
	user_badge = result.scalars().first()
	
	if not user_badge:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Badge not found in your collection"
		)
	
	# Проверяем, что бэйджик не истек (для временных)
	now = datetime.now(timezone.utc)
	if user_badge.expires_at and user_badge.expires_at <= now:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="This badge has expired"
		)
	
	# Обновляем selected_badge_id
	current_user.selected_badge_id = badge_id
	await db.commit()
	await db.refresh(current_user)
	
	return {"message": "Badge selected successfully", "selected_badge_id": str(badge_id)}

@router.delete("/badges/me/select")
async def deselect_badge(
	current_user: User = Depends(deps.get_current_user),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Снять выбранный бэйджик"""
	current_user.selected_badge_id = None
	await db.commit()
	await db.refresh(current_user)
	
	return {"message": "Badge deselected successfully"}

@router.get("/badges/conditions")
async def get_available_conditions(
	db: AsyncSession = Depends(deps.get_db)
):
	"""
	Возвращает список всех доступных condition_key с описаниями.
	Доступно всем пользователям для понимания возможных условий.
	"""
	from app.core.badge_conditions import get_available_conditions
	
	conditions = get_available_conditions()
	return conditions

# ========== Публичные эндпоинты (продолжение) ==========
# ВАЖНО: Этот эндпоинт должен быть ПОСЛЕ /badges/me и /badges/conditions, иначе FastAPI будет интерпретировать их как badge_id

@router.get("/badges/{badge_id}", response_model=Badge)
async def get_badge(
	badge_id: UUID,
	db: AsyncSession = Depends(deps.get_db)
):
	"""Публичное получение информации о бэйдже"""
	result = await db.execute(
		select(BadgeModel).where(BadgeModel.id == badge_id)
	)
	badge = result.scalars().first()
	
	if not badge:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Badge not found"
		)
	
	return badge

@router.get("/badges/minecraft/{player_uuid}", response_model=Optional[Badge])
async def get_minecraft_player_selected_badge(
	player_uuid: str,
	db: AsyncSession = Depends(deps.get_db)
):
	"""Получить выбранный бэджик игрока Minecraft по его UUID"""
	# Валидация UUID формата (36 символов)
	if len(player_uuid) != 36:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Invalid player UUID format"
		)
	
	# Сначала проверяем, существует ли игрок в MinecraftUser
	result = await db.execute(
		select(MinecraftUser).where(MinecraftUser.uuid == player_uuid)
	)
	minecraft_user = result.scalar_one_or_none()
	
	if not minecraft_user:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Player not found"
		)
	
	# Поиск ExternalLink с platform="MC" и external_id=player_uuid
	result = await db.execute(
		select(ExternalLink)
		.options(selectinload(ExternalLink.user))
		.where(
			and_(
				ExternalLink.platform == "MC",
				ExternalLink.external_id == player_uuid
			)
		)
	)
	external_link = result.scalar_one_or_none()
	
	# Если нет связи с User, значит у игрока нет бэйджика
	if not external_link:
		return None
	
	# Получаем User
	user = external_link.user
	if not user:
		return None
	
	# Проверяем selected_badge_id
	if not user.selected_badge_id:
		return None
	
	# Получаем Badge по selected_badge_id
	badge_result = await db.execute(
		select(BadgeModel).where(BadgeModel.id == user.selected_badge_id)
	)
	badge = badge_result.scalar_one_or_none()
	
	if not badge:
		# Если badge не найден, возвращаем null
		return None
	
	# Проверяем, что у пользователя есть UserBadge с этим badge_id
	now = datetime.now(timezone.utc)
	user_badge_result = await db.execute(
		select(UserBadge).where(
			and_(
				UserBadge.user_id == user.id,
				UserBadge.badge_id == user.selected_badge_id,
				or_(
					UserBadge.expires_at.is_(None),
					UserBadge.expires_at > now
				)
			)
		)
	)
	user_badge = user_badge_result.scalar_one_or_none()
	
	# Если UserBadge не найден или истек, возвращаем null
	if not user_badge:
		return None
	
	return badge

# ========== Админские эндпоинты ==========

@router.post("/admin/badges", response_model=Badge)
async def create_badge(
	name: str = Form(...),
	description: Optional[str] = Form(None),
	badge_type: str = Form(...),
	image: UploadFile = File(...),
	condition_key: Optional[str] = Form(None),
	target_value: Optional[int] = Form(None),
	auto_check: Optional[bool] = Form(False),
	reward_xp: Optional[int] = Form(0),
	reward_balance: Optional[int] = Form(0),
	unicode_char: Optional[str] = Form(None),
	current_user: User = Depends(deps.get_current_admin),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Создание бэйджа (только для админов)"""
	# Валидация типа файла
	allowed_content_types = ["image/jpeg", "image/png", "image/webp"]
	if image.content_type not in allowed_content_types:
		raise HTTPException(
			status_code=400,
			detail=f"Invalid file type. Allowed types: {', '.join(allowed_content_types)}"
		)
	
	# Валидация размера файла (5MB)
	MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
	file_content = await image.read()
	if len(file_content) > MAX_FILE_SIZE:
		raise HTTPException(
			status_code=400,
			detail=f"File too large. Maximum size is {MAX_FILE_SIZE / 1024 / 1024}MB"
		)
	
	# Валидация типа бэйджа
	try:
		badge_type_enum = BadgeType(badge_type)
	except ValueError:
		raise HTTPException(
			status_code=400,
			detail=f"Invalid badge_type. Allowed values: {', '.join([bt.value for bt in BadgeType])}"
		)
	
	# Валидация condition_key если указан
	if condition_key:
		from app.core.badge_conditions import is_condition_valid, get_condition_info
		if not is_condition_valid(condition_key):
			available_keys = ", ".join(["xp_leader", "deaths_in_session", "playtime_leader_season", "messages_sent"])
			raise HTTPException(
				status_code=400,
				detail=f"Invalid condition_key. Available values: {available_keys}. Use GET /api/v1/badges/conditions for details."
			)
		
		# Проверяем требования условия
		condition_info = get_condition_info(condition_key)
		if condition_info:
			if condition_info.get("requires_target_value") and not target_value:
				raise HTTPException(
					status_code=400,
					detail=f"condition_key '{condition_key}' requires target_value to be set"
				)
			if condition_info.get("requires_auto_check") and not auto_check:
				raise HTTPException(
					status_code=400,
					detail=f"condition_key '{condition_key}' requires auto_check to be True"
				)
	
	# Определяем расширение файла
	content_type_to_ext = {
		"image/jpeg": "jpg",
		"image/png": "png",
		"image/webp": "webp"
	}
	file_ext = content_type_to_ext.get(image.content_type, "jpg")
	
	# Генерируем уникальное имя файла
	file_id = str(uuid.uuid4())
	file_name = f"{file_id}.{file_ext}"
	
	# Сохраняем файл
	storage = get_badges_storage()
	image_url = await storage.save(file_content, file_name)
	
	# Создаем бэйджик
	new_badge = BadgeModel(
		name=name,
		description=description,
		badge_type=badge_type_enum,
		image_url=image_url,
		condition_key=condition_key,
		target_value=target_value,
		auto_check=auto_check if auto_check is not None else False,
		reward_xp=reward_xp if reward_xp is not None else 0,
		reward_balance=reward_balance if reward_balance is not None else 0,
		unicode_char=unicode_char
	)
	
	# Генерируем unicode_char для нового баджа перед сохранением, если не указан
	if not new_badge.unicode_char:
		# Получаем количество существующих баджей (без нового)
		badges_count_result = await db.execute(select(BadgeModel))
		existing_badges_count = len(badges_count_result.scalars().all())
		new_badge.unicode_char = generate_unicode_char(existing_badges_count)
	
	db.add(new_badge)
	await db.commit()
	await db.refresh(new_badge)
	
	# Генерируем ресурс-пак для всех GameServer'ов
	try:
		game_servers_result = await db.execute(select(GameServer))
		game_servers = game_servers_result.scalars().all()
		resource_packs_storage = get_resource_packs_storage()
		
		for game_server in game_servers:
			try:
				await generate_resource_pack(db, resource_packs_storage, game_server.id)
			except Exception as e:
				logger.error(f"Failed to generate resource pack for game server {game_server.id}: {e}", exc_info=True)
	except Exception as e:
		logger.error(f"Failed to generate resource packs: {e}", exc_info=True)
		# Не прерываем выполнение, бадж создан успешно
	
	return new_badge

@router.get("/admin/badges", response_model=list[Badge])
async def list_badges(
	current_user: User = Depends(deps.get_current_admin),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Список всех бэджиков (только для админов)"""
	result = await db.execute(
		select(BadgeModel).order_by(BadgeModel.created_at.desc())
	)
	badges = result.scalars().all()
	return badges

@router.get("/admin/badges/{badge_id}", response_model=Badge)
async def get_badge_admin(
	badge_id: UUID,
	current_user: User = Depends(deps.get_current_admin),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Получение бэйджа (только для админов)"""
	result = await db.execute(
		select(BadgeModel).where(BadgeModel.id == badge_id)
	)
	badge = result.scalars().first()
	
	if not badge:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Badge not found"
		)
	
	return badge

@router.put("/admin/badges/{badge_id}", response_model=Badge)
async def update_badge(
	badge_id: UUID,
	name: Optional[str] = Form(None),
	description: Optional[str] = Form(None),
	badge_type: Optional[str] = Form(None),
	image: Optional[UploadFile] = File(None),
	condition_key: Optional[str] = Form(None),
	target_value: Optional[int] = Form(None),
	auto_check: Optional[bool] = Form(None),
	reward_xp: Optional[int] = Form(None),
	reward_balance: Optional[int] = Form(None),
	unicode_char: Optional[str] = Form(None),
	current_user: User = Depends(deps.get_current_admin),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Обновление бэйджа (только для админов)"""
	result = await db.execute(
		select(BadgeModel).where(BadgeModel.id == badge_id)
	)
	badge = result.scalars().first()
	
	if not badge:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Badge not found"
		)
	
	# Обновляем поля
	if name is not None:
		badge.name = name
	if description is not None:
		badge.description = description
	if badge_type is not None:
		try:
			badge.badge_type = BadgeType(badge_type)
		except ValueError:
			raise HTTPException(
				status_code=400,
				detail=f"Invalid badge_type. Allowed values: {', '.join([bt.value for bt in BadgeType])}"
			)
	if condition_key is not None:
		badge.condition_key = condition_key
	if target_value is not None:
		badge.target_value = target_value
	if auto_check is not None:
		badge.auto_check = auto_check
	if reward_xp is not None:
		badge.reward_xp = reward_xp
	if reward_balance is not None:
		badge.reward_balance = reward_balance
	if unicode_char is not None:
		badge.unicode_char = unicode_char
	
	# Обрабатываем новое изображение если загружено
	if image:
		# Валидация типа файла
		allowed_content_types = ["image/jpeg", "image/png", "image/webp"]
		if image.content_type not in allowed_content_types:
			raise HTTPException(
				status_code=400,
				detail=f"Invalid file type. Allowed types: {', '.join(allowed_content_types)}"
			)
		
		# Валидация размера файла (5MB)
		MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
		file_content = await image.read()
		if len(file_content) > MAX_FILE_SIZE:
			raise HTTPException(
				status_code=400,
				detail=f"File too large. Maximum size is {MAX_FILE_SIZE / 1024 / 1024}MB"
			)
		
		# Удаляем старое изображение если оно существует
		if badge.image_url:
			old_image = badge.image_url
			badges_base_url = settings.STORAGE_BADGES_BASE_URL
			full_base_url = f"{settings.BACKEND_BASE_URL}{badges_base_url}"
			
			if old_image.startswith(full_base_url) or old_image.startswith(badges_base_url):
				old_path = old_image.replace(full_base_url, "").replace(badges_base_url, "").lstrip("/")
				try:
					storage = get_badges_storage()
					await storage.delete(old_path)
				except Exception as e:
					logger.warning(f"Failed to delete old badge image {old_path}: {e}")
		
		# Определяем расширение файла
		content_type_to_ext = {
			"image/jpeg": "jpg",
			"image/png": "png",
			"image/webp": "webp"
		}
		file_ext = content_type_to_ext.get(image.content_type, "jpg")
		
		# Генерируем уникальное имя файла
		file_id = str(uuid.uuid4())
		file_name = f"{file_id}.{file_ext}"
		
		# Сохраняем новый файл
		storage = get_badges_storage()
		badge.image_url = await storage.save(file_content, file_name)
		
		# При обновлении изображения нужно перегенерировать ресурс-пак
		image_updated = True
	else:
		image_updated = False
	
	await db.commit()
	await db.refresh(badge)
	
	# Генерируем ресурс-пак для всех GameServer'ов если изображение было обновлено
	if image_updated:
		try:
			game_servers_result = await db.execute(select(GameServer))
			game_servers = game_servers_result.scalars().all()
			resource_packs_storage = get_resource_packs_storage()
			
			for game_server in game_servers:
				try:
					await generate_resource_pack(db, resource_packs_storage, game_server.id)
				except Exception as e:
					logger.error(f"Failed to generate resource pack for game server {game_server.id}: {e}", exc_info=True)
		except Exception as e:
			logger.error(f"Failed to generate resource packs: {e}", exc_info=True)
			# Не прерываем выполнение, бадж обновлен успешно
	
	return badge

@router.delete("/admin/badges/{badge_id}")
async def delete_badge(
	badge_id: UUID,
	current_user: User = Depends(deps.get_current_admin),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Удаление бэйджа (только для админов)"""
	result = await db.execute(
		select(BadgeModel).where(BadgeModel.id == badge_id)
	)
	badge = result.scalars().first()
	
	if not badge:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Badge not found"
		)
	
	# Проверяем, используется ли бэйджик
	user_badges_result = await db.execute(
		select(UserBadge).where(UserBadge.badge_id == badge_id)
	)
	user_badges = user_badges_result.scalars().all()
	
	if user_badges:
		# Проверяем, есть ли пользователи с selected_badge_id
		users_result = await db.execute(
			select(User).where(User.selected_badge_id == badge_id)
		)
		users_with_selected = users_result.scalars().all()
		
		# Сбрасываем selected_badge_id у всех пользователей
		for user in users_with_selected:
			user.selected_badge_id = None
		
		# Удаляем все связи UserBadge (каскадно)
		await db.execute(delete(UserBadge).where(UserBadge.badge_id == badge_id))
	
	# Удаляем изображение
	if badge.image_url:
		old_image = badge.image_url
		badges_base_url = settings.STORAGE_BADGES_BASE_URL
		full_base_url = f"{settings.BACKEND_BASE_URL}{badges_base_url}"
		
		if old_image.startswith(full_base_url) or old_image.startswith(badges_base_url):
			old_path = old_image.replace(full_base_url, "").replace(badges_base_url, "").lstrip("/")
			try:
				storage = get_badges_storage()
				await storage.delete(old_path)
			except Exception as e:
				logger.warning(f"Failed to delete badge image {old_path}: {e}")
	
	# Удаляем бэйджик
	await db.execute(delete(BadgeModel).where(BadgeModel.id == badge_id))
	await db.commit()
	
	# Перегенерируем ресурс-пак для всех GameServer'ов после удаления баджа
	try:
		game_servers_result = await db.execute(select(GameServer))
		game_servers = game_servers_result.scalars().all()
		resource_packs_storage = get_resource_packs_storage()
		
		for game_server in game_servers:
			try:
				await generate_resource_pack(db, resource_packs_storage, game_server.id)
			except Exception as e:
				logger.error(f"Failed to generate resource pack for game server {game_server.id}: {e}", exc_info=True)
	except Exception as e:
		logger.error(f"Failed to generate resource packs: {e}", exc_info=True)
		# Не прерываем выполнение, бадж удален успешно
	
	return {"message": "Badge deleted successfully"}

@router.post("/admin/badges/{badge_id}/award/{user_id}")
async def award_badge(
	badge_id: UUID,
	user_id: UUID,
	request: AwardBadgeRequest,
	current_user: User = Depends(deps.get_current_admin),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Выдача бэйджа пользователю (только для админов)"""
	# Проверяем существование бэйджа
	badge_result = await db.execute(
		select(BadgeModel).where(BadgeModel.id == badge_id)
	)
	badge = badge_result.scalars().first()
	
	if not badge:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Badge not found"
		)
	
	# Проверяем существование пользователя
	user_result = await db.execute(
		select(User).where(User.id == user_id)
	)
	user = user_result.scalars().first()
	
	if not user:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="User not found"
		)
	
	# Проверяем, нет ли уже такого бэйджа у пользователя
	existing_result = await db.execute(
		select(UserBadge).where(
			and_(
				UserBadge.user_id == user_id,
				UserBadge.badge_id == badge_id
			)
		)
	)
	existing = existing_result.scalars().first()
	
	if existing:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="User already has this badge"
		)
	
	# Для временных бэджиков проверяем наличие expires_at
	expires_at = request.expires_at
	if badge.badge_type == BadgeType.temporary and not expires_at:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="expires_at is required for temporary badges"
		)
	
	# Создаем связь
	new_user_badge = UserBadge(
		user_id=user_id,
		badge_id=badge_id,
		expires_at=expires_at
	)
	
	db.add(new_user_badge)
	await db.commit()
	await db.refresh(new_user_badge)
	
	# Загружаем с информацией о бэйдже
	result = await db.execute(
		select(UserBadge)
		.options(selectinload(UserBadge.badge))
		.where(UserBadge.id == new_user_badge.id)
	)
	user_badge = result.scalars().first()
	
	return UserBadgeWithBadge.model_validate(user_badge)

@router.delete("/admin/badges/{badge_id}/revoke/{user_id}")
async def revoke_badge(
	badge_id: UUID,
	user_id: UUID,
	current_user: User = Depends(deps.get_current_admin),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Отзыв бэйджа у пользователя (только для админов)"""
	# Проверяем существование связи
	result = await db.execute(
		select(UserBadge).where(
			and_(
				UserBadge.user_id == user_id,
				UserBadge.badge_id == badge_id
			)
		)
	)
	user_badge = result.scalars().first()
	
	if not user_badge:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="User badge not found"
		)
	
	# Если это selected_badge_id, сбрасываем
	user_result = await db.execute(
		select(User).where(User.id == user_id)
	)
	user = user_result.scalars().first()
	
	if user and user.selected_badge_id == badge_id:
		user.selected_badge_id = None
	
	# Удаляем связь
	await db.execute(
		delete(UserBadge).where(UserBadge.id == user_badge.id)
	)
	await db.commit()
	
	return {"message": "Badge revoked successfully"}

@router.post("/admin/badges/check-periodic")
async def check_periodic_badges_endpoint(
	current_user: User = Depends(deps.get_current_admin),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Ручной запуск проверки периодических бейджей (только для админов)"""
	from app.services.badge_progress import check_periodic_badges
	
	try:
		await check_periodic_badges(db)
		return {"message": "Periodic badge check completed successfully"}
	except Exception as e:
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=f"Error during periodic badge check: {str(e)}"
		)

@router.post("/admin/badges/{badge_id}/check/{user_id}")
async def check_badge_for_user(
	badge_id: UUID,
	user_id: UUID,
	current_user: User = Depends(deps.get_current_admin),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Проверка конкретного бейджа для пользователя (только для админов)"""
	from app.services.badge_progress import check_badge_completion
	
	# Проверяем существование бейджа
	badge_result = await db.execute(
		select(BadgeModel).where(BadgeModel.id == badge_id)
	)
	badge = badge_result.scalars().first()
	
	if not badge:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Badge not found"
		)
	
	# Проверяем существование пользователя
	user_result = await db.execute(
		select(User).where(User.id == user_id)
	)
	user = user_result.scalars().first()
	
	if not user:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="User not found"
		)
	
	# Проверяем выполнение условия
	is_completed = await check_badge_completion(user_id, badge_id, db)
	
	return {
		"user_id": str(user_id),
		"badge_id": str(badge_id),
		"is_completed": is_completed
	}

