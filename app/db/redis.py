from typing import Optional
import redis.asyncio as redis
from app.core.config import settings

_redis_client: Optional[redis.Redis] = None

async def get_redis() -> redis.Redis:
    """Get Redis client instance"""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            decode_responses=True
        )
    return _redis_client

async def save_refresh_token(user_id: str, token: str, expires_in_seconds: int) -> None:
    """Save refresh token to Redis with TTL"""
    client = await get_redis()
    key = f"{settings.REFRESH_TOKEN_REDIS_PREFIX}{token}"
    await client.setex(key, expires_in_seconds, user_id)

async def get_refresh_token(token: str) -> Optional[str]:
    """Get user_id by refresh token"""
    client = await get_redis()
    key = f"{settings.REFRESH_TOKEN_REDIS_PREFIX}{token}"
    user_id = await client.get(key)
    return user_id

async def delete_refresh_token(token: str) -> None:
    """Delete refresh token from Redis"""
    client = await get_redis()
    key = f"{settings.REFRESH_TOKEN_REDIS_PREFIX}{token}"
    await client.delete(key)
