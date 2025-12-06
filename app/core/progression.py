"""
Модуль для расчета и начисления опыта (XP) и уровней пользователей.

Формулы:
- E(L) = ⌈L/10⌉ × 100 XP - дополнительный опыт для перехода от уровня L-1 к уровню L
- TotalXP(N) = Σ(L=1 to N) E(L) - общий опыт, требуемый для достижения уровня N
"""
import math
from typing import Dict
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.user import User


def calculate_e_for_level(level: int) -> int:
	"""
	Рассчитывает дополнительный опыт E(L), необходимый для перехода от уровня L-1 к уровню L.
	
	Формула: E(L) = ⌈L/10⌉ × 100
	
	Args:
		level: Целевой уровень (от 1 до 100+)
		
	Returns:
		Количество XP, необходимое для достижения этого уровня от предыдущего
	"""
	if level < 1:
		return 0
	return math.ceil(level / 10) * 100


def calculate_total_xp_for_level(level: int) -> int:
	"""
	Рассчитывает общий опыт TotalXP(N), требуемый для достижения уровня N.
	
	Формула: TotalXP(N) = Σ(L=1 to N) E(L)
	
	Args:
		level: Целевой уровень
		
	Returns:
		Общее количество XP, необходимое для достижения указанного уровня
	"""
	if level < 1:
		return 0
	
	total_xp = 0
	for i in range(1, level + 1):
		total_xp += calculate_e_for_level(i)
	return total_xp


def calculate_level_from_xp(total_xp: int) -> int:
	"""
	Определяет текущий уровень пользователя на основе общего опыта.
	
	Args:
		total_xp: Общий опыт пользователя
		
	Returns:
		Текущий уровень пользователя
	"""
	if total_xp < 0:
		return 1
	
	level = 1
	while True:
		xp_for_next_level = calculate_total_xp_for_level(level + 1)
		if total_xp < xp_for_next_level:
			return level
		level += 1
		# Защита от бесконечного цикла (максимальный уровень 1000)
		if level > 1000:
			return 1000


def get_progression_info(total_xp: int) -> Dict:
	"""
	Получает информацию о прогрессе пользователя.
	
	Args:
		total_xp: Общий опыт пользователя
		
	Returns:
		Словарь с информацией о прогрессе:
		- level: текущий уровень
		- total_xp: общий опыт
		- xp_for_current_level: XP, требуемый для текущего уровня
		- xp_for_next_level: XP, требуемый для следующего уровня
		- xp_progress: XP, накопленный на текущем уровне (от начала уровня)
		- xp_needed: XP, необходимое для следующего уровня
		- progress_percent: процент прогресса до следующего уровня (0-100)
	"""
	current_level = calculate_level_from_xp(total_xp)
	xp_for_current_level = calculate_total_xp_for_level(current_level)
	xp_for_next_level = calculate_total_xp_for_level(current_level + 1)
	
	xp_progress = total_xp - xp_for_current_level
	xp_needed = xp_for_next_level - total_xp
	e_for_next = calculate_e_for_level(current_level + 1)
	
	if e_for_next > 0:
		progress_percent = (xp_progress / e_for_next) * 100
	else:
		progress_percent = 100.0
	
	return {
		"level": current_level,
		"total_xp": total_xp,
		"xp_for_current_level": xp_for_current_level,
		"xp_for_next_level": xp_for_next_level,
		"xp_progress": xp_progress,
		"xp_needed": xp_needed,
		"progress_percent": round(progress_percent, 2)
	}


async def award_xp(
	db: AsyncSession,
	user_id: UUID,
	xp_amount: int
) -> Dict:
	"""
	Атомарно начисляет опыт пользователю, проверяет повышение уровня и сохраняет результат.
	
	Использует SELECT FOR UPDATE для блокировки строки пользователя и предотвращения
	race conditions при одновременном начислении XP.
	
	Args:
		db: Асинхронная сессия базы данных
		user_id: UUID пользователя
		xp_amount: Количество XP для начисления (может быть отрицательным)
		
	Returns:
		Словарь с информацией о результате начисления:
		- level: новый уровень пользователя
		- total_xp: новый общий опыт
		- xp_awarded: начисленное количество XP
		- level_increased: True, если уровень повысился
		- progression: информация о прогрессе (см. get_progression_info)
		
	Raises:
		ValueError: Если пользователь не найден
	"""
	if xp_amount == 0:
		# Если XP не начисляется, просто возвращаем текущее состояние
		result = await db.execute(
			select(User).where(User.id == user_id)
		)
		user = result.scalar_one_or_none()
		if not user:
			raise ValueError(f"User with id {user_id} not found")
		
		progression = get_progression_info(user.xp)
		return {
			"level": user.level,
			"total_xp": user.xp,
			"xp_awarded": 0,
			"level_increased": False,
			"progression": progression
		}
	
	# Блокируем строку пользователя для атомарной операции
	result = await db.execute(
		select(User)
		.where(User.id == user_id)
		.with_for_update()
	)
	user = result.scalar_one_or_none()
	
	if not user:
		raise ValueError(f"User with id {user_id} not found")
	
	old_level = user.level
	old_xp = user.xp
	
	# Начисляем XP
	new_xp = max(0, user.xp + xp_amount)  # XP не может быть отрицательным
	new_level = calculate_level_from_xp(new_xp)
	
	# Обновляем данные пользователя
	user.xp = new_xp
	user.level = new_level
	
	await db.commit()
	await db.refresh(user)
	
	level_increased = new_level > old_level
	progression = get_progression_info(new_xp)
	
	return {
		"level": new_level,
		"total_xp": new_xp,
		"xp_awarded": xp_amount,
		"level_increased": level_increased,
		"old_level": old_level,
		"old_xp": old_xp,
		"progression": progression
	}
