from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.models.user import User
from app.schemas.shop import (
    ShopItemResponse, 
    ShopOrderCreate, 
    ShopOrderResponse, 
    PendingCommandResponse,
    ShopCategoryCreate,
    ShopCategoryUpdate,
    ShopCategoryResponse,
    ShopItemCreate,
    ShopItemUpdate
)
from app.services import shop as shop_service

router = APIRouter()

# --- User Endpoints ---

@router.get("/categories", response_model=List[ShopCategoryResponse])
async def get_shop_categories(
    db: AsyncSession = Depends(deps.get_db),
):
    """
    Get all shop categories.
    """
    return await shop_service.get_categories(db)

@router.get("/items", response_model=List[ShopItemResponse])
async def get_shop_items(
    server_id: Optional[UUID] = None,
    db: AsyncSession = Depends(deps.get_db),
):
    """
    Get available shop items.
    If server_id is provided, filters items available for that server.
    If not provided, returns ALL items (useful for admin or global view).
    """
    if server_id:
        items = await shop_service.get_items_for_server(db, server_id)
    else:
        # If no server specified, return all items (e.g. for admin or global list)
        items = await shop_service.get_all_items(db)
    return items

@router.post("/buy", response_model=ShopOrderResponse)
async def buy_item(
    order_in: ShopOrderCreate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    Purchase an item.
    """
    order = await shop_service.buy_item(db, current_user.id, order_in)
    return order

@router.get("/orders/me", response_model=List[ShopOrderResponse])
async def get_my_orders(
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    Get current user's purchase history.
    """
    return await shop_service.get_user_orders(db, current_user.id)

# --- Server/Plugin Endpoints ---
# NOTE: These should be protected by a Server Token mechanism.
# For now, assuming we have a dependency `deps.get_current_server` or similar.
# If not, we'll use a placeholder or assume the caller passes a secret header verified in deps.

# Let's check `deps.py` to see if we have server auth.
# If not, I'll assume a simple header check or similar for now, but ideally this needs proper auth.
# I will use a placeholder dependency `get_current_server` which we might need to implement or mock.

@router.get("/commands/pending", response_model=List[PendingCommandResponse])
async def get_pending_commands(
    server_token: str, # passed in query or header
    ingest_token: bool = Depends(deps.verify_ingest_token), # Verify X-Ingest-Token header
    db: AsyncSession = Depends(deps.get_db),
):
    """
    Poll for pending commands.
    """
    # Verify token (Simple implementation)
    # Find server by token (assuming we have a token field or similar)
    # For now, let's assume we find the server by ID and validate a static secret or similar.
    # Since I can't easily modify GameServer model to add a token field right now without a migration,
    # I will assume the `server_token` IS the `server_id` for this MVP (NOT SECURE).
    # TODO: Implement proper Server Auth with API Keys.
    
    try:
        server_id = UUID(server_token)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid server token format")
        
    commands = await shop_service.get_pending_commands(db, server_id)
    return commands

@router.post("/commands/confirm")
async def confirm_command(
    server_token: str = Body(..., embed=True),
    order_id: UUID = Body(..., embed=True),
    ingest_token: bool = Depends(deps.verify_ingest_token), # Verify X-Ingest-Token header
    db: AsyncSession = Depends(deps.get_db),
):
    """
    Confirm command execution.
    """
    try:
        server_id = UUID(server_token)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid server token format")
        
    await shop_service.confirm_delivery(db, order_id, server_id)
    return {"status": "success"}

# --- Admin Endpoints ---

@router.get("/orders", response_model=List[ShopOrderResponse])
async def get_all_orders(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """
    Get all orders (history) for admins.
    """
    return await shop_service.get_all_orders(db, limit=limit, offset=offset)

@router.post("/categories", response_model=ShopCategoryResponse)
async def create_category(
    category_in: ShopCategoryCreate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """
    Create a new shop category.
    """
    return await shop_service.create_category(db, category_in)

@router.put("/categories/{category_id}", response_model=ShopCategoryResponse)
async def update_category(
    category_id: UUID,
    category_in: ShopCategoryUpdate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """
    Update a shop category.
    """
    return await shop_service.update_category(db, category_id, category_in)

@router.delete("/categories/{category_id}")
async def delete_category(
    category_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """
    Delete a shop category.
    """
    await shop_service.delete_category(db, category_id)
    return {"status": "success"}

@router.post("/items", response_model=ShopItemResponse)
async def create_item(
    item_in: ShopItemCreate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """
    Create a new shop item.
    """
    return await shop_service.create_item(db, item_in)

@router.put("/items/{item_id}", response_model=ShopItemResponse)
async def update_item(
    item_id: UUID,
    item_in: ShopItemUpdate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """
    Update a shop item.
    """
    return await shop_service.update_item(db, item_id, item_in)

@router.delete("/items/{item_id}")
async def delete_item(
    item_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """
    Delete a shop item.
    """
    await shop_service.delete_item(db, item_id)
    return {"status": "success"}
