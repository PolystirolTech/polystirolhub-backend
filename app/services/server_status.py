from typing import Optional
from uuid import UUID
import json
import base64
import logging
from mcstatus import JavaServer
from mcstatus.responses import JavaStatusResponse
from app.db.redis import get_cache, set_cache, acquire_lock, release_lock

logger = logging.getLogger(__name__)

# Константы
CACHE_TTL = 60  # 1 минута
LOCK_TIMEOUT = 10  # 10 секунд
DEFAULT_MINECRAFT_PORT = 25565

async def get_server_status(server_id: UUID, ip: str, port: Optional[int] = None) -> dict:
	"""
	Получение статуса сервера с кэшированием в Redis.
	
	Логика:
	1. Проверка кэша в Redis
	2. Если кэш есть - возврат из кэша
	3. Если кэша нет - попытка получить блокировку
	4. Если блокировка получена - запрос к серверу, сохранение в кэш
	5. Если блокировка не получена - ожидание и повторная проверка кэша
	"""
	cache_key = f"server_status:{server_id}"
	lock_key = f"server_status:lock:{server_id}"
	
	# Проверяем кэш
	cached_data = await get_cache(cache_key)
	if cached_data:
		try:
			return json.loads(cached_data)
		except (json.JSONDecodeError, Exception) as e:
			logger.warning(f"Failed to parse cached server status for {server_id}: {e}")
	
	# Кэш истек или отсутствует, пытаемся получить блокировку
	lock_acquired = await acquire_lock(lock_key, timeout=LOCK_TIMEOUT)
	
	if lock_acquired:
		try:
			# Запрашиваем статус у сервера
			status_data = await _fetch_minecraft_status(ip, port)
			
			# Сохраняем в кэш
			await set_cache(cache_key, json.dumps(status_data), CACHE_TTL)
			
			return status_data
		finally:
			# Освобождаем блокировку
			await release_lock(lock_key)
	else:
		# Блокировка не получена, значит другой процесс обновляет статус
		# Ждем немного и проверяем кэш снова
		import asyncio
		await asyncio.sleep(0.5)
		
		cached_data = await get_cache(cache_key)
		if cached_data:
			try:
				return json.loads(cached_data)
			except (json.JSONDecodeError, Exception) as e:
				logger.warning(f"Failed to parse cached server status after wait for {server_id}: {e}")
		
		# Если кэш все еще пуст, возвращаем статус "недоступен"
		return {
			"server_icon": None,
			"motd": None,
			"players_online": 0,
			"players_max": 0,
			"players_list": None,
			"ping": None,
			"version": None,
			"online": False,
			"error": "Server status is being updated, please try again"
		}

async def _fetch_minecraft_status(ip: str, port: Optional[int] = None) -> dict:
	"""
	Внутренняя функция для запроса статуса Minecraft сервера.
	"""
	try:
		# Определяем порт
		server_port = port if port is not None else DEFAULT_MINECRAFT_PORT
		
		# Создаем объект сервера
		# Если порт стандартный, можно использовать lookup для проверки SRV записей
		if port is None:
			try:
				server = JavaServer.lookup(ip)
			except Exception:
				# Если lookup не сработал, используем стандартный порт
				server = JavaServer(ip, DEFAULT_MINECRAFT_PORT)
		else:
			server = JavaServer(ip, server_port)
		
		# Получаем статус (mcstatus поддерживает async через asyncio)
		status: JavaStatusResponse = await server.async_status()
		
		# Обрабатываем server icon
		server_icon_base64 = None
		if status.icon:
			try:
				# icon уже в base64 формате, но нужно убрать префикс data:image/png;base64,
				icon_data = status.icon
				if isinstance(icon_data, str):
					if icon_data.startswith("data:image"):
						# Извлекаем base64 часть
						server_icon_base64 = icon_data.split(",", 1)[1] if "," in icon_data else icon_data
					else:
						server_icon_base64 = icon_data
				else:
					# Если это bytes, конвертируем в base64
					server_icon_base64 = base64.b64encode(icon_data).decode('utf-8')
			except Exception as e:
				logger.warning(f"Failed to process server icon: {e}")
		
		# Обрабатываем MOTD
		motd = None
		# Используем raw description для получения сырых данных (может быть dict, list или str)
		raw_description = status.raw.get("description")
		if raw_description:
			if isinstance(raw_description, dict):
				# Извлекаем текст из JSON структуры
				motd = _extract_text_from_motd(raw_description)
			elif isinstance(raw_description, list):
				# Если это список, обрабатываем как список
				motd = _extract_text_from_motd(raw_description)
			else:
				# Если это строка, используем как есть
				motd = str(raw_description)
		elif status.description:
			# Fallback на property description, если raw недоступен
			motd = str(status.description)
		
		# Обрабатываем список игроков
		players_list = None
		if status.players.sample:
			players_list = [player.name for player in status.players.sample]
		
		return {
			"server_icon": server_icon_base64,
			"motd": motd,
			"players_online": status.players.online,
			"players_max": status.players.max,
			"players_list": players_list,
			"ping": status.latency,
			"version": status.version.name if status.version else None,
			"online": True,
			"error": None
		}
		
	except Exception as e:
		logger.error(f"Failed to fetch Minecraft server status for {ip}:{port or DEFAULT_MINECRAFT_PORT}: {e}")
		return {
			"server_icon": None,
			"motd": None,
			"players_online": 0,
			"players_max": 0,
			"players_list": None,
			"ping": None,
			"version": None,
			"online": False,
			"error": str(e)
		}

def _extract_text_from_motd(motd_dict: dict) -> str:
	"""
	Извлекает текст из JSON структуры MOTD Minecraft.
	"""
	text_parts = []
	
	def extract_text(obj):
		if isinstance(obj, dict):
			if "text" in obj:
				text_parts.append(obj["text"])
			if "extra" in obj and isinstance(obj["extra"], list):
				for item in obj["extra"]:
					extract_text(item)
		elif isinstance(obj, list):
			for item in obj:
				extract_text(item)
		elif isinstance(obj, str):
			text_parts.append(obj)
	
	extract_text(motd_dict)
	return "".join(text_parts).strip() or None
