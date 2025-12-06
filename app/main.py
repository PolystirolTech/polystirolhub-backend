from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.config import settings
from app.api.v1.api import api_router

app = FastAPI(title=settings.PROJECT_NAME)

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

@app.get("/health")
def health_check():
    return {"status": "ok"}
