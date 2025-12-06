from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.api import deps
from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token
from app.models.user import User, OAuthAccount
from app.schemas.user import UserUpdate
from app.db.redis import save_refresh_token, get_refresh_token, delete_refresh_token
import httpx
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from itsdangerous import URLSafeTimedSerializer
import secrets
import logging
from typing import Optional, Tuple

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
    },
    "steam": {
        "auth_url": "https://steamcommunity.com/openid/login",
        "api_key": settings.STEAM_API_KEY,
        "api_url": "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/",
        "openid_verify_url": "https://steamcommunity.com/openid/login",
    }
}

# Check Steam API key on startup
if not settings.STEAM_API_KEY:
    logger.warning("STEAM_API_KEY is not configured - Steam authentication will fail")


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

async def refresh_oauth_token_if_needed(
    user: User,
    db: AsyncSession
) -> Tuple[Optional[datetime], bool]:
    """
    Refresh OAuth tokens if they expired.
    Returns: (max_expires_at, success)
    """
    result = await db.execute(
        select(OAuthAccount).where(OAuthAccount.user_id == user.id)
    )
    oauth_accounts = result.scalars().all()
    
    if not oauth_accounts:
        return None, False
    
    max_expires_at = None
    all_refreshed = True
    now = datetime.now(timezone.utc)
    
    for oauth_account in oauth_accounts:
        # Skip Steam - it doesn't use refresh tokens
        if oauth_account.provider == "steam":
            continue
        
        # Skip if token doesn't expire or is still valid
        if not oauth_account.expires_at or oauth_account.expires_at > now:
            if oauth_account.expires_at:
                if max_expires_at is None or oauth_account.expires_at > max_expires_at:
                    max_expires_at = oauth_account.expires_at
            continue
        
        # Skip if no refresh token
        if not oauth_account.refresh_token:
            all_refreshed = False
            continue
        
        # Try to refresh token
        if oauth_account.provider not in PROVIDERS:
            all_refreshed = False
            continue
        
        config = PROVIDERS[oauth_account.provider]
        
        try:
            async with httpx.AsyncClient() as client:
                data = {
                    "client_id": config["client_id"],
                    "client_secret": config["client_secret"],
                    "grant_type": "refresh_token",
                    "refresh_token": oauth_account.refresh_token,
                }
                
                response = await client.post(config["token_url"], data=data)
                
                if response.status_code == 200:
                    token_data = response.json()
                    oauth_account.access_token = token_data["access_token"]
                    oauth_account.refresh_token = token_data.get("refresh_token") or oauth_account.refresh_token
                    
                    expires_in = token_data.get("expires_in")
                    if expires_in:
                        oauth_account.expires_at = now + timedelta(seconds=int(expires_in))
                        if max_expires_at is None or oauth_account.expires_at > max_expires_at:
                            max_expires_at = oauth_account.expires_at
                    else:
                        oauth_account.expires_at = None
                    
                    await db.commit()
                    logger.info(f"Refreshed OAuth token for user {user.id}, provider {oauth_account.provider}")
                else:
                    logger.warning(f"Failed to refresh OAuth token for user {user.id}, provider {oauth_account.provider}: {response.status_code}")
                    all_refreshed = False
        except Exception as e:
            logger.exception(f"Error refreshing OAuth token for user {user.id}, provider {oauth_account.provider}: {str(e)}")
            all_refreshed = False
    
    return max_expires_at, all_refreshed

@router.get("/login/{provider}")
def login(provider: str):
    """Initiate OAuth login flow with CSRF protection"""
    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail="Provider not supported")
    
    config = PROVIDERS[provider]
    redirect_uri = f"{settings.BACKEND_CORS_ORIGINS[1]}{settings.API_V1_STR}/auth/callback/{provider}"
    
    # Create secure state token for CSRF protection
    state = create_state_token("login")
    
    # Steam uses OpenID 2.0, not OAuth 2.0
    if provider == "steam":
        params = {
            "openid.ns": "http://specs.openid.net/auth/2.0",
            "openid.mode": "checkid_setup",
            "openid.return_to": redirect_uri,
            "openid.realm": settings.BACKEND_CORS_ORIGINS[1],
            "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
            "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
        }
    else:
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
    
    # Steam uses OpenID 2.0, not OAuth 2.0
    if provider == "steam":
        # Add state to return_to for linking support
        redirect_uri_with_state = f"{redirect_uri}?state={state}"
        params = {
            "openid.ns": "http://specs.openid.net/auth/2.0",
            "openid.mode": "checkid_setup",
            "openid.return_to": redirect_uri_with_state,
            "openid.realm": settings.BACKEND_CORS_ORIGINS[1],
            "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
            "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
        }
    else:
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
    request: Request,
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
    
    if provider not in PROVIDERS:
        error_params = urlencode({"error": "invalid_provider"})
        return RedirectResponse(f"{settings.FRONTEND_URL}/auth/error?{error_params}")
    
    config = PROVIDERS[provider]
    redirect_uri = f"{settings.BACKEND_CORS_ORIGINS[1]}{settings.API_V1_STR}/auth/callback/{provider}"
    
    try:
        # Steam uses OpenID 2.0, handle differently
        if provider == "steam":
            # Steam returns OpenID parameters in query string
            openid_params = dict(request.query_params)
            
            if "openid.mode" not in openid_params or openid_params.get("openid.mode") != "id_res":
                error_params = urlencode({"error": "invalid_request"})
                return RedirectResponse(f"{settings.FRONTEND_URL}/auth/error?{error_params}")
            
            # Extract state if present (for linking)
            state = openid_params.get("state")
            if state:
                try:
                    state_data = verify_state_token(state)
                    action = state_data.get("action")
                    user_id = state_data.get("user_id")
                except Exception:
                    # Invalid state, default to login
                    action = "login"
                    user_id = None
            else:
                action = "login"
                user_id = None
            
            # Verify OpenID assertion
            verify_data = {}
            
            # Copy all openid.* parameters for verification
            # This is critical - Steam checks that all parameters match exactly
            for key, value in openid_params.items():
                if key.startswith("openid."):
                    # Change mode from id_res to check_authentication
                    if key == "openid.mode":
                        verify_data[key] = "check_authentication"
                    else:
                        verify_data[key] = value
            
            # Verify that we have all required parameters
            required_params = ["openid.mode", "openid.ns", "openid.op_endpoint", "openid.claimed_id", 
                             "openid.identity", "openid.return_to", "openid.response_nonce", 
                             "openid.assoc_handle", "openid.signed", "openid.sig"]
            missing_params = [p for p in required_params if p not in verify_data]
            if missing_params:
                logger.warning(f"Missing required OpenID parameters: {missing_params}")
            
            if "openid.signed" in verify_data:
                signed_params = verify_data["openid.signed"].split(",")
                # Check that all signed parameters are present
                for param in signed_params:
                    full_param = f"openid.{param}" if not param.startswith("openid.") else param
                    if full_param not in verify_data:
                        logger.error(f"Missing signed parameter: {full_param}")
            
            async with httpx.AsyncClient(follow_redirects=False, timeout=10.0) as client:
                # Steam OpenID expects application/x-www-form-urlencoded
                headers = {
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "PolystirolHub/1.0"
                }
                
                verify_response = await client.post(
                    config["openid_verify_url"], 
                    data=verify_data,
                    headers=headers
                )
                
                # Steam should return text/plain, not text/html
                content_type = verify_response.headers.get('Content-Type', '').lower()
                if 'text/html' in content_type:
                    logger.error(f"Steam returned HTML instead of text/plain. This usually means the request was invalid or redirected.")
                    if verify_response.status_code == 302:
                        location = verify_response.headers.get('Location', '')
                        logger.error(f"302 redirect to: {location}")
                    error_params = urlencode({"error": "token_error"})
                    return RedirectResponse(f"{settings.FRONTEND_URL}/auth/error?{error_params}")
                
                verify_text = verify_response.text
                
                # Steam returns plain text in format: "is_valid:true" or "is_valid:false"
                is_valid = False
                
                # Try to parse the response
                if verify_text:
                    for line in verify_text.split('\n'):
                        line = line.strip()
                        if line.startswith('is_valid:'):
                            is_valid_value = line.split(':', 1)[1].strip().lower()
                            is_valid = is_valid_value == 'true'
                            break
                
                # If we got 302, it might be an error, but check body first
                if verify_response.status_code == 302:
                    if not is_valid:
                        logger.error("Steam returned 302 without is_valid in response body")
                        error_params = urlencode({"error": "token_error"})
                        return RedirectResponse(f"{settings.FRONTEND_URL}/auth/error?{error_params}")
                
                if not is_valid:
                    logger.error(f"Steam OpenID verification failed. Status: {verify_response.status_code}, Response: {verify_text[:200]}")
                    error_params = urlencode({"error": "token_error"})
                    return RedirectResponse(f"{settings.FRONTEND_URL}/auth/error?{error_params}")
                
                # Extract Steam ID from openid.identity
                identity = openid_params.get("openid.identity", "")
                if not identity.startswith("https://steamcommunity.com/openid/id/"):
                    error_params = urlencode({"error": "invalid_identity"})
                    return RedirectResponse(f"{settings.FRONTEND_URL}/auth/error?{error_params}")
                
                steam_id = identity.replace("https://steamcommunity.com/openid/id/", "")
                provider_account_id = steam_id
                
                # Get user data from Steam Web API
                if not config.get("api_key"):
                    logger.error("STEAM_API_KEY is not configured")
                    error_params = urlencode({"error": "config_error"})
                    return RedirectResponse(f"{settings.FRONTEND_URL}/auth/error?{error_params}")
                
                api_url = f"{config['api_url']}?key={config['api_key']}&steamids={steam_id}"
                user_response = await client.get(api_url)
                
                if user_response.status_code != 200:
                    logger.error(f"Steam API error: {user_response.status_code}, {user_response.text}")
                    error_params = urlencode({"error": "user_info_error"})
                    return RedirectResponse(f"{settings.FRONTEND_URL}/auth/error?{error_params}")
                
                user_data = user_response.json()
                players = user_data.get("response", {}).get("players", [])
                
                if not players:
                    logger.error(f"Steam API returned no players: {user_data}")
                    error_params = urlencode({"error": "user_info_error"})
                    return RedirectResponse(f"{settings.FRONTEND_URL}/auth/error?{error_params}")
                
                player = players[0]
                username = player.get("personaname", "")
                avatar = player.get("avatarfull") or player.get("avatarmedium", "")
                email = None  # Steam doesn't provide email via OpenID
                access_token = steam_id  # Store Steam ID as access_token
                refresh_token = None  # Steam doesn't use refresh tokens
                expires_in = None
                
        else:
            # Standard OAuth 2.0 flow
            if not code or not state:
                error_params = urlencode({"error": "invalid_request"})
                return RedirectResponse(f"{settings.FRONTEND_URL}/auth/error?{error_params}")
            
            # Verify state token (CSRF protection)
            try:
                state_data = verify_state_token(state)
                action = state_data.get("action")
                user_id = state_data.get("user_id")
            except Exception:
                error_params = urlencode({"error": "invalid_state"})
                return RedirectResponse(f"{settings.FRONTEND_URL}/auth/error?{error_params}")
            
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
            
            # For OAuth 2.0, we have action and user_id from state
            action = state_data.get("action")
            user_id = state_data.get("user_id")

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
                if expires_in:
                    oauth_account.expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                else:
                    oauth_account.expires_at = None
                await db.commit()
            else:
                new_oauth = OAuthAccount(
                    user_id=user.id,
                    provider=provider,
                    provider_account_id=provider_account_id,
                    access_token=access_token,
                    refresh_token=refresh_token,
                    expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in) if expires_in else None
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
                oauth_account.expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            else:
                oauth_account.expires_at = None
            await db.commit()
        else:
            # Only search by email if it exists (Steam doesn't provide email)
            if email:
                result = await db.execute(select(User).where(User.email == email))
                user = result.scalars().first()
            
            if not user:
                # For Steam, username is just a display name and not unique
                # If username already exists, make it unique by adding a suffix
                final_username = username
                if username:
                    base_username = username
                    counter = 1
                    while True:
                        result = await db.execute(select(User).where(User.username == final_username))
                        existing = result.scalars().first()
                        if not existing:
                            break
                        final_username = f"{base_username}{counter}"
                        counter += 1
                        if counter > 100:  # Safety limit
                            final_username = f"{base_username}_{secrets.token_hex(4)}"
                            break
                
                user = User(email=email, username=final_username, avatar=avatar if avatar else None)
                db.add(user)
                await db.commit()
                await db.refresh(user)
            
            new_oauth = OAuthAccount(
                user_id=user.id,
                provider=provider,
                provider_account_id=provider_account_id,
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in) if expires_in else None
            )
            db.add(new_oauth)
            await db.commit()

        # Verify user exists before creating JWT
        if not user:
            logger.error("User is None after OAuth processing")
            error_params = urlencode({"error": "user_creation_failed"})
            return RedirectResponse(f"{settings.FRONTEND_URL}/auth/error?{error_params}")

        # Create JWT access token
        access_token_jwt = create_access_token(subject=user.id)
        
        # Create refresh token
        refresh_token_value = create_refresh_token()
        
        # Calculate refresh token TTL: minimum 30 days or OAuth token expiration if longer
        min_refresh_ttl = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60  # 30 days in seconds
        refresh_ttl = min_refresh_ttl
        
        # Check all OAuth token expirations to find maximum
        result = await db.execute(
            select(OAuthAccount).where(OAuthAccount.user_id == user.id)
        )
        all_oauth_accounts = result.scalars().all()
        
        for acc in all_oauth_accounts:
            if acc.expires_at:
                oauth_ttl = int((acc.expires_at - datetime.now(timezone.utc)).total_seconds())
                if oauth_ttl > refresh_ttl:
                    refresh_ttl = oauth_ttl
        
        # Save refresh token to Redis
        await save_refresh_token(str(user.id), refresh_token_value, refresh_ttl)
        
        response = RedirectResponse(f"{settings.FRONTEND_URL}/auth/success")
        
        # Set HTTP-only cookies for security
        is_secure = settings.FRONTEND_URL.startswith("https")
        
        # Access token cookie (30 minutes)
        response.set_cookie(
            key="access_token",
            value=access_token_jwt,
            httponly=True,  # Prevents JavaScript access
            secure=is_secure,  # Only send over HTTPS in production
            samesite="lax",  # CSRF protection
            max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
        
        # Refresh token cookie (30+ days)
        response.set_cookie(
            key="refresh_token",
            value=refresh_token_value,
            httponly=True,
            secure=is_secure,
            samesite="lax",
            max_age=refresh_ttl
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

@router.post("/refresh")
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(deps.get_db)
):
    """Refresh access token using refresh token"""
    refresh_token_value = request.cookies.get("refresh_token")
    
    if not refresh_token_value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found"
        )
    
    # Get user_id from Redis
    user_id = await get_refresh_token(refresh_token_value)
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )
    
    # Get user from database
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    
    if not user:
        # Clean up invalid token
        await delete_refresh_token(refresh_token_value)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    # Refresh OAuth tokens if needed
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
    
    # Update cookies
    is_secure = settings.FRONTEND_URL.startswith("https")
    
    response.set_cookie(
        key="access_token",
        value=new_access_token,
        httponly=True,
        secure=is_secure,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
    
    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        secure=is_secure,
        samesite="lax",
        max_age=refresh_ttl
    )
    
    return {"message": "Tokens refreshed successfully"}

@router.post("/logout")
async def logout(request: Request, response: Response):
    """Logout user by clearing the authentication cookies and refresh token"""
    # Delete refresh token from Redis if exists
    refresh_token_value = request.cookies.get("refresh_token")
    if refresh_token_value:
        await delete_refresh_token(refresh_token_value)
    
    # Delete cookies
    response.delete_cookie(key="access_token")
    response.delete_cookie(key="refresh_token")
    return {"message": "Successfully logged out"}
