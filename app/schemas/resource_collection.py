from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from uuid import UUID
from datetime import datetime

# ========== Запросы от модов ==========

class ResourceCollectionRequest(BaseModel):
	"""Запрос от мода для обновления прогресса сбора ресурсов"""
	server_uuid: str = Field(..., max_length=36, description="UUID сервера из game_servers")
	resource_type: str = Field(..., description="Тип ресурса (например, 'wood', 'stone', 'iron')")
	amount: int = Field(..., ge=0, description="Количество собранных ресурсов (инкремент)")

	@field_validator('server_uuid')
	@classmethod
	def validate_server_uuid(cls, v: str) -> str:
		if len(v) != 36:
			raise ValueError("server_uuid must be 36 characters long")
		return v


class ResourceCollectionResponse(BaseModel):
	"""Ответ на запрос от мода"""
	success: bool
	message: str
	current_amount: int


# ========== Схемы для админки ==========

class ResourceGoalBase(BaseModel):
	server_id: UUID
	name: str = Field(..., description="Название цели")
	resource_type: str
	target_amount: int = Field(..., ge=0)
	is_active: bool = True


class ResourceGoalCreate(ResourceGoalBase):
	pass


class ResourceGoalUpdate(BaseModel):
	server_id: Optional[UUID] = None
	name: Optional[str] = None
	resource_type: Optional[str] = None
	target_amount: Optional[int] = Field(None, ge=0)
	is_active: Optional[bool] = None


class ResourceGoalResponse(ResourceGoalBase):
	id: UUID
	created_at: datetime
	updated_at: datetime

	class Config:
		from_attributes = True


# ========== Схемы для получения прогресса ==========

class ResourceProgressDetail(BaseModel):
	"""Детальная информация о прогрессе по типу ресурса"""
	resource_type: str
	name: Optional[str] = None  # Название цели
	current_amount: int
	target_amount: Optional[int] = None
	goal_id: Optional[UUID] = None
	is_active: Optional[bool] = None
	progress_percentage: Optional[float] = None  # Процент выполнения (0-100)
	updated_at: datetime

	class Config:
		from_attributes = True


class ResourceProgressResponse(BaseModel):
	"""Ответ с прогрессом для отображения на сайте"""
	server_id: UUID
	server_name: str
	resources: List[ResourceProgressDetail]

	class Config:
		from_attributes = True

