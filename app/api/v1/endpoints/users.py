from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete
from app.api import deps
from app.models.user import User, OAuthAccount
from app.db.redis import delete_refresh_token
from app.core.progression import award_xp, get_progression_info
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class AwardXPRequest(BaseModel):
	xp_amount: int


@router.get("/me/progression")
async def get_progression(
	current_user: User = Depends(deps.get_current_user),
	db: AsyncSession = Depends(deps.get_db)
):
	"""Получить текущий уровень, XP и прогресс до следующего уровня"""
	progression = get_progression_info(current_user.xp)
	return progression


@router.post("/me/award-xp")
async def award_xp_to_user(
	request: AwardXPRequest,
	current_user: User = Depends(deps.get_current_user),
	db: AsyncSession = Depends(deps.get_db),
	_ = Depends(deps.require_debug_mode)
):
	"""Начислить XP текущему пользователю (дэбаг)"""
	try:
		result = await award_xp(db, current_user.id, request.xp_amount)
		return result
	except ValueError as e:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=str(e)
		)


@router.post("/me/reset-progression")
async def reset_progression(
	current_user: User = Depends(deps.get_current_user),
	db: AsyncSession = Depends(deps.get_db),
	_ = Depends(deps.require_debug_mode)
):
	"""Сбросить XP и уровень до начальных значений (дэбаг)"""
	try:
		# Сбрасываем XP и уровень
		current_user.xp = 0
		current_user.level = 1
		await db.commit()
		await db.refresh(current_user)
		
		progression = get_progression_info(0)
		return {
			"message": "Progression reset successfully",
			"progression": progression
		}
	except Exception as e:
		await db.rollback()
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=f"Failed to reset progression: {str(e)}"
		)


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
