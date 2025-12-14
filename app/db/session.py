from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# Импортируем все модели для регистрации в Base.metadata
from app.models.user import User, OAuthAccount, ExternalLink, UserCounter  # noqa: F401
from app.models.game_server import GameType, GameServer  # noqa: F401
from app.models.badge import Badge, UserBadge, UserBadgeProgress  # noqa: F401
from app.models.quest import Quest, UserQuest  # noqa: F401
from app.models.activity import Activity  # noqa: F401
from app.models.statistics import (  # noqa: F401
	MinecraftServer, MinecraftUser, MinecraftUserInfo, MinecraftSession,
	MinecraftNickname, MinecraftKill, MinecraftPing, MinecraftPlatform,
	MinecraftPluginVersion, MinecraftTPS, MinecraftWorld, MinecraftWorldTime,
	MinecraftJoinAddress, MinecraftVersionProtocol, MinecraftGeolocation,
	MinecraftSettings
)

engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
