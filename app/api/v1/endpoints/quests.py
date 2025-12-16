from fastapi import APIRouter, Depends, HTTPException, status, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload
from typing import Optional
from datetime import date
from app.api import deps
from app.models.user import User
from app.models.quest import Quest as QuestModel, UserQuest, QuestType
from app.schemas.quest import (
	Quest,
	UserQuestWithQuest
)
from app.services.quest_progress import initialize_daily_quests_for_user, initialize_achievement_quests_for_user
from uuid import UUID
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# ========== Публичные эндпоинты ==========

@router.get("/quests", response_model=list[Quest])
async def get_quests(
	skip: int = Query(0, ge=0, description="Количество пропущенных записей"),
	limit: int = Query(50, ge=1, le=100, description="Максимальное количество записей"),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Публичный список всех активных квестов"""
	result = await db.execute(
		select(QuestModel)
		.where(QuestModel.is_active)
		.order_by(QuestModel.created_at.desc())
		.offset(skip)
		.limit(limit)
	)
	quests = result.scalars().all()
	return quests

# ========== Пользовательские эндпоинты ==========

@router.get("/quests/me", response_model=list[UserQuestWithQuest])
async def get_my_quests(
	skip: int = Query(0, ge=0, description="Количество пропущенных записей"),
	limit: int = Query(50, ge=1, le=100, description="Максимальное количество записей"),
	current_user: User = Depends(deps.get_current_user),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Получить список моих квестов с прогрессом"""
	today = date.today()
	
	# Для daily квестов автоматически инициализируем квесты на сегодня если их нет
	await initialize_daily_quests_for_user(current_user.id, db, today)
	
	# Для achievement квестов автоматически инициализируем квесты если их нет
	await initialize_achievement_quests_for_user(current_user.id, db)
	
	# Получаем все квесты пользователя
	# Для daily - только сегодняшние, для achievement - все
	result = await db.execute(
		select(UserQuest)
		.options(selectinload(UserQuest.quest))
		.where(
			and_(
				UserQuest.user_id == current_user.id,
				or_(
					and_(
						UserQuest.quest.has(QuestModel.quest_type == QuestType.daily),
						UserQuest.quest_date == today
					),
					and_(
						UserQuest.quest.has(QuestModel.quest_type == QuestType.achievement),
						UserQuest.quest_date.is_(None)
					)
				)
			)
		)
		.order_by(UserQuest.quest_date.desc().nullslast(), UserQuest.id.desc())
		.offset(skip)
		.limit(limit)
	)
	user_quests = result.scalars().all()
	
	return user_quests

# ========== Админские эндпоинты ==========

@router.get("/admin/quests", response_model=list[Quest])
async def list_quests(
	skip: int = Query(0, ge=0, description="Количество пропущенных записей"),
	limit: int = Query(50, ge=1, le=100, description="Максимальное количество записей"),
	current_user: User = Depends(deps.get_current_admin),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Список всех квестов (только для админов)"""
	result = await db.execute(
		select(QuestModel).order_by(QuestModel.created_at.desc())
		.offset(skip)
		.limit(limit)
	)
	quests = result.scalars().all()
	return quests

@router.post("/admin/quests", response_model=Quest)
async def create_quest(
	name: str = Form(...),
	description: Optional[str] = Form(None),
	quest_type: str = Form(...),
	condition_key: str = Form(...),
	target_value: int = Form(...),
	reward_xp: int = Form(0),
	reward_balance: int = Form(0),
	is_active: bool = Form(True),
	current_user: User = Depends(deps.get_current_admin),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Создание квеста (только для админов)"""
	# Валидация типа квеста
	try:
		quest_type_enum = QuestType(quest_type)
	except ValueError:
		raise HTTPException(
			status_code=400,
			detail=f"Invalid quest_type. Allowed values: {', '.join([qt.value for qt in QuestType])}"
		)
	
	# Валидация condition_key
	# Проверяем, есть ли он в badge_conditions (для общих условий)
	from app.core.badge_conditions import is_condition_valid, get_condition_info
	
	# Список специальных condition_key для квестов (не счетчики)
	special_quest_condition_keys = [
		"link_all_platforms",
		"playtime_daily",
		"server_join",
		"deaths_in_session"
	]
		
	# Проверяем, валиден ли condition_key
	is_badge_condition = is_condition_valid(condition_key)
	is_special_quest_condition = condition_key in special_quest_condition_keys
	
	# Разрешаем любые ключи, так как система счетчиков универсальная
	# Любой ключ может быть счетчиком и будет работать автоматически
	if not is_badge_condition and not is_special_quest_condition:
		# Это может быть новый счетчик - разрешаем
		# Система UserCounters поддерживает любые ключи
		pass
	
	# Если это badge condition, проверяем требования
	if is_badge_condition:
		condition_info = get_condition_info(condition_key)
		if condition_info:
			if condition_info.get("requires_target_value") and not target_value:
				raise HTTPException(
					status_code=400,
					detail=f"condition_key '{condition_key}' requires target_value to be set"
				)
	
	# Создаем квест
	new_quest = QuestModel(
		name=name,
		description=description,
		quest_type=quest_type_enum,
		condition_key=condition_key,
		target_value=target_value,
		reward_xp=reward_xp,
		reward_balance=reward_balance,
		is_active=is_active
	)
	
	db.add(new_quest)
	await db.commit()
	await db.refresh(new_quest)
	
	return new_quest

@router.get("/admin/quests/{quest_id}", response_model=Quest)
async def get_quest_admin(
	quest_id: UUID,
	current_user: User = Depends(deps.get_current_admin),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Получение квеста (только для админов)"""
	result = await db.execute(
		select(QuestModel).where(QuestModel.id == quest_id)
	)
	quest = result.scalar_one_or_none()
	
	if not quest:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Quest not found"
		)
	
	return quest

@router.put("/admin/quests/{quest_id}", response_model=Quest)
async def update_quest(
	quest_id: UUID,
	name: Optional[str] = Form(None),
	description: Optional[str] = Form(None),
	quest_type: Optional[str] = Form(None),
	condition_key: Optional[str] = Form(None),
	target_value: Optional[int] = Form(None),
	reward_xp: Optional[int] = Form(None),
	reward_balance: Optional[int] = Form(None),
	is_active: Optional[bool] = Form(None),
	current_user: User = Depends(deps.get_current_admin),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Обновление квеста (только для админов)"""
	result = await db.execute(
		select(QuestModel).where(QuestModel.id == quest_id)
	)
	quest = result.scalar_one_or_none()
	
	if not quest:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Quest not found"
		)
	
	# Обновляем поля
	if name is not None:
		quest.name = name
	if description is not None:
		quest.description = description
	if quest_type is not None:
		try:
			quest.quest_type = QuestType(quest_type)
		except ValueError:
			raise HTTPException(
				status_code=400,
				detail=f"Invalid quest_type. Allowed values: {', '.join([qt.value for qt in QuestType])}"
			)
	if condition_key is not None:
		# Валидация condition_key аналогично create
		from app.core.badge_conditions import is_condition_valid
		special_quest_condition_keys = [
			"link_all_platforms",
			"playtime_daily",
			"server_join",
			"deaths_in_session"
		]
		is_badge_condition = is_condition_valid(condition_key)
		is_special_quest_condition = condition_key in special_quest_condition_keys
		
		# Разрешаем любые ключи, так как система счетчиков универсальная
		# Любой ключ может быть счетчиком и будет работать автоматически
		if not is_badge_condition and not is_special_quest_condition:
			# Это может быть новый счетчик - разрешаем
			pass
		quest.condition_key = condition_key
	if target_value is not None:
		quest.target_value = target_value
	if reward_xp is not None:
		quest.reward_xp = reward_xp
	if reward_balance is not None:
		quest.reward_balance = reward_balance
	if is_active is not None:
		quest.is_active = is_active
	
	await db.commit()
	await db.refresh(quest)
	
	return quest

@router.delete("/admin/quests/{quest_id}")
async def delete_quest(
	quest_id: UUID,
	current_user: User = Depends(deps.get_current_admin),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Удаление квеста (soft delete через is_active=False) (только для админов)"""
	result = await db.execute(
		select(QuestModel).where(QuestModel.id == quest_id)
	)
	quest = result.scalar_one_or_none()
	
	if not quest:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Quest not found"
		)
	
	quest.is_active = False
	await db.commit()
	
	return {"message": "Quest deleted successfully"}

