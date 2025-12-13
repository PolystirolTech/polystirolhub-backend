# Техническая инструкция по интеграции мода Minecraft с бэкендом

## Обзор

Система бэйджиков работает через комбинацию:
- **Resource Pack** - содержит все бэйджики как bitmap font providers
- **API эндпоинты** - для получения информации о выбранном бэйджике игрока
- **Unicode символы** - каждый бэйджик маппится на уникальный символ из Private Use Area (E000-EFFF)

## Архитектура

### 1. Resource Pack

Ресурс-пак генерируется автоматически при создании/обновлении/удалении бэйджа и содержит:
- `pack.mcmeta` - метаданные ресурс-пака (pack_format: 15)
- `assets/minecraft/font/default.json` - конфигурация font providers
- `assets/minecraft/textures/font/badge_{badge_id}.png` - текстуры бэйджиков

Каждый бэйджик маппится на уникальный Unicode символ из диапазона E000-EFFF через bitmap font provider.

### 2. Структура данных

**Badge:**
- `id` (UUID) - уникальный идентификатор
- `name` (string) - название
- `description` (string) - описание
- `image_url` (string) - URL изображения
- `unicode_char` (string) - hex код Unicode символа (например, "E000")
- `badge_type` (enum) - тип: temporary, event, permanent

**UserBadge:**
- `user_id` (UUID) - ID пользователя
- `badge_id` (UUID) - ID бэйджика
- `received_at` (datetime) - когда получен
- `expires_at` (datetime, nullable) - срок действия (для temporary)

**User:**
- `selected_badge_id` (UUID, nullable) - выбранный для отображения бэйджик

**GameServer:**
- `resource_pack_url` (string, nullable) - публичный URL ресурс-пака
- `resource_pack_hash` (string, nullable) - SHA256 хэш ресурс-пака

## API Эндпоинты

### Базовый URL
```
https://api.dev.sluicee.ru/api/v1
```

### 1. Получение выбранного бэйджика игрока

**GET** `/badges/minecraft/{player_uuid}`

**Параметры:**
- `player_uuid` (string) - UUID игрока Minecraft в формате `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` (36 символов)

**Ответ:**
```json
{
	"id": "uuid",
	"name": "Название бэйджика",
	"description": "Описание",
	"image_url": "https://...",
	"badge_type": "permanent",
	"unicode_char": "E000",
	"created_at": "2024-01-01T00:00:00Z"
}
```

**Коды ответа:**
- `200` - бэйджик найден
- `404` - игрок не найден или бэйджик не выбран/истек
- `400` - неверный формат UUID

**Важно:** Если у игрока нет выбранного бэйджика или он истек, возвращается `null`.

### 2. Получение информации о сервере

**GET** `/game-servers/{server_id}`

**Параметры:**
- `server_id` (UUID) - ID игрового сервера

**Ответ:**
```json
{
	"id": "uuid",
	"name": "Название сервера",
	"ip": "127.0.0.1",
	"port": 25565,
	"resource_pack_url": "https://.../static/resource_packs/badges_resource_pack.zip",
	"resource_pack_hash": "sha256_hash_hex",
	...
}
```

**Использование:**
- `resource_pack_url` - URL для загрузки ресурс-пака
- `resource_pack_hash` - SHA256 хэш для проверки целостности

### 3. Получение списка всех бэйджиков

**GET** `/badges`

**Ответ:**
```json
[
	{
		"id": "uuid",
		"name": "Название",
		"description": "Описание",
		"image_url": "https://...",
		"badge_type": "permanent",
		"unicode_char": "E000",
		"created_at": "2024-01-01T00:00:00Z"
	},
	...
]
```

## Логика работы мода

### 1. Инициализация

При подключении к серверу:

1. **Получить информацию о сервере:**
   ```
   GET /api/v1/game-servers/{server_id}
   ```
   Из ответа извлечь `resource_pack_url` и `resource_pack_hash`.

2. **Загрузить и применить ресурс-пак:**
   - Скачать ZIP архив по `resource_pack_url`
   - Проверить SHA256 хэш (опционально, но рекомендуется)
   - Применить ресурс-пак через Minecraft API

### 2. Получение бэйджика игрока

Для каждого игрока в игре:

1. **Получить UUID игрока** (Minecraft UUID)

2. **Запросить бэйджик:**
   ```
   GET /api/v1/badges/minecraft/{player_uuid}
   ```

3. **Обработать ответ:**
   - Если `null` - игрок не имеет выбранного бэйджика
   - Если объект - извлечь `unicode_char` (например, "E000")

4. **Отобразить бэйджик:**
   - Преобразовать hex строку в Unicode символ:
     ```java
     int unicodeValue = Integer.parseInt(unicodeChar, 16); // "E000" -> 57344
     char badgeChar = (char) unicodeValue; // '\uE000'
     ```
   - Добавить символ в имя игрока или в отдельный компонент

### 3. Кэширование

Рекомендуется кэшировать:
- **Resource Pack** - до получения нового `resource_pack_hash`
- **Бэйджики игроков** - на короткое время (30-60 секунд) для снижения нагрузки на API

### 4. Обработка ошибок

- **404 при получении бэйджика** - игрок не найден или не имеет бэйджика (нормальная ситуация)
- **Сетевые ошибки** - повторить запрос с экспоненциальной задержкой
- **Неверный формат UUID** - логировать ошибку, не отправлять запрос

## Примеры кода

### Java (Forge/Fabric)

```java
// Получение бэйджика игрока
public CompletableFuture<Optional<String>> getPlayerBadge(UUID playerUuid) {
	return CompletableFuture.supplyAsync(() -> {
		try {
			String url = String.format("%s/api/v1/badges/minecraft/%s", 
				BACKEND_URL, playerUuid.toString());
			
			HttpResponse<String> response = HttpClient.newHttpClient()
				.send(HttpRequest.newBuilder()
					.uri(URI.create(url))
					.GET()
					.build(),
					HttpResponse.BodyHandlers.ofString());
			
			if (response.statusCode() == 404) {
				return Optional.empty();
			}
			
			if (response.statusCode() != 200) {
				throw new RuntimeException("Bad response: " + response.statusCode());
			}
			
			String body = response.body();
			if (body == null || body.equals("null")) {
				return Optional.empty();
			}
			
			JsonObject badge = JsonParser.parseString(body).getAsJsonObject();
			String unicodeChar = badge.get("unicode_char").getAsString();
			return Optional.of(unicodeChar);
			
		} catch (Exception e) {
			LOGGER.error("Failed to get player badge", e);
			return Optional.empty();
		}
	});
}

// Преобразование hex в символ
public char unicodeCharFromHex(String hex) {
	int unicodeValue = Integer.parseInt(hex, 16);
	return (char) unicodeValue;
}

// Отображение бэйджика в имени
public Component formatPlayerNameWithBadge(Player player, String unicodeChar) {
	char badgeChar = unicodeCharFromHex(unicodeChar);
	return Component.literal(badgeChar + " " + player.getName().getString());
}
```

### Получение resource pack URL

```java
public CompletableFuture<ResourcePackInfo> getServerResourcePack(UUID serverId) {
	return CompletableFuture.supplyAsync(() -> {
		try {
			String url = String.format("%s/api/v1/game-servers/%s", 
				BACKEND_URL, serverId.toString());
			
			HttpResponse<String> response = HttpClient.newHttpClient()
				.send(HttpRequest.newBuilder()
					.uri(URI.create(url))
					.GET()
					.build(),
					HttpResponse.BodyHandlers.ofString());
			
			if (response.statusCode() != 200) {
				throw new RuntimeException("Failed to get server info");
			}
			
			JsonObject server = JsonParser.parseString(response.body()).getAsJsonObject();
			String packUrl = server.get("resource_pack_url").getAsString();
			String packHash = server.get("resource_pack_hash").getAsString();
			
			return new ResourcePackInfo(packUrl, packHash);
			
		} catch (Exception e) {
			LOGGER.error("Failed to get resource pack info", e);
			throw new RuntimeException(e);
		}
	});
}
```

## Важные детали

### Unicode символы

- Каждый бэйджик имеет уникальный `unicode_char` в формате hex (например, "E000")
- Диапазон: E000-EFFF (4096 возможных бэйджиков)
- Символы из Private Use Area, не конфликтуют с обычными символами

### Resource Pack формат

- **Pack format:** 15 (для Minecraft 1.20+)
- **Font providers:** bitmap type
- **Текстуры:** PNG, максимальный размер 256x256 (автоматически ресайзится)

### Обновление ресурс-пака

Ресурс-пак автоматически перегенерируется при:
- Создании нового бэйджика
- Обновлении изображения бэйджика
- Удалении бэйджика

Мод должен проверять `resource_pack_hash` и перезагружать ресурс-пак при изменении.

### Временные бэйджики

Бэйджики типа `temporary` имеют `expires_at`. API автоматически фильтрует истекшие бэйджики, но мод может дополнительно проверять срок действия для кэширования.

## Безопасность

- Все эндпоинты публичные (не требуют аутентификации)
- UUID игрока должен быть валидным (36 символов, формат UUID)
- Resource Pack загружается по HTTPS (рекомендуется проверять SSL сертификат)

## Отладка

Для проверки работы API используйте Swagger UI:
```
https://your-backend-domain.com/docs
```

Полезные эндпоинты для тестирования:
- `GET /badges` - список всех бэйджиков
- `GET /badges/minecraft/{player_uuid}` - бэйджик конкретного игрока
- `GET /game-servers/{server_id}` - информация о сервере
