from pydantic_settings import BaseSettings
from typing import List, Union
import json

class Settings(BaseSettings):
	PROJECT_NAME: str = "PolystirolHub Backend"
	API_V1_STR: str = "/api/v1"
	
	# CORS
	BACKEND_CORS_ORIGINS: Union[str, List[str]] = ["http://localhost:3000", "http://localhost:8000"]

	# Database
	POSTGRES_SERVER: str = "localhost"
	POSTGRES_USER: str = "postgres"
	POSTGRES_PASSWORD: str = "postgres"
	POSTGRES_DB: str = "app"
	SQLALCHEMY_DATABASE_URI: Union[str, None] = None

	# Redis
	REDIS_HOST: str = "localhost"
	REDIS_PORT: int = 6379

	# Auth
	SECRET_KEY: str = "CHANGE_THIS_SECRET_KEY"
	ALGORITHM: str = "HS256"
	ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
	REFRESH_TOKEN_EXPIRE_DAYS: int = 30
	REFRESH_TOKEN_REDIS_PREFIX: str = "refresh_token:"

	# OAuth Providers
	TWITCH_CLIENT_ID: str = ""
	TWITCH_CLIENT_SECRET: str = ""
	DISCORD_CLIENT_ID: str = ""
	DISCORD_CLIENT_SECRET: str = ""
	STEAM_CLIENT_ID: str = ""  # Опционально, для совместимости
	STEAM_API_KEY: str = ""

	# Frontend
	FRONTEND_URL: str = "http://localhost:3000"
	
	# Backend
	STORAGE_BASE_URL: str = "http://localhost:8000"  # Базовый URL бэкенда для формирования полных URL

	# Storage
	STORAGE_BACKEND: str = "local"  # "local" or "s3"
	STORAGE_LOCAL_PATH: str = "uploads/avatars"  # Путь для локального хранения
	STORAGE_BASE_URL: str = "/static/avatars"  # Базовый URL для доступа к файлам (относительный путь)
	# S3 настройки (для будущего использования)
	STORAGE_S3_BUCKET: str = ""
	STORAGE_S3_REGION: str = "us-east-1"
	STORAGE_S3_BASE_URL: str = ""  # Опционально, кастомный URL

	# Debug
	DEBUG: bool = True  # По умолчанию True для разработки

	class Config:
		case_sensitive = True
		env_file = ".env"

	def __init__(self, **data):
		super().__init__(**data)
		# Парсинг BACKEND_CORS_ORIGINS из строки
		if isinstance(self.BACKEND_CORS_ORIGINS, str):
			# Пробуем парсить как JSON
			try:
				self.BACKEND_CORS_ORIGINS = json.loads(self.BACKEND_CORS_ORIGINS)
			except json.JSONDecodeError:
				# Если не JSON, парсим как строку через запятую
				self.BACKEND_CORS_ORIGINS = [origin.strip() for origin in self.BACKEND_CORS_ORIGINS.split(",") if origin.strip()]
		# Формирование URI для БД
		if not self.SQLALCHEMY_DATABASE_URI:
			self.SQLALCHEMY_DATABASE_URI = f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}/{self.POSTGRES_DB}"

settings = Settings()
