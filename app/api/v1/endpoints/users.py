from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete
from app.api import deps
from app.models.user import User, OAuthAccount
from app.db.redis import delete_refresh_token
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.delete("/me")
async def delete_current_user(
	request: Request,
	response: Response,
	current_user: User = Depends(deps.get_current_user),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Delete current user account and all associated data"""
	# Delete refresh token from Redis if exists
	refresh_token_value = request.cookies.get("refresh_token")
	if refresh_token_value:
		await delete_refresh_token(refresh_token_value)
	
	# Delete all OAuth accounts first (cascade doesn't work with delete().where())
	await db.execute(delete(OAuthAccount).where(OAuthAccount.user_id == current_user.id))
	# Delete user from database
	await db.execute(delete(User).where(User.id == current_user.id))
	await db.commit()
	
	# Clear cookies
	response.delete_cookie(key="access_token")
	response.delete_cookie(key="refresh_token")
	
	return {"message": "Account deleted successfully"}
