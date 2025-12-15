from fastapi import APIRouter
from app.api.v1.endpoints import auth, users, admin, game_servers, statistics, badges, quests, notifications, activity

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(game_servers.router, tags=["game-servers"])
api_router.include_router(statistics.router, prefix="/statistics", tags=["statistics"])
api_router.include_router(badges.router, tags=["badges"])
api_router.include_router(quests.router, tags=["quests"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
api_router.include_router(activity.router, prefix="/activity", tags=["activity"])
