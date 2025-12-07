from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import Optional
from app.api import deps
from app.models.user import User
from app.models.game_server import GameType, GameServer
from app.schemas.game_server import (
	GameTypeCreate,
	GameTypeUpdate,
	GameTypeResponse,
	GameServerResponse,
	GameServerPublic,
	ServerStatusResponse
)
from app.services.server_status import get_server_status
from app.core.storage import get_banners_storage
from app.core.config import settings
from uuid import UUID
import logging
import uuid
import json

logger = logging.getLogger(__name__)

router = APIRouter()

# ========== Публичные эндпоинты ==========

@router.get("/game-types", response_model=list[GameTypeResponse])
async def get_game_types(
	db: AsyncSession = Depends(deps.get_db)
):
	"""Публичный список типов игр"""
	result = await db.execute(select(GameType).order_by(GameType.name))
	game_types = result.scalars().all()
	return game_types

@router.get("/game-servers", response_model=list[GameServerPublic])
async def get_game_servers(
	db: AsyncSession = Depends(deps.get_db)
):
	"""Публичный список игровых серверов"""
	result = await db.execute(
		select(GameServer)
		.options(selectinload(GameServer.game_type))
		.order_by(GameServer.created_at.desc())
	)
	servers = result.scalars().all()
	return servers

@router.get("/game-servers/{server_id}", response_model=GameServerPublic)
async def get_game_server(
	server_id: UUID,
	db: AsyncSession = Depends(deps.get_db)
):
	"""Публичное получение игрового сервера"""
	result = await db.execute(
		select(GameServer)
		.options(selectinload(GameServer.game_type))
		.where(GameServer.id == server_id)
	)
	server = result.scalars().first()
	
	if not server:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Game server not found"
		)
	
	return server

@router.get("/game-servers/{server_id}/status", response_model=ServerStatusResponse)
async def get_game_server_status(
	server_id: UUID,
	db: AsyncSession = Depends(deps.get_db)
):
	"""Получение статуса игрового сервера (icon, motd, players, ping)"""
	result = await db.execute(
		select(GameServer)
		.where(GameServer.id == server_id)
	)
	server = result.scalars().first()
	
	if not server:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Game server not found"
		)
	
	# Получаем статус через сервис (с кэшированием)
	status_data = await get_server_status(server.id, server.ip, server.port)
	
	return ServerStatusResponse(**status_data)

# ========== Админские эндпоинты для типов игр ==========

@router.post("/admin/game-types", response_model=GameTypeResponse)
async def create_game_type(
	game_type: GameTypeCreate,
	current_user: User = Depends(deps.get_current_admin),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Создание типа игры. Только для админов."""
	# Проверяем, существует ли уже тип с таким именем
	result = await db.execute(select(GameType).where(GameType.name == game_type.name))
	existing = result.scalars().first()
	
	if existing:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Game type with this name already exists"
		)
	
	new_game_type = GameType(name=game_type.name)
	db.add(new_game_type)
	await db.commit()
	await db.refresh(new_game_type)
	
	return new_game_type

@router.get("/admin/game-types", response_model=list[GameTypeResponse])
async def list_game_types(
	current_user: User = Depends(deps.get_current_admin),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Список типов игр. Только для админов."""
	result = await db.execute(select(GameType).order_by(GameType.name))
	game_types = result.scalars().all()
	return game_types

@router.put("/admin/game-types/{type_id}", response_model=GameTypeResponse)
async def update_game_type(
	type_id: UUID,
	game_type_update: GameTypeUpdate,
	current_user: User = Depends(deps.get_current_admin),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Обновление типа игры. Только для админов."""
	result = await db.execute(select(GameType).where(GameType.id == type_id))
	game_type = result.scalars().first()
	
	if not game_type:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Game type not found"
		)
	
	update_data = game_type_update.model_dump(exclude_unset=True)
	
	# Если обновляется имя, проверяем на уникальность
	if "name" in update_data and update_data["name"] != game_type.name:
		result = await db.execute(select(GameType).where(GameType.name == update_data["name"]))
		existing = result.scalars().first()
		if existing:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="Game type with this name already exists"
			)
		game_type.name = update_data["name"]
	
	await db.commit()
	await db.refresh(game_type)
	
	return game_type

@router.delete("/admin/game-types/{type_id}")
async def delete_game_type(
	type_id: UUID,
	current_user: User = Depends(deps.get_current_admin),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Удаление типа игры. Только для админов."""
	result = await db.execute(select(GameType).where(GameType.id == type_id))
	game_type = result.scalars().first()
	
	if not game_type:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Game type not found"
		)
	
	# Проверяем, нет ли серверов с этим типом
	result = await db.execute(select(GameServer).where(GameServer.game_type_id == type_id))
	servers = result.scalars().all()
	
	if servers:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail=f"Cannot delete game type. {len(servers)} server(s) are using this type"
		)
	
	await db.delete(game_type)
	await db.commit()
	
	return {"message": "Game type deleted successfully"}

# ========== Админские эндпоинты для игровых серверов ==========

@router.post("/admin/game-servers", response_model=GameServerResponse)
async def create_game_server(
	name: str = Form(...),
	game_type_id: UUID = Form(...),
	description: str = Form(None),
	mods: str = Form("[]"),  # JSON строка массива
	ip: str = Form(...),
	port: Optional[int] = Form(None),
	banner: UploadFile = File(None),
	current_user: User = Depends(deps.get_current_admin),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Создание игрового сервера с возможной загрузкой баннера. Только для админов."""
	# Проверяем, существует ли тип игры
	result = await db.execute(select(GameType).where(GameType.id == game_type_id))
	game_type = result.scalars().first()
	
	if not game_type:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Game type not found"
		)
	
	# Парсим моды из JSON строки
	try:
		mods_list = json.loads(mods) if mods else []
		if not isinstance(mods_list, list):
			raise ValueError("mods must be a list")
	except (json.JSONDecodeError, ValueError):
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="mods must be a valid JSON array"
		)
	
	# Обрабатываем баннер если загружен
	banner_url = None
	if banner:
		# Валидация типа файла
		allowed_content_types = ["image/jpeg", "image/png", "image/webp"]
		if banner.content_type not in allowed_content_types:
			raise HTTPException(
				status_code=400,
				detail=f"Invalid file type. Allowed types: {', '.join(allowed_content_types)}"
			)
		
		# Валидация размера файла (5MB)
		MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
		file_content = await banner.read()
		if len(file_content) > MAX_FILE_SIZE:
			raise HTTPException(
				status_code=400,
				detail=f"File too large. Maximum size is {MAX_FILE_SIZE / 1024 / 1024}MB"
			)
		
		# Определяем расширение файла
		content_type_to_ext = {
			"image/jpeg": "jpg",
			"image/png": "png",
			"image/webp": "webp"
		}
		file_ext = content_type_to_ext.get(banner.content_type, "jpg")
		
		# Генерируем уникальное имя файла
		file_id = str(uuid.uuid4())
		file_name = f"{file_id}.{file_ext}"
		
		# Сохраняем файл
		storage = get_banners_storage()
		banner_url = await storage.save(file_content, file_name)
	
	# Создаем сервер
	new_server = GameServer(
		name=name,
		game_type_id=game_type_id,
		description=description,
		mods=mods_list,
		ip=ip,
		port=port,
		banner_url=banner_url
	)
	
	db.add(new_server)
	await db.commit()
	await db.refresh(new_server)
	
	# Загружаем связь с типом игры
	result = await db.execute(
		select(GameServer)
		.options(selectinload(GameServer.game_type))
		.where(GameServer.id == new_server.id)
	)
	server = result.scalars().first()
	
	return server

@router.get("/admin/game-servers", response_model=list[GameServerResponse])
async def list_game_servers(
	current_user: User = Depends(deps.get_current_admin),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Список игровых серверов. Только для админов."""
	result = await db.execute(
		select(GameServer)
		.options(selectinload(GameServer.game_type))
		.order_by(GameServer.created_at.desc())
	)
	servers = result.scalars().all()
	return servers

@router.get("/admin/game-servers/{server_id}", response_model=GameServerResponse)
async def get_game_server_admin(
	server_id: UUID,
	current_user: User = Depends(deps.get_current_admin),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Получение игрового сервера. Только для админов."""
	result = await db.execute(
		select(GameServer)
		.options(selectinload(GameServer.game_type))
		.where(GameServer.id == server_id)
	)
	server = result.scalars().first()
	
	if not server:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Game server not found"
		)
	
	return server

@router.put("/admin/game-servers/{server_id}", response_model=GameServerResponse)
async def update_game_server(
	server_id: UUID,
	name: str = Form(None),
	game_type_id: str = Form(None),
	description: str = Form(None),
	mods: str = Form(None),
	ip: str = Form(None),
	port: Optional[int] = Form(None),
	banner: UploadFile = File(None),
	current_user: User = Depends(deps.get_current_admin),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Обновление игрового сервера с возможной загрузкой баннера. Только для админов."""
	result = await db.execute(
		select(GameServer)
		.options(selectinload(GameServer.game_type))
		.where(GameServer.id == server_id)
	)
	server = result.scalars().first()
	
	if not server:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Game server not found"
		)
	
	# Обновляем поля если они переданы
	if name is not None:
		server.name = name
	
	if game_type_id is not None:
		try:
			game_type_uuid = UUID(game_type_id)
		except ValueError:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="Invalid game_type_id format"
			)
		result = await db.execute(select(GameType).where(GameType.id == game_type_uuid))
		game_type = result.scalars().first()
		if not game_type:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="Game type not found"
			)
		server.game_type_id = game_type_uuid
	
	if description is not None:
		server.description = description
	
	if mods is not None:
		try:
			mods_list = json.loads(mods) if mods else []
			if not isinstance(mods_list, list):
				raise ValueError("mods must be a list")
		except (json.JSONDecodeError, ValueError):
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="mods must be a valid JSON array"
			)
		server.mods = mods_list
	
	if ip is not None:
		server.ip = ip
	
	if port is not None:
		server.port = port
	
	# Обрабатываем новый баннер если загружен
	if banner:
		# Валидация типа файла
		allowed_content_types = ["image/jpeg", "image/png", "image/webp"]
		if banner.content_type not in allowed_content_types:
			raise HTTPException(
				status_code=400,
				detail=f"Invalid file type. Allowed types: {', '.join(allowed_content_types)}"
			)
		
		# Валидация размера файла (5MB)
		MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
		file_content = await banner.read()
		if len(file_content) > MAX_FILE_SIZE:
			raise HTTPException(
				status_code=400,
				detail=f"File too large. Maximum size is {MAX_FILE_SIZE / 1024 / 1024}MB"
			)
		
		# Определяем расширение файла
		content_type_to_ext = {
			"image/jpeg": "jpg",
			"image/png": "png",
			"image/webp": "webp"
		}
		file_ext = content_type_to_ext.get(banner.content_type, "jpg")
		
		# Удаляем старый баннер если он существует
		if server.banner_url:
			old_banner = server.banner_url
			banners_base_url = settings.STORAGE_BANNERS_BASE_URL
			full_base_url = f"{settings.BACKEND_BASE_URL}{banners_base_url}"
			
			if old_banner.startswith(full_base_url) or old_banner.startswith(banners_base_url):
				old_path = old_banner.replace(full_base_url, "").replace(banners_base_url, "").lstrip("/")
				try:
					storage = get_banners_storage()
					await storage.delete(old_path)
				except Exception as e:
					logger.warning(f"Failed to delete old banner {old_path}: {e}")
		
		# Генерируем уникальное имя файла
		file_id = str(uuid.uuid4())
		file_name = f"{file_id}.{file_ext}"
		
		# Сохраняем новый файл
		storage = get_banners_storage()
		server.banner_url = await storage.save(file_content, file_name)
	
	await db.commit()
	await db.refresh(server)
	
	# Загружаем связь с типом игры
	result = await db.execute(
		select(GameServer)
		.options(selectinload(GameServer.game_type))
		.where(GameServer.id == server.id)
	)
	updated_server = result.scalars().first()
	
	return updated_server

@router.delete("/admin/game-servers/{server_id}")
async def delete_game_server(
	server_id: UUID,
	current_user: User = Depends(deps.get_current_admin),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Удаление игрового сервера. Только для админов."""
	result = await db.execute(select(GameServer).where(GameServer.id == server_id))
	server = result.scalars().first()
	
	if not server:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Game server not found"
		)
	
	# Удаляем баннер если он существует
	if server.banner_url:
		banners_base_url = settings.STORAGE_BANNERS_BASE_URL
		full_base_url = f"{settings.BACKEND_BASE_URL}{banners_base_url}"
		
		if server.banner_url.startswith(full_base_url) or server.banner_url.startswith(banners_base_url):
			old_path = server.banner_url.replace(full_base_url, "").replace(banners_base_url, "").lstrip("/")
			try:
				storage = get_banners_storage()
				await storage.delete(old_path)
			except Exception as e:
				logger.warning(f"Failed to delete banner {old_path}: {e}")
	
	await db.delete(server)
	await db.commit()
	
	return {"message": "Game server deleted successfully"}
