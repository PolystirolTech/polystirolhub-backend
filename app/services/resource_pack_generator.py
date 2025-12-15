from typing import Tuple
from uuid import UUID
import zipfile
import json
import hashlib
import io
import logging
import httpx
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.badge import Badge as BadgeModel
from app.models.game_server import GameServer
from app.core.storage import StorageBackend

logger = logging.getLogger(__name__)

def generate_unicode_char(badge_index: int) -> str:
	"""
	Генерация уникального юникод символа из Private Use Area (E000-EFFF)
	
	Args:
		badge_index: Индекс баджа (0-based)
	
	Returns:
		Юникод символ в формате "E000" (без префикса \\u)
	"""
	if badge_index < 0 or badge_index > 4095:  # E000-EFFF это 4096 символов
		raise ValueError(f"Badge index must be between 0 and 4095, got {badge_index}")
	
	unicode_value = 0xE000 + badge_index
	return f"{unicode_value:04X}"

async def generate_resource_pack(
	db: AsyncSession,
	storage: StorageBackend,
	game_server_id: UUID
) -> Tuple[str, str]:
	"""
	Генерация общего Minecraft resource pack со всеми баджами
	
	Args:
		db: Асинхронная сессия БД
		storage: Storage backend для сохранения ресурс-пака
		game_server_id: ID игрового сервера для обновления
	
	Returns:
		Tuple (url, hash) - публичный URL ресурс-пака и его SHA1 хэш
	"""
	# Получаем все баджи из БД
	result = await db.execute(select(BadgeModel).order_by(BadgeModel.created_at))
	badges = result.scalars().all()
	
	if not badges:
		logger.warning("No badges found, skipping resource pack generation")
		# Обновляем GameServer с пустыми значениями
		game_server_result = await db.execute(
			select(GameServer).where(GameServer.id == game_server_id)
		)
		game_server = game_server_result.scalar_one_or_none()
		if game_server:
			game_server.resource_pack_url = None
			game_server.resource_pack_hash = None
			await db.commit()
		return (None, None)
	
	# Создаем ZIP архив в памяти
	zip_buffer = io.BytesIO()
	
	with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
		# Создаем pack.mcmeta
		pack_meta = {
			"pack": {
				"pack_format": 15,
				"description": "PolystirolHub Badges"
			}
		}
		zip_file.writestr("pack.mcmeta", json.dumps(pack_meta, indent=2))
		
		# Убеждаемся, что у всех баджей есть unicode_char
		badges_to_update = []
		for index, badge in enumerate(badges):
			if not badge.unicode_char:
				badge.unicode_char = generate_unicode_char(index)
				badges_to_update.append(badge)
		
		# Сохраняем обновления одним коммитом
		if badges_to_update:
			await db.commit()
		
		# Создаем структуру директорий
		font_providers = []
		
		async with httpx.AsyncClient(timeout=30.0) as client:
			for badge in badges:
				# Преобразуем hex строку (например "E000") в юникод символ
				unicode_char_value = int(badge.unicode_char, 16)
				unicode_char = chr(unicode_char_value)
				
				# Скачиваем изображение баджа
				try:
					response = await client.get(badge.image_url)
					response.raise_for_status()
					image_data = response.content
					
					# Обрабатываем изображение через Pillow для конвертации в PNG
					image = Image.open(io.BytesIO(image_data))
					# Конвертируем в RGBA если нужно
					if image.mode != 'RGBA':
						image = image.convert('RGBA')
					# Изменяем размер если нужно (для Minecraft лучше квадратные изображения 8x8, 16x16 и т.д.)
					# Но сохраняем оригинальный размер, если он разумный
					max_size = 256
					if image.width > max_size or image.height > max_size:
						image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
					
					# Сохраняем в PNG формат
					png_buffer = io.BytesIO()
					image.save(png_buffer, format='PNG')
					png_data = png_buffer.getvalue()
					
					# Добавляем в ZIP
					texture_path = f"assets/minecraft/textures/font/badge_{badge.id}.png"
					zip_file.writestr(texture_path, png_data)
					
					# Добавляем provider для font
					font_providers.append({
						"type": "bitmap",
						"file": f"minecraft:font/badge_{badge.id}.png",
						"ascent": 8,
						"height": 8,
						"chars": [unicode_char]
					})
					
				except Exception as e:
					logger.error(f"Failed to process badge {badge.id} image: {e}", exc_info=True)
					continue
		
		# Создаем default.json для font
		font_json = {
			"providers": font_providers
		}
		zip_file.writestr("assets/minecraft/font/default.json", json.dumps(font_json, indent=2))
	
	# Получаем данные ZIP архива
	zip_data = zip_buffer.getvalue()
	
	# Вычисляем SHA1 хэш
	hash_obj = hashlib.sha1(zip_data)
	pack_hash = hash_obj.hexdigest()
	
	# Сохраняем в storage
	file_name = "badges_resource_pack.zip"
	resource_pack_url = await storage.save(zip_data, file_name)
	
	logger.info(f"Resource pack generated: {resource_pack_url}, hash: {pack_hash}")
	
	# Обновляем GameServer
	game_server_result = await db.execute(
		select(GameServer).where(GameServer.id == game_server_id)
	)
	game_server = game_server_result.scalar_one_or_none()
	
	if not game_server:
		logger.error(f"GameServer {game_server_id} not found")
		return (resource_pack_url, pack_hash)
	
	game_server.resource_pack_url = resource_pack_url
	game_server.resource_pack_hash = pack_hash
	await db.commit()
	
	return (resource_pack_url, pack_hash)
