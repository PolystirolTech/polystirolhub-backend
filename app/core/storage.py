from abc import ABC, abstractmethod
from pathlib import Path
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

class StorageBackend(ABC):
	"""Абстрактный класс для бэкендов хранения файлов"""
	
	@abstractmethod
	async def save(self, file_content: bytes, file_path: str) -> str:
		"""
		Сохраняет файл и возвращает URL для доступа к нему
		
		Args:
			file_content: Содержимое файла в байтах
			file_path: Путь относительно корня хранилища (например, "avatars/user_123.jpg")
		
		Returns:
			URL для доступа к файлу
		"""
		pass
	
	@abstractmethod
	async def delete(self, file_path: str) -> bool:
		"""
		Удаляет файл из хранилища
		
		Args:
			file_path: Путь относительно корня хранилища
		
		Returns:
			True если файл был удален, False если файл не найден
		"""
		pass
	
	@abstractmethod
	def get_url(self, file_path: str) -> str:
		"""
		Возвращает URL для доступа к файлу
		
		Args:
			file_path: Путь относительно корня хранилища
		
		Returns:
			URL для доступа к файлу
		"""
		pass

class LocalStorageBackend(StorageBackend):
	"""Локальное хранилище файлов"""
	
	def __init__(self, base_path: str, base_url: str, backend_url: str = None):
		"""
		Args:
			base_path: Абсолютный путь к директории хранения
			base_url: Базовый URL для доступа к файлам (например, "/static/avatars")
			backend_url: Базовый URL бэкенда для формирования полных URL (например, "http://localhost:8000")
		"""
		self.base_path = Path(base_path)
		self.base_url = base_url.rstrip("/")
		self.backend_url = (backend_url or "").rstrip("/")
		# Создаем директорию если не существует
		self.base_path.mkdir(parents=True, exist_ok=True)
	
	async def save(self, file_content: bytes, file_path: str) -> str:
		"""Сохраняет файл локально"""
		full_path = self.base_path / file_path
		# Создаем директорию если нужно
		full_path.parent.mkdir(parents=True, exist_ok=True)
		
		# Сохраняем файл
		with open(full_path, "wb") as f:
			f.write(file_content)
		
		logger.info(f"File saved to {full_path}")
		return self.get_url(file_path)
	
	async def delete(self, file_path: str) -> bool:
		"""Удаляет файл локально"""
		full_path = self.base_path / file_path
		if full_path.exists():
			full_path.unlink()
			logger.info(f"File deleted: {full_path}")
			return True
		return False
	
	def get_url(self, file_path: str) -> str:
		"""Возвращает URL для локального файла"""
		# Убираем начальный слеш если есть
		file_path = file_path.lstrip("/")
		relative_url = f"{self.base_url}/{file_path}"
		# Если указан backend_url, формируем полный URL
		if self.backend_url:
			return f"{self.backend_url}{relative_url}"
		return relative_url

class S3StorageBackend(StorageBackend):
	"""S3 хранилище (заготовка для будущего использования)"""
	
	def __init__(self, bucket: str, region: str, base_url: str = None):
		"""
		Args:
			bucket: Имя S3 бакета
			region: Регион S3
			base_url: Базовый URL (опционально, можно использовать стандартный S3 URL)
		"""
		self.bucket = bucket
		self.region = region
		self.base_url = base_url or f"https://{bucket}.s3.{region}.amazonaws.com"
		# TODO: Инициализировать boto3 client
	
	async def save(self, file_content: bytes, file_path: str) -> str:
		"""Сохраняет файл в S3"""
		# TODO: Реализовать загрузку в S3 через boto3
		raise NotImplementedError("S3 storage not implemented yet")
	
	async def delete(self, file_path: str) -> bool:
		"""Удаляет файл из S3"""
		# TODO: Реализовать удаление из S3
		raise NotImplementedError("S3 storage not implemented yet")
	
	def get_url(self, file_path: str) -> str:
		"""Возвращает URL для S3 файла"""
		file_path = file_path.lstrip("/")
		return f"{self.base_url}/{file_path}"

def get_storage_backend() -> StorageBackend:
	"""Фабрика для получения бэкенда хранения"""
	backend_type = settings.STORAGE_BACKEND.lower()
	
	if backend_type == "local":
		# Получаем абсолютный путь
		base_path = Path(settings.STORAGE_LOCAL_PATH)
		if not base_path.is_absolute():
			# Относительно корня проекта
			base_path = Path(__file__).parent.parent.parent / base_path
		
		return LocalStorageBackend(
			base_path=str(base_path),
			base_url=settings.STORAGE_BASE_URL,
			backend_url=settings.STORAGE_BASE_URL
		)
	elif backend_type == "s3":
		return S3StorageBackend(
			bucket=settings.STORAGE_S3_BUCKET,
			region=settings.STORAGE_S3_REGION,
			base_url=getattr(settings, "STORAGE_S3_BASE_URL", None)
		)
	else:
		raise ValueError(f"Unknown storage backend: {backend_type}")

# Глобальный экземпляр бэкенда
_storage_backend: StorageBackend = None

def get_storage() -> StorageBackend:
	"""Получить глобальный экземпляр бэкенда хранения (singleton)"""
	global _storage_backend
	if _storage_backend is None:
		_storage_backend = get_storage_backend()
	return _storage_backend
