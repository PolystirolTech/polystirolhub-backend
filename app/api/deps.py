from typing import AsyncGenerator, Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token
from app.db.session import AsyncSessionLocal
from app.db.redis import get_refresh_token, save_refresh_token, delete_refresh_token
from app.models.user import User
from datetime import datetime, timezone

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login/access-token", auto_error=False)

async def get_db() -> AsyncGenerator:
    async with AsyncSessionLocal() as session:
        yield session

async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db), 
    token: Optional[str] = Depends(oauth2_scheme)
) -> User:
    """Get current user from JWT token (cookie or Authorization header). 
    Automatically refreshes access token if expired but refresh token is valid."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Try to get token from cookie first, then from Authorization header
    if not token:
        token = request.cookies.get("access_token")
    
    # Try to decode access token
    user_id = None
    token_valid = False
    
    if token:
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            user_id = payload.get("sub")
            if user_id is not None:
                token_valid = True
        except JWTError:
            # Token is invalid or expired, will try refresh token
            token_valid = False
    
    # If access token is invalid/expired, try to refresh using refresh token
    if not token_valid:
        refresh_token_value = request.cookies.get("refresh_token")
        if refresh_token_value:
            # Get user_id from Redis
            redis_user_id = await get_refresh_token(refresh_token_value)
            
            if redis_user_id:
                # Verify user exists
                result = await db.execute(select(User).where(User.id == redis_user_id))
                user = result.scalars().first()
                
                if user:
                    # Refresh OAuth tokens if needed (lazy import to avoid circular dependency)
                    from app.api.v1.endpoints.auth import refresh_oauth_token_if_needed
                    max_expires_at, _ = await refresh_oauth_token_if_needed(user, db)
                    
                    # Create new tokens (rotation)
                    new_access_token = create_access_token(subject=user.id)
                    new_refresh_token = create_refresh_token()
                    
                    # Calculate new refresh token TTL
                    min_refresh_ttl = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
                    refresh_ttl = min_refresh_ttl
                    
                    if max_expires_at:
                        oauth_ttl = int((max_expires_at - datetime.now(timezone.utc)).total_seconds())
                        if oauth_ttl > refresh_ttl:
                            refresh_ttl = oauth_ttl
                    
                    # Delete old refresh token and save new one
                    await delete_refresh_token(refresh_token_value)
                    await save_refresh_token(str(user.id), new_refresh_token, refresh_ttl)
                    
                    # Store new tokens in request.state for middleware to set cookies
                    request.state.new_tokens = {
                        'access_token': new_access_token,
                        'refresh_token': new_refresh_token,
                        'refresh_ttl': refresh_ttl
                    }
                    
                    # Set user_id for validation below
                    user_id = str(user.id)
                    token_valid = True
    
    if not token_valid or not user_id:
        raise credentials_exception
    
    # Get user from database
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    
    if user is None:
        raise credentials_exception
    return user

async def get_current_admin(
	current_user: User = Depends(get_current_user)
) -> User:
	"""Get current user and verify they are an admin (is_admin=True or is_super_admin=True)"""
	if not current_user.is_admin and not current_user.is_super_admin:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="Not enough permissions. Admin access required."
		)
	return current_user

async def get_current_super_admin(
	current_user: User = Depends(get_current_user)
) -> User:
	"""Get current user and verify they are a super admin (is_super_admin=True)"""
	if not current_user.is_super_admin:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="Not enough permissions. Super admin access required."
		)
	return current_user

async def require_debug_mode():
	"""Dependency для проверки, что DEBUG режим включен"""
	if not settings.DEBUG:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="Debug endpoints are disabled in production"
		)
	return True
