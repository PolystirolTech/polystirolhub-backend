from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from typing import Tuple, Optional
import logging

from app.models.game_server import GameServer
from app.models.resource_collection import ResourceProgress
from app.models.statistics import MinecraftServer as MinecraftServerModel
from app.schemas.resource_collection import ResourceCollectionRequest

logger = logging.getLogger(__name__)


async def validate_server_uuid(db: AsyncSession, server_uuid: str) -> Optional[GameServer]:
	"""Валидирует server_uuid и возвращает GameServer если найден"""
	# Проверяем наличие minecraft_server с таким server_uuid
	result = await db.execute(
		select(MinecraftServerModel)
		.options(selectinload(MinecraftServerModel.game_server))
		.join(GameServer, MinecraftServerModel.game_server_id == GameServer.id)
		.where(MinecraftServerModel.server_uuid == server_uuid)
	)
	mc_server = result.scalar_one_or_none()
	
	if mc_server:
		return mc_server.game_server
	
	# Если minecraft_server не найден, ищем game_server по UUID
	# (на случай если сервер еще не был зарегистрирован в статистике)
	result = await db.execute(
		select(GameServer).where(GameServer.id == server_uuid)
	)
	game_server = result.scalar_one_or_none()
	
	return game_server


async def process_resource_collection(
	db: AsyncSession,
	request: ResourceCollectionRequest
) -> Tuple[bool, int, Optional[str]]:
	"""
	Обрабатывает запрос от мода на обновление прогресса сбора ресурсов.
	
	Args:
		db: Сессия БД
		request: Запрос с данными о собранных ресурсах
		
	Returns:
		Tuple[success, current_amount, error_message]
	"""
	try:
		# Валидируем server_uuid
		game_server = await validate_server_uuid(db, request.server_uuid)
		
		if not game_server:
			return False, 0, f"Server with UUID {request.server_uuid} not found"
		
		# Получаем или создаем запись прогресса
		result = await db.execute(
			select(ResourceProgress).where(
				and_(
					ResourceProgress.server_id == game_server.id,
					ResourceProgress.resource_type == request.resource_type
				)
			)
		)
		progress = result.scalar_one_or_none()
		
		if progress:
			# Обновляем существующий прогресс (инкремент)
			progress.current_amount += request.amount
		else:
			# Создаем новую запись прогресса
			progress = ResourceProgress(
				server_id=game_server.id,
				resource_type=request.resource_type,
				current_amount=request.amount
			)
			db.add(progress)
		
		await db.commit()
		await db.refresh(progress)
		
		logger.info(
			f"Resource collection updated: server_id={game_server.id}, "
			f"resource_type={request.resource_type}, "
			f"amount={request.amount}, "
			f"current_amount={progress.current_amount}"
		)
		
		return True, progress.current_amount, None
		
	except Exception as e:
		await db.rollback()
		logger.error(f"Error processing resource collection: {str(e)}", exc_info=True)
		return False, 0, str(e)

