from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import Optional
from app.api import deps
from app.models.user import User
from app.models.game_server import GameType, GameServer, ServerStatus, ServerWhitelistEntry, WhitelistStatus
from app.schemas.game_server import (
	GameTypeCreate,
	GameTypeUpdate,
	GameTypeResponse,
	GameServerResponse,
	GameServerPublic,
	ServerStatusResponse,
	WhitelistApplyRequest,
	WhitelistApplyResponse,
	WhitelistEntryResponse,
	WhitelistAdminAddRequest,
	WhitelistIngestResponse,
	WhitelistStatusResponse,
)
from app.services.server_status import get_server_status
from app.core.storage import get_banners_storage
from app.core.config import settings
from uuid import UUID
from datetime import date, datetime, timezone
import logging
import uuid
import json
import re

logger = logging.getLogger(__name__)

router = APIRouter()

def parse_and_validate_mods(mods_json: str) -> list[str]:
	"""
	Парсит и валидирует моды в формате JSON массива.
	Каждый элемент должен быть в формате "название: ссылка".
	"""
	try:
		mods_list = json.loads(mods_json) if mods_json else []
		if not isinstance(mods_list, list):
			raise ValueError("mods must be a list")
		
		# Валидируем формат каждого мода
		mod_pattern = re.compile(r'^.+:\s*.+$')
		for i, mod in enumerate(mods_list):
			if not isinstance(mod, str):
				raise ValueError(f"mod at index {i} must be a string")
			if not mod_pattern.match(mod.strip()):
				raise ValueError(
					f"mod at index {i} must be in format 'название: ссылка', got: '{mod}'"
				)
		
		# Нормализуем формат (убираем лишние пробелы, но сохраняем структуру)
		normalized_mods = [mod.strip() for mod in mods_list if mod.strip()]
		
		return normalized_mods
	except json.JSONDecodeError as e:
		raise ValueError(f"mods must be a valid JSON array: {e}")
	except ValueError as e:
		raise e

def parse_date(date_str: Optional[str]) -> Optional[date]:
	"""
	Парсит строку даты в формате YYYY-MM-DD в объект date.
	Возвращает None если строка пустая или None.
	"""
	if not date_str:
		return None
	try:
		return date.fromisoformat(date_str)
	except ValueError:
		raise ValueError(f"Invalid date format. Expected YYYY-MM-DD, got: {date_str}")

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
		.where(GameServer.status != ServerStatus.disabled)
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
	
	# Не отображаем серверы со статусом disabled
	if server.status == ServerStatus.disabled:
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
		.options(selectinload(GameServer.game_type))
		.where(GameServer.id == server_id)
	)
	server = result.scalars().first()
	
	if not server:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Game server not found"
		)
	
	# Не отображаем статус для серверов со статусом disabled
	if server.status == ServerStatus.disabled:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Game server not found"
		)
	
	# Получаем статус через сервис (с кэшированием), передаем статус сервера и название типа игры
	status_data = await get_server_status(server.id, server.ip, server.port, server.status, server.game_type.name)
	
	return ServerStatusResponse(**status_data)


# ========== Вайтлист: публичная заявка ==========

@router.post("/game-servers/{server_id}/whitelist/apply", response_model=WhitelistApplyResponse, status_code=status.HTTP_201_CREATED)
async def apply_whitelist(
	server_id: UUID,
	body: WhitelistApplyRequest,
	current_user: User = Depends(deps.get_current_user),
	db: AsyncSession = Depends(deps.get_db),
):
	"""Подать заявку в вайтлист сервера. Только для авторизованных пользователей."""
	result = await db.execute(
		select(GameServer).where(GameServer.id == server_id)
	)
	server = result.scalar()
	if not server:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game server not found")
	if server.status == ServerStatus.disabled:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game server not found")
	if not server.is_whitelist:
		raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This server does not use whitelist")
	nickname = (body.nickname or "").strip()
	if not nickname or len(nickname) > 255:
		raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="nickname is required and must be up to 255 characters")
	# Один ник на сервер
	existing = await db.execute(
		select(ServerWhitelistEntry).where(
			ServerWhitelistEntry.server_id == server_id,
			ServerWhitelistEntry.nickname == nickname,
		)
	)
	existing_entry = existing.scalar()
	if existing_entry:
		if existing_entry.status == WhitelistStatus.pending:
			return WhitelistApplyResponse(message="Заявка уже подана и ожидает рассмотрения", entry_id=existing_entry.id, status=existing_entry.status)
		if existing_entry.status == WhitelistStatus.approved:
			raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This nickname is already on the whitelist")
		# rejected — переоткрываем заявку
		existing_entry.status = WhitelistStatus.pending
		existing_entry.user_id = current_user.id
		existing_entry.reviewed_at = None
		existing_entry.reviewed_by_id = None
		await db.commit()
		await db.refresh(existing_entry)
		return WhitelistApplyResponse(message="Заявка отправлена на рассмотрение", entry_id=existing_entry.id, status=existing_entry.status)
	entry = ServerWhitelistEntry(
		server_id=server_id,
		user_id=current_user.id,
		nickname=nickname,
		status=WhitelistStatus.pending,
	)
	db.add(entry)
	await db.commit()
	await db.refresh(entry)
	return WhitelistApplyResponse(message="Заявка отправлена на рассмотрение", entry_id=entry.id, status=entry.status)


@router.get("/game-servers/{server_id}/whitelist/my-status", response_model=WhitelistStatusResponse)
async def get_my_whitelist_status(
	server_id: UUID,
	current_user: User = Depends(deps.get_current_user),
	db: AsyncSession = Depends(deps.get_db),
):
	"""Получить статус моей заявки в вайтлист на этом сервере."""
	# Ищем заявку пользователя
	result = await db.execute(
		select(ServerWhitelistEntry).where(
			ServerWhitelistEntry.server_id == server_id,
			ServerWhitelistEntry.user_id == current_user.id
		)
	)
	entry = result.scalar()
	
	if not entry:
		# Если заявки по user_id нет, попробуем найти по нику из привязанного MC аккаунта (если есть)
		# Это нужно, если админ добавил вручную по нику, но не привязал к user_id
		# Или если заявка была подана анонимно (хотя сейчас мы требуем авторизацию для apply, но вдруг)
		# Но пока реализуем только прямой поиск по user_id, так как apply теперь всегда пишет user_id
		return WhitelistStatusResponse(status=None)
	
	return WhitelistStatusResponse(
		status=entry.status,
		entry_id=entry.id,
		created_at=entry.created_at,
		reviewed_at=entry.reviewed_at
	)


# ========== Вайтлист: ingest для модов (X-Ingest-Token) ==========

@router.get("/game-servers/{server_id}/whitelist", response_model=WhitelistIngestResponse, dependencies=[Depends(deps.verify_ingest_token)])
async def get_whitelist_ingest(
	server_id: UUID,
	db: AsyncSession = Depends(deps.get_db),
):
	"""Список одобренных ников вайтлиста для сервера. Только с заголовком X-Ingest-Token (для модов)."""
	result = await db.execute(
		select(ServerWhitelistEntry).where(
			ServerWhitelistEntry.server_id == server_id,
			ServerWhitelistEntry.status == WhitelistStatus.approved,
		)
	)
	entries = result.scalars().all()
	return WhitelistIngestResponse(nicknames=[e.nickname for e in entries])


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
	server_status: Optional[str] = Form(None),
	season_start: Optional[str] = Form(None),
	season_end: Optional[str] = Form(None),
	is_whitelist: bool = Form(False),
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
	
	# Парсим и валидируем моды из JSON строки
	try:
		mods_list = parse_and_validate_mods(mods)
	except ValueError as e:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail=str(e)
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
	
	# Парсим статус если передан
	server_status_enum = ServerStatus.active
	if server_status is not None:
		try:
			server_status_enum = ServerStatus(server_status)
		except ValueError:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail=f"Invalid server_status. Must be one of: {', '.join([s.value for s in ServerStatus])}"
			)
	
	# Парсим даты сезона если переданы
	parsed_season_start = None
	parsed_season_end = None
	if season_start is not None:
		try:
			parsed_season_start = parse_date(season_start)
		except ValueError as e:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail=str(e)
			)
	if season_end is not None:
		try:
			parsed_season_end = parse_date(season_end)
		except ValueError as e:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail=str(e)
			)
	
	# Создаем сервер
	new_server = GameServer(
		name=name,
		game_type_id=game_type_id,
		description=description,
		mods=mods_list,
		ip=ip,
		port=port,
		banner_url=banner_url,
		status=server_status_enum,
		season_start=parsed_season_start,
		season_end=parsed_season_end,
		is_whitelist=is_whitelist,
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
	server_status: Optional[str] = Form(None),
	season_start: Optional[str] = Form(None),
	season_end: Optional[str] = Form(None),
	is_whitelist: Optional[bool] = Form(None),
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
			mods_list = parse_and_validate_mods(mods)
		except ValueError as e:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail=str(e)
			)
		server.mods = mods_list
	
	if ip is not None:
		server.ip = ip
	
	if port is not None:
		server.port = port
	
	# Обновляем статус если передан
	old_status = server.status
	if server_status is not None:
		try:
			server_status_enum = ServerStatus(server_status)
			server.status = server_status_enum
		except ValueError:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail=f"Invalid server_status. Must be one of: {', '.join([s.value for s in ServerStatus])}"
			)
	
	# Обновляем даты сезона если переданы
	if season_start is not None:
		try:
			server.season_start = parse_date(season_start)
		except ValueError as e:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail=str(e)
			)
	if season_end is not None:
		try:
			server.season_end = parse_date(season_end)
		except ValueError as e:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail=str(e)
			)
	
	if is_whitelist is not None:
		server.is_whitelist = is_whitelist
	
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
	
	# Создаем событие активности если статус изменился
	if server_status is not None and old_status != server.status:
		try:
			from app.services.activity import create_activity
			from app.models.activity import ActivityType
			status_names = {
				ServerStatus.active: "работает",
				ServerStatus.disabled: "выключен",
				ServerStatus.maintenance: "на обслуживании"
			}
			await create_activity(
				db=db,
				activity_type=ActivityType.server_status_changed,
				title=f"Статус сервера {server.name} изменился",
				description=f"Сервер теперь {status_names.get(server.status, server.status.value)}",
				server_id=server.id,
				meta_data={
					"server_id": str(server.id),
					"server_name": server.name,
					"old_status": old_status.value,
					"new_status": server.status.value
				}
			)
		except Exception as e:
			logger.error(f"Failed to create server_status_changed activity for server {server.id}: {e}", exc_info=True)
	
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


# ========== Админ: вайтлист ==========

@router.get("/admin/whitelist/pending", response_model=list[WhitelistEntryResponse])
async def admin_whitelist_pending(
	current_user: User = Depends(deps.get_current_admin),
	db: AsyncSession = Depends(deps.get_db),
	server_id: Optional[UUID] = Query(None, description="Фильтр по серверу"),
):
	"""Список заявок в вайтлист со статусом pending. Опционально фильтр по server_id."""
	q = (
		select(ServerWhitelistEntry)
		.where(ServerWhitelistEntry.status == WhitelistStatus.pending)
		.order_by(ServerWhitelistEntry.created_at.desc())
	)
	if server_id is not None:
		q = q.where(ServerWhitelistEntry.server_id == server_id)
	result = await db.execute(q)
	entries = result.scalars().all()
	return entries


@router.get("/admin/whitelist/approved", response_model=list[WhitelistEntryResponse])
async def admin_whitelist_approved(
	current_user: User = Depends(deps.get_current_admin),
	db: AsyncSession = Depends(deps.get_db),
	server_id: Optional[UUID] = Query(None, description="Фильтр по серверу"),
):
	"""Список одобренных записей вайтлиста (status=approved). Опционально фильтр по server_id."""
	q = (
		select(ServerWhitelistEntry)
		.where(ServerWhitelistEntry.status == WhitelistStatus.approved)
		.order_by(ServerWhitelistEntry.created_at.desc())
	)
	if server_id is not None:
		q = q.where(ServerWhitelistEntry.server_id == server_id)
	result = await db.execute(q)
	entries = result.scalars().all()
	return entries


@router.post("/admin/whitelist/entries/{entry_id}/approve")
async def admin_whitelist_approve(
	entry_id: UUID,
	current_user: User = Depends(deps.get_current_admin),
	db: AsyncSession = Depends(deps.get_db),
):
	"""Принять заявку в вайтлист."""
	result = await db.execute(select(ServerWhitelistEntry).where(ServerWhitelistEntry.id == entry_id))
	entry = result.scalar()
	if not entry:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Whitelist entry not found")
	if entry.status != WhitelistStatus.pending:
		raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Entry is not pending")
	entry.status = WhitelistStatus.approved
	entry.reviewed_at = datetime.now(timezone.utc)
	entry.reviewed_by_id = current_user.id
	await db.commit()
	return {"message": "Approved", "entry_id": str(entry_id)}


@router.post("/admin/whitelist/entries/{entry_id}/reject")
async def admin_whitelist_reject(
	entry_id: UUID,
	current_user: User = Depends(deps.get_current_admin),
	db: AsyncSession = Depends(deps.get_db),
):
	"""Отклонить заявку в вайтлист."""
	result = await db.execute(select(ServerWhitelistEntry).where(ServerWhitelistEntry.id == entry_id))
	entry = result.scalar()
	if not entry:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Whitelist entry not found")
	# Можно отклонять и уже принятые (удаление из вайтлиста)
	entry.status = WhitelistStatus.rejected
	entry.reviewed_at = datetime.now(timezone.utc)
	entry.reviewed_by_id = current_user.id
	await db.commit()
	return {"message": "Rejected", "entry_id": str(entry_id)}


@router.delete("/admin/whitelist/entries/{entry_id}")
async def admin_whitelist_delete(
	entry_id: UUID,
	current_user: User = Depends(deps.get_current_admin),
	db: AsyncSession = Depends(deps.get_db),
):
	"""Удалить запись из вайтлиста (полное удаление)."""
	result = await db.execute(select(ServerWhitelistEntry).where(ServerWhitelistEntry.id == entry_id))
	entry = result.scalar()
	if not entry:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Whitelist entry not found")
	await db.delete(entry)
	await db.commit()
	return {"message": "Deleted", "entry_id": str(entry_id)}


@router.post("/admin/whitelist/add", response_model=WhitelistEntryResponse, status_code=status.HTTP_201_CREATED)
async def admin_whitelist_add(
	body: WhitelistAdminAddRequest,
	current_user: User = Depends(deps.get_current_admin),
	db: AsyncSession = Depends(deps.get_db),
):
	"""Добавить пользователя/ник в вайтлист сервера без заявки (сразу approved)."""
	result = await db.execute(select(GameServer).where(GameServer.id == body.server_id))
	server = result.scalar()
	if not server:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game server not found")
	nickname = (body.nickname or "").strip()
	if not nickname or len(nickname) > 255:
		raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="nickname is required and up to 255 characters")
	existing = await db.execute(
		select(ServerWhitelistEntry).where(
			ServerWhitelistEntry.server_id == body.server_id,
			ServerWhitelistEntry.nickname == nickname,
		)
	)
	if existing.scalar():
		raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This nickname is already in whitelist or has a pending request")
	entry = ServerWhitelistEntry(
		server_id=body.server_id,
		user_id=body.user_id,
		nickname=nickname,
		status=WhitelistStatus.approved,
		reviewed_at=datetime.now(timezone.utc),
		reviewed_by_id=current_user.id,
	)
	db.add(entry)
	await db.commit()
	await db.refresh(entry)
	return entry
