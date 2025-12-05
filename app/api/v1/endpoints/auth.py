from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.api import deps
from app.core.config import settings
from app.core.security import create_access_token
from app.models.user import User, OAuthAccount
from app.schemas.user import UserUpdate
import httpx
from datetime import datetime, timedelta
from urllib.parse import urlencode
from itsdangerous import URLSafeTimedSerializer
import secrets
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Secure serializer for state tokens
serializer = URLSafeTimedSerializer(settings.SECRET_KEY)

PROVIDERS = {
    "twitch": {
        "auth_url": "https://id.twitch.tv/oauth2/authorize",
        "token_url": "https://id.twitch.tv/oauth2/token",
        "user_url": "https://api.twitch.tv/helix/users",
        "client_id": settings.TWITCH_CLIENT_ID,
        "client_secret": settings.TWITCH_CLIENT_SECRET,
        "scope": "user:read:email",
    },
    "discord": {
        "auth_url": "https://discord.com/api/oauth2/authorize",
        "token_url": "https://discord.com/api/oauth2/token",
        "user_url": "https://discord.com/api/users/@me",
        "client_id": settings.DISCORD_CLIENT_ID,
        "client_secret": settings.DISCORD_CLIENT_SECRET,
        "scope": "identify email",
    }
}

def create_state_token(action: str, user_id: str = None) -> str:
    """Create secure state token with CSRF protection"""
    data = {
        "action": action,
        "nonce": secrets.token_urlsafe(32),
        "user_id": user_id
    }
    return serializer.dumps(data)

def verify_state_token(state: str, max_age: int = 600) -> dict:
    """Verify and decode state token (max_age in seconds, default 10 minutes)"""
    try:
        return serializer.loads(state, max_age=max_age)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or expired state token")

@router.get("/login/{provider}")
def login(provider: str):
    """Initiate OAuth login flow with CSRF protection"""
    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail="Provider not supported")
    
    config = PROVIDERS[provider]
    redirect_uri = f"{settings.BACKEND_CORS_ORIGINS[1]}{settings.API_V1_STR}/auth/callback/{provider}"
    
    # Create secure state token for CSRF protection
    state = create_state_token("login")
    
    params = {
        "client_id": config['client_id'],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": config['scope'],
        "state": state
    }
    
    url = f"{config['auth_url']}?{urlencode(params)}"
    return RedirectResponse(url)

@router.get("/link/{provider}")
async def link(provider: str, current_user: User = Depends(deps.get_current_user)):
    """Get OAuth URL for linking a new provider to existing account"""
    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail="Provider not supported")
    
    config = PROVIDERS[provider]
    redirect_uri = f"{settings.BACKEND_CORS_ORIGINS[1]}{settings.API_V1_STR}/auth/callback/{provider}"
    
    # Create secure state token with user ID for linking
    state = create_state_token("link", str(current_user.id))
    
    params = {
        "client_id": config['client_id'],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": config['scope'],
        "state": state
    }
    
    url = f"{config['auth_url']}?{urlencode(params)}"
    return {"url": url}

@router.get("/callback/{provider}")
async def callback(
    provider: str, 
    code: str = None,
    error: str = None,
    error_description: str = None,
    state: str = None, 
    db: AsyncSession = Depends(deps.get_db)
):
    """Handle OAuth provider callback with secure state validation"""
    
    # Handle OAuth errors
    if error:
        error_params = urlencode({"error": "oauth_error"})
        return RedirectResponse(f"{settings.FRONTEND_URL}/auth/error?{error_params}")
    
    if not code or not state:
        error_params = urlencode({"error": "invalid_request"})
        return RedirectResponse(f"{settings.FRONTEND_URL}/auth/error?{error_params}")
    
    if provider not in PROVIDERS:
        error_params = urlencode({"error": "invalid_provider"})
        return RedirectResponse(f"{settings.FRONTEND_URL}/auth/error?{error_params}")
    
    # Verify state token (CSRF protection)
    try:
        state_data = verify_state_token(state)
        action = state_data.get("action")
        user_id = state_data.get("user_id")
    except Exception:
        error_params = urlencode({"error": "invalid_state"})
        return RedirectResponse(f"{settings.FRONTEND_URL}/auth/error?{error_params}")
    
    config = PROVIDERS[provider]
    redirect_uri = f"{settings.BACKEND_CORS_ORIGINS[1]}{settings.API_V1_STR}/auth/callback/{provider}"
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(config["token_url"], data={
                "client_id": config["client_id"],
                "client_secret": config["client_secret"],
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            })
            
            if response.status_code != 200:
                error_params = urlencode({"error": "token_error"})
                return RedirectResponse(f"{settings.FRONTEND_URL}/auth/error?{error_params}")
            
            token_data = response.json()
            access_token = token_data["access_token"]
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in")
            if expires_in is not None:
                try:
                    expires_in = int(expires_in)
                except (ValueError, TypeError):
                    logger.warning(f"Invalid expires_in value: {expires_in}, treating as None")
                    expires_in = None
            
            headers = {"Authorization": f"Bearer {access_token}"}
            if provider == "twitch":
                headers["Client-Id"] = config["client_id"]
                
            user_response = await client.get(config["user_url"], headers=headers)
            
            if user_response.status_code != 200:
                error_params = urlencode({"error": "user_info_error"})
                return RedirectResponse(f"{settings.FRONTEND_URL}/auth/error?{error_params}")
            
            user_data = user_response.json()
            
            provider_account_id = ""
            email = ""
            username = ""
            avatar = ""
            
            if provider == "twitch":
                data = user_data["data"][0]
                provider_account_id = data["id"]
                email = data.get("email")
                username = data["login"]
                avatar = data.get("profile_image_url", "")
            elif provider == "discord":
                provider_account_id = user_data["id"]
                email = user_data.get("email")
                username = user_data["username"]
                avatar_hash = user_data.get("avatar")
                if avatar_hash:
                    avatar = f"https://cdn.discordapp.com/avatars/{provider_account_id}/{avatar_hash}.png?size=512"
                else:
                    discriminator = user_data.get("discriminator", "0")
                    discriminator_mod = int(discriminator) % 5
                    avatar = f"https://cdn.discordapp.com/embed/avatars/{discriminator_mod}.png"

        # Check if OAuth account exists
        result = await db.execute(select(OAuthAccount).where(
            OAuthAccount.provider == provider,
            OAuthAccount.provider_account_id == provider_account_id
        ))
        oauth_account = result.scalars().first()

        user = None
        
        # Handle Linking
        if action == "link" and user_id:
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalars().first()
            
            if not user:
                error_params = urlencode({"error": "link_error"})
                return RedirectResponse(f"{settings.FRONTEND_URL}/auth/error?{error_params}")
            
            if oauth_account:
                if oauth_account.user_id != user.id:
                    error_params = urlencode({"error": "already_linked"})
                    return RedirectResponse(f"{settings.FRONTEND_URL}/auth/error?{error_params}")
                
                oauth_account.access_token = access_token
                oauth_account.refresh_token = refresh_token
                await db.commit()
            else:
                new_oauth = OAuthAccount(
                    user_id=user.id,
                    provider=provider,
                    provider_account_id=provider_account_id,
                    access_token=access_token,
                    refresh_token=refresh_token,
                    expires_at=datetime.utcnow() + timedelta(seconds=expires_in) if expires_in else None
                )
                db.add(new_oauth)
                await db.commit()
                
            success_params = urlencode({"success": "true"})
            return RedirectResponse(f"{settings.FRONTEND_URL}/auth/link-success?{success_params}")

        # Handle Login
        if oauth_account:
            result = await db.execute(select(User).where(User.id == oauth_account.user_id))
            user = result.scalars().first()
            
            if not user:
                logger.error(f"OAuth account exists but user not found: user_id={oauth_account.user_id}")
                error_params = urlencode({"error": "user_not_found"})
                return RedirectResponse(f"{settings.FRONTEND_URL}/auth/error?{error_params}")
            
            oauth_account.access_token = access_token
            oauth_account.refresh_token = refresh_token
            if expires_in:
                oauth_account.expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            await db.commit()
        else:
            if email:
                result = await db.execute(select(User).where(User.email == email))
                user = result.scalars().first()
            
            if not user:
                user = User(email=email, username=username, avatar=avatar if avatar else None)
                db.add(user)
                await db.commit()
                await db.refresh(user)
            
            new_oauth = OAuthAccount(
                user_id=user.id,
                provider=provider,
                provider_account_id=provider_account_id,
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=datetime.utcnow() + timedelta(seconds=expires_in) if expires_in else None
            )
            db.add(new_oauth)
            await db.commit()

        # Verify user exists before creating JWT
        if not user:
            logger.error("User is None after OAuth processing")
            error_params = urlencode({"error": "user_creation_failed"})
            return RedirectResponse(f"{settings.FRONTEND_URL}/auth/error?{error_params}")

        # Create JWT and set as HTTP-only cookie
        access_token_jwt = create_access_token(subject=user.id)
        
        response = RedirectResponse(f"{settings.FRONTEND_URL}/auth/success")
        
        # Set HTTP-only cookie for security
        response.set_cookie(
            key="access_token",
            value=access_token_jwt,
            httponly=True,  # Prevents JavaScript access
            secure=settings.FRONTEND_URL.startswith("https"),  # Only send over HTTPS in production
            samesite="lax",  # CSRF protection
            max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
        
        return response
        
    except Exception as e:
        logger.exception(f"OAuth callback error for provider {provider}: {str(e)}")
        error_params = urlencode({"error": "server_error"})
        return RedirectResponse(f"{settings.FRONTEND_URL}/auth/error?{error_params}")

@router.get("/me")
async def get_current_user_info(current_user: User = Depends(deps.get_current_user)):
    """Get current authenticated user information"""
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "username": current_user.username,
        "avatar": current_user.avatar,
        "is_active": current_user.is_active,
        "created_at": current_user.created_at.isoformat()
    }

@router.patch("/me")
async def update_current_user(
    user_update: UserUpdate,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db)
):
    """Update current user profile"""
    update_data = user_update.model_dump(exclude_unset=True)
    
    if "email" in update_data and update_data["email"] is not None:
        # Check if email is already taken by another user
        result = await db.execute(select(User).where(User.email == update_data["email"]))
        existing_user = result.scalars().first()
        if existing_user and existing_user.id != current_user.id:
            raise HTTPException(status_code=400, detail="Email already registered")
        current_user.email = update_data["email"]
    
    if "username" in update_data and update_data["username"] is not None:
        # Check if username is already taken by another user
        result = await db.execute(select(User).where(User.username == update_data["username"]))
        existing_user = result.scalars().first()
        if existing_user and existing_user.id != current_user.id:
            raise HTTPException(status_code=400, detail="Username already taken")
        current_user.username = update_data["username"]
    
    if "avatar" in update_data:
        current_user.avatar = update_data["avatar"]
    
    if "is_active" in update_data:
        current_user.is_active = update_data["is_active"]
    
    await db.commit()
    await db.refresh(current_user)
    
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "username": current_user.username,
        "avatar": current_user.avatar,
        "is_active": current_user.is_active,
        "created_at": current_user.created_at.isoformat()
    }

@router.post("/logout")
async def logout(response: Response):
    """Logout user by clearing the authentication cookie"""
    response.delete_cookie(key="access_token")
    return {"message": "Successfully logged out"}
