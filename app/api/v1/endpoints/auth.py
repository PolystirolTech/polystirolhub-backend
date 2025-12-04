from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.api import deps
from app.core.config import settings
from app.core.security import create_access_token
from app.models.user import User, OAuthAccount
from app.schemas.user import UserCreate, OAuthAccountCreate
import httpx
import uuid
from datetime import datetime, timedelta
from typing import Optional
from jose import jwt

router = APIRouter()

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

@router.get("/login/{provider}")
def login(provider: str):
    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail="Provider not supported")
    
    config = PROVIDERS[provider]
    redirect_uri = f"http://localhost:8000/api/v1/auth/callback/{provider}"
    state = "login"
    url = f"{config['auth_url']}?client_id={config['client_id']}&redirect_uri={redirect_uri}&response_type=code&scope={config['scope']}&state={state}"
    return RedirectResponse(url)

@router.get("/link/{provider}")
def link(provider: str, current_user: User = Depends(deps.get_current_user)):
    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail="Provider not supported")
    
    config = PROVIDERS[provider]
    redirect_uri = f"http://localhost:8000/api/v1/auth/callback/{provider}"
    state = f"link:{current_user.id}" 
    url = f"{config['auth_url']}?client_id={config['client_id']}&redirect_uri={redirect_uri}&response_type=code&scope={config['scope']}&state={state}"
    return {"url": url}

@router.get("/callback/{provider}")
async def callback(
    provider: str, 
    code: str, 
    state: str = None, 
    db: AsyncSession = Depends(deps.get_db)
):
    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail="Provider not supported")
    
    config = PROVIDERS[provider]
    redirect_uri = f"http://localhost:8000/api/v1/auth/callback/{provider}"
    
    async with httpx.AsyncClient() as client:
        response = await client.post(config["token_url"], data={
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        })
        
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to retrieve token")
        
        token_data = response.json()
        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in")
        
        headers = {"Authorization": f"Bearer {access_token}"}
        if provider == "twitch":
            headers["Client-Id"] = config["client_id"]
            
        user_response = await client.get(config["user_url"], headers=headers)
        
        if user_response.status_code != 200:
             raise HTTPException(status_code=400, detail="Failed to retrieve user info")
        
        user_data = user_response.json()
        
        provider_account_id = ""
        email = ""
        username = ""
        
        if provider == "twitch":
            data = user_data["data"][0]
            provider_account_id = data["id"]
            email = data.get("email")
            username = data["login"]
        elif provider == "discord":
            provider_account_id = user_data["id"]
            email = user_data.get("email")
            username = user_data["username"]

    # Check if OAuth account exists
    result = await db.execute(select(OAuthAccount).where(
        OAuthAccount.provider == provider,
        OAuthAccount.provider_account_id == provider_account_id
    ))
    oauth_account = result.scalars().first()

    user = None
    
    # Handle Linking
    if state and state.startswith("link:"):
        user_id = state.split(":")[1]
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        
        if not user:
             raise HTTPException(status_code=400, detail="User for linking not found")
        
        if oauth_account:
            if oauth_account.user_id != user.id:
                raise HTTPException(status_code=400, detail="Account already linked to another user")
            
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
            
        return {"msg": "Account linked successfully"}

    # Handle Login
    if oauth_account:
        result = await db.execute(select(User).where(User.id == oauth_account.user_id))
        user = result.scalars().first()
        
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
            user = User(email=email, username=username)
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

    access_token_jwt = create_access_token(subject=user.id)
    
    return {
        "access_token": access_token_jwt,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "username": user.username
        }
    }
