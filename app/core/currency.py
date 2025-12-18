"""
Модуль для работы с валютой пользователей.

Функции для начисления и списания валюты с атомарными операциями.
"""
from typing import Dict
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import logging

from app.models.user import User

logger = logging.getLogger(__name__)


async def add_currency(
	db: AsyncSession,
	user_id: UUID,
	amount: int
) -> Dict:
	"""
	Атомарно начисляет валюту пользователю.
	
	Использует SELECT FOR UPDATE для блокировки строки пользователя и предотвращения
	race conditions при одновременном начислении валюты.
	
	Args:
		db: Асинхронная сессия базы данных
		user_id: UUID пользователя
		amount: Количество валюты для начисления (должно быть положительным)
		
	Returns:
		Словарь с информацией о результате начисления:
		- balance: новый баланс пользователя
		- amount_added: начисленное количество валюты
		- old_balance: баланс до начисления
		
	Raises:
		ValueError: Если пользователь не найден или amount <= 0
	"""
	if amount <= 0:
		raise ValueError("Amount must be positive")
	
	# Блокируем строку пользователя для атомарной операции
	result = await db.execute(
		select(User)
		.where(User.id == user_id)
		.with_for_update()
	)
	user = result.scalar_one_or_none()
	
	if not user:
		raise ValueError(f"User with id {user_id} not found")
	
	old_balance = user.balance
	
	# Начисляем валюту
	new_balance = user.balance + amount
	user.balance = new_balance
	
	await db.commit()
	await db.refresh(user)
	
	# Обновляем счетчик накопленной валюты и прогресс баджиков
	# Импорты внутри функции для избежания циклического импорта
	try:
		from app.services.user_counters import increment_counter
		from app.services.badge_progress import update_progress
		
		await increment_counter(user_id, "currency_accumulated", amount, db)
		await update_progress("currency_accumulated", user_id, amount, db)
	except Exception as e:
		# Логируем ошибку, но не прерываем выполнение основной операции
		logger.error(f"Failed to update currency_accumulated counter or badge progress for user {user_id}: {e}", exc_info=True)
	
	return {
		"balance": new_balance,
		"amount_added": amount,
		"old_balance": old_balance
	}


async def deduct_currency(
	db: AsyncSession,
	user_id: UUID,
	amount: int
) -> Dict:
	"""
	Атомарно списывает валюту с пользователя с проверкой достаточности средств.
	
	Использует SELECT FOR UPDATE для блокировки строки пользователя и предотвращения
	race conditions при одновременном списании валюты.
	
	Args:
		db: Асинхронная сессия базы данных
		user_id: UUID пользователя
		amount: Количество валюты для списания (должно быть положительным)
		
	Returns:
		Словарь с информацией о результате списания:
		- balance: новый баланс пользователя
		- amount_deducted: списанное количество валюты
		- old_balance: баланс до списания
		
	Raises:
		ValueError: Если пользователь не найден, amount <= 0 или недостаточно средств
	"""
	if amount <= 0:
		raise ValueError("Amount must be positive")
	
	# Блокируем строку пользователя для атомарной операции
	result = await db.execute(
		select(User)
		.where(User.id == user_id)
		.with_for_update()
	)
	user = result.scalar_one_or_none()
	
	if not user:
		raise ValueError(f"User with id {user_id} not found")
	
	old_balance = user.balance
	
	# Проверяем достаточность средств
	if user.balance < amount:
		raise ValueError("Insufficient funds")
	
	# Списываем валюту
	new_balance = user.balance - amount
	user.balance = new_balance
	
	await db.commit()
	await db.refresh(user)
	
	return {
		"balance": new_balance,
		"amount_deducted": amount,
		"old_balance": old_balance
	}

