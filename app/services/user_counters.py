"""
Сервис для работы со счетчиками пользователя (Minecraft статистика).
"""
from typing import Dict
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.dialects.postgresql import insert
import logging

from app.models.user import UserCounter

logger = logging.getLogger(__name__)


async def increment_counter(
	user_id: UUID,
	counter_key: str,
	amount: int,
	db: AsyncSession
) -> None:
	"""
	Увеличивает значение счетчика на указанное количество.
	
	Args:
		user_id: UUID пользователя
		counter_key: Ключ счетчика (например, "blocks_traveled", "messages_sent")
		amount: Количество для увеличения
		db: Асинхронная сессия базы данных
	"""
	if amount <= 0:
		return
	
	try:
		# Используем upsert для атомарного обновления
		stmt = insert(UserCounter).values(
			user_id=user_id,
			counter_key=counter_key,
			value=amount
		)
		stmt = stmt.on_conflict_do_update(
			index_elements=['user_id', 'counter_key'],
			set_={
				'value': UserCounter.value + amount,
				'updated_at': func.now()
			}
		)
		await db.execute(stmt)
		await db.flush()
		logger.debug(f"Incremented counter {counter_key} for user {user_id} by {amount}")
	except Exception as e:
		logger.error(f"Error incrementing counter {counter_key} for user {user_id}: {e}", exc_info=True)
		raise


async def set_counter(
	user_id: UUID,
	counter_key: str,
	value: int,
	db: AsyncSession
) -> None:
	"""
	Устанавливает абсолютное значение счетчика.
	
	Args:
		user_id: UUID пользователя
		counter_key: Ключ счетчика
		value: Абсолютное значение для установки
		db: Асинхронная сессия базы данных
	"""
	try:
		stmt = insert(UserCounter).values(
			user_id=user_id,
			counter_key=counter_key,
			value=value
		)
		stmt = stmt.on_conflict_do_update(
			index_elements=['user_id', 'counter_key'],
			set_={
				'value': stmt.excluded.value,
				'updated_at': func.now()
			}
		)
		await db.execute(stmt)
		await db.flush()
		logger.debug(f"Set counter {counter_key} for user {user_id} to {value}")
	except Exception as e:
		logger.error(f"Error setting counter {counter_key} for user {user_id}: {e}", exc_info=True)
		raise


async def get_counter(
	user_id: UUID,
	counter_key: str,
	db: AsyncSession
) -> int:
	"""
	Получает значение счетчика.
	
	Args:
		user_id: UUID пользователя
		counter_key: Ключ счетчика
		db: Асинхронная сессия базы данных
		
	Returns:
		Значение счетчика (0 если не существует)
	"""
	try:
		result = await db.execute(
			select(UserCounter.value).where(
				and_(
					UserCounter.user_id == user_id,
					UserCounter.counter_key == counter_key
				)
			)
		)
		counter = result.scalar_one_or_none()
		return counter if counter is not None else 0
	except Exception as e:
		logger.error(f"Error getting counter {counter_key} for user {user_id}: {e}", exc_info=True)
		return 0


async def get_all_counters(
	user_id: UUID,
	db: AsyncSession
) -> Dict[str, int]:
	"""
	Получает все счетчики пользователя.
	
	Args:
		user_id: UUID пользователя
		db: Асинхронная сессия базы данных
		
	Returns:
		Словарь счетчиков: ключ -> значение
	"""
	try:
		result = await db.execute(
			select(UserCounter.counter_key, UserCounter.value).where(
				UserCounter.user_id == user_id
			)
		)
		counters = {row[0]: row[1] for row in result.all()}
		return counters
	except Exception as e:
		logger.error(f"Error getting all counters for user {user_id}: {e}", exc_info=True)
		return {}
