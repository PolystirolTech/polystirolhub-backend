from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from pathlib import Path
from contextlib import asynccontextmanager
from app.core.config import settings
from app.api.v1.api import api_router
from app.core.scheduler import start_scheduler, shutdown_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
	"""Управление жизненным циклом приложения."""
	# Startup
	start_scheduler()
	yield
	# Shutdown
	shutdown_scheduler()


app = FastAPI(
	title=settings.PROJECT_NAME,
	lifespan=lifespan,
	docs_url="/docs" if settings.DEBUG else None,
	redoc_url="/redoc" if settings.DEBUG else None
)

class TokenRefreshMiddleware(BaseHTTPMiddleware):
    """Middleware to set refreshed tokens in cookies if they were refreshed"""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Check if new tokens were set during request processing
        if hasattr(request.state, 'new_tokens'):
            tokens = request.state.new_tokens
            is_secure = settings.FRONTEND_URL.startswith("https")
            
            response.set_cookie(
                key="access_token",
                value=tokens['access_token'],
                httponly=True,
                secure=is_secure,
                samesite="lax",
                max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
            )
            
            response.set_cookie(
                key="refresh_token",
                value=tokens['refresh_token'],
                httponly=True,
                secure=is_secure,
                samesite="lax",
                max_age=tokens['refresh_ttl']
            )
        
        return response

app.add_middleware(TokenRefreshMiddleware)

# Set all CORS enabled origins
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix=settings.API_V1_STR)

# Mount static files for local storage
if settings.STORAGE_BACKEND.lower() == "local":
	# Получаем абсолютный путь к директории uploads
	uploads_path = Path(settings.STORAGE_LOCAL_PATH)
	if not uploads_path.is_absolute():
		uploads_path = Path(__file__).parent.parent / uploads_path
	
	# Создаем директорию если не существует
	uploads_path.mkdir(parents=True, exist_ok=True)
	
	# Создаем директорию для баннеров если не существует
	banners_path = Path(settings.STORAGE_BANNERS_LOCAL_PATH)
	if not banners_path.is_absolute():
		banners_path = Path(__file__).parent.parent / banners_path
	banners_path.mkdir(parents=True, exist_ok=True)
	
	# Создаем директорию для бэджиков если не существует
	badges_path = Path(settings.STORAGE_BADGES_LOCAL_PATH)
	if not badges_path.is_absolute():
		badges_path = Path(__file__).parent.parent / badges_path
	badges_path.mkdir(parents=True, exist_ok=True)
	
	# Создаем директорию для ресурс-паков если не существует
	resource_packs_path = Path(settings.STORAGE_RESOURCE_PACKS_LOCAL_PATH)
	if not resource_packs_path.is_absolute():
		resource_packs_path = Path(__file__).parent.parent / resource_packs_path
	resource_packs_path.mkdir(parents=True, exist_ok=True)
	
	# Mount для статических файлов
	app.mount("/static", StaticFiles(directory=str(uploads_path.parent)), name="static")

@app.get("/health")
def health_check():
    return {"status": "ok"}
