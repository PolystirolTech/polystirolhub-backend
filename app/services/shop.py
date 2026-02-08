from typing import List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from sqlalchemy.orm import selectinload
from fastapi import HTTPException

from app.models.shop import ShopItem, ShopOrder, ShopCategory
from app.models.game_server import GameServer, GameType
from app.models.user import User
from app.schemas.shop import (
    ShopOrderCreate, 
    PendingCommandResponse,
    ShopCategoryCreate, 
    ShopCategoryUpdate,
    ShopItemCreate,
    ShopItemUpdate
)
from app.core.currency import deduct_currency

# --- User / Public Services ---

async def get_categories(db: AsyncSession) -> List[ShopCategory]:
    """
    Get all shop categories.
    """
    query = select(ShopCategory).order_by(ShopCategory.name)
    result = await db.execute(query)
    return result.scalars().all()

async def get_all_items(db: AsyncSession) -> List[ShopItem]:
    """
    Get all shop items (for admin or global view).
    """
    query = select(ShopItem).options(
        selectinload(ShopItem.game_servers),
        selectinload(ShopItem.game_types)
    )
    result = await db.execute(query)
    return result.scalars().all()

async def get_items_for_server(db: AsyncSession, server_id: UUID) -> List[ShopItem]:
    """
    Get all shop items available for a specific server.
    """
    server = await db.get(GameServer, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    query = select(ShopItem).where(
        ShopItem.is_active
    ).options(
        selectinload(ShopItem.game_servers),
        selectinload(ShopItem.game_types)
    )
    
    result = await db.execute(query)
    all_items = result.scalars().all()
    
    available_items = []
    for item in all_items:
        server_ids = [s.id for s in item.game_servers]
        if server_id in server_ids:
            available_items.append(item)
            continue
            
        type_ids = [t.id for t in item.game_types]
        if server.game_type_id in type_ids:
            available_items.append(item)
            continue
            
    return available_items

async def buy_item(db: AsyncSession, user_id: UUID, order_in: ShopOrderCreate) -> ShopOrder:
    """
    Process a purchase:
    1. Validate item availability for the server.
    2. Validate user linked accounts (Steam/Minecraft) if required.
    3. Deduct currency.
    4. Create order with substituted command variables.
    """
    # 1. Get Item and Server
    item = await db.get(ShopItem, order_in.item_id)
    if not item or not item.is_active:
        raise HTTPException(status_code=404, detail="Item not found or inactive")
        
    server = await db.get(GameServer, order_in.game_server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
        
    # 2. Validate Availability
    await db.refresh(item, attribute_names=["game_servers", "game_types"])
    
    is_allowed = False
    if server.id in [s.id for s in item.game_servers]:
        is_allowed = True
    elif server.game_type_id in [t.id for t in item.game_types]:
        is_allowed = True
        
    if not is_allowed:
        raise HTTPException(status_code=400, detail="Item is not available for this server")
    
    # 3. Validate Linked Accounts & Prepare Variables
    user = await db.get(User, user_id)
    # Load relationships for checking linked accounts
    await db.refresh(user, attribute_names=["oauth_accounts", "external_links"])
    
    steam_id = None
    mc_name = None
    
    # Try to find Steam ID
    # Check OAuth (e.g. if logged in via Steam)
    for oauth in user.oauth_accounts:
        if oauth.provider == "steam":
            steam_id = oauth.provider_account_id
            break
    # Check External Links (if linked manually)
    if not steam_id:
        for link in user.external_links:
            if link.platform == "steam":
                steam_id = link.external_id
                break
                
    # Try to find Minecraft Name
    # Usually in ExternalLink with platform='minecraft'
    for link in user.external_links:
        if link.platform == "minecraft":
            mc_name = link.platform_username # Assuming we store nickname here
            if not mc_name:
                 # Fallback if we only stored UUID in external_id, but usually we need name for commands
                 pass
            break
            
    # Check Requirements
    if item.required_platform == "steam":
        if not steam_id:
            raise HTTPException(status_code=400, detail="Linked Steam account required for this item")
    elif item.required_platform == "minecraft":
        if not mc_name:
            raise HTTPException(status_code=400, detail="Linked Minecraft account required for this item")
            
    # 4. Deduct Currency (Atomic)
    try:
        await deduct_currency(db, user_id, item.price)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    # 5. Prepare Command
    final_command = item.command
    
    # Replace {username} with site username (default)
    final_command = final_command.replace("{username}", user.username)
    
    # Replace {steam_id} if available
    if steam_id:
        final_command = final_command.replace("{steam_id}", steam_id)
        
    # Replace {mc_name} if available
    if mc_name:
        final_command = final_command.replace("{mc_name}", mc_name)
    
    # Check if command still has unresolved variables that are required?
    # For now, we assume admin configured it correctly matching required_platform.
    
    # 6. Create Order
    order = ShopOrder(
        user_id=user_id,
        item_id=item.id,
        game_server_id=server.id,
        price_paid=item.price,
        status="PENDING",
        command=final_command
    )
    
    db.add(order)
    await db.commit()
    await db.refresh(order)
    
    return order

async def get_user_orders(db: AsyncSession, user_id: UUID) -> List[ShopOrder]:
    """
    Get purchase history for a user.
    """
    query = select(ShopOrder).where(
        ShopOrder.user_id == user_id
    ).order_by(desc(ShopOrder.created_at))
    
    # Load related item and server for display
    query = query.options(
        selectinload(ShopOrder.item),
        selectinload(ShopOrder.game_server)
    )
    
    result = await db.execute(query)
    return result.scalars().all()

async def get_pending_commands(db: AsyncSession, server_id: UUID) -> List[PendingCommandResponse]:
    """
    Fetch all pending commands for a specific server.
    """
    query = select(ShopOrder).where(
        ShopOrder.game_server_id == server_id,
        ShopOrder.status == "PENDING"
    ).options(selectinload(ShopOrder.user)) # Load user to get username/id
    
    result = await db.execute(query)
    orders = result.scalars().all()
    
    response = []
    for order in orders:
        response.append(PendingCommandResponse(
            order_id=order.id,
            command=order.command,
            username=order.user.username,
            user_id=order.user.id,
            created_at=order.created_at
        ))
        
    return response

async def confirm_delivery(db: AsyncSession, order_id: UUID, server_id: UUID):
    """
    Mark an order as delivered.
    Security: Ensure the server confirming is the one the order was for.
    """
    order = await db.get(ShopOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    if order.game_server_id != server_id:
        raise HTTPException(status_code=403, detail="Server mismatch")
        
    if order.status != "PENDING":
        # Already delivered or failed?
        return # Idempotent success
        
    order.status = "DELIVERED"
    order.delivered_at = func.now()
    
    await db.commit()

# --- Admin Services ---

async def get_all_orders(db: AsyncSession, limit: int = 100, offset: int = 0) -> List[ShopOrder]:
    """
    Get all orders (for admin history).
    """
    query = select(ShopOrder).order_by(desc(ShopOrder.created_at)).limit(limit).offset(offset)
    
    # Load relationships
    query = query.options(
        selectinload(ShopOrder.user),
        selectinload(ShopOrder.item),
        selectinload(ShopOrder.game_server)
    )
    
    result = await db.execute(query)
    return result.scalars().all()

async def create_category(db: AsyncSession, category_in: ShopCategoryCreate) -> ShopCategory:
    category = ShopCategory(**category_in.model_dump())
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category

async def update_category(db: AsyncSession, category_id: UUID, category_in: ShopCategoryUpdate) -> ShopCategory:
    category = await db.get(ShopCategory, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
        
    update_data = category_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(category, field, value)
        
    await db.commit()
    await db.refresh(category)
    return category

async def delete_category(db: AsyncSession, category_id: UUID):
    category = await db.get(ShopCategory, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
        
    await db.delete(category)
    await db.commit()

async def create_item(db: AsyncSession, item_in: ShopItemCreate) -> ShopItem:
    # Handle M2M relationships
    game_type_ids = item_in.game_type_ids
    game_server_ids = item_in.game_server_ids
    
    # Create item without relationships first
    item_data = item_in.model_dump(exclude={"game_type_ids", "game_server_ids"})
    item = ShopItem(**item_data)
    
    # Add relationships
    if game_type_ids:
        result = await db.execute(select(GameType).where(GameType.id.in_(game_type_ids)))
        game_types = result.scalars().all()
        item.game_types = game_types
        
    if game_server_ids:
        result = await db.execute(select(GameServer).where(GameServer.id.in_(game_server_ids)))
        game_servers = result.scalars().all()
        item.game_servers = game_servers
        
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item

async def update_item(db: AsyncSession, item_id: UUID, item_in: ShopItemUpdate) -> ShopItem:
    # Use selectinload to load relationships so we can update them
    query = select(ShopItem).where(ShopItem.id == item_id).options(
        selectinload(ShopItem.game_types),
        selectinload(ShopItem.game_servers)
    )
    result = await db.execute(query)
    item = result.scalar_one_or_none()
    
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
        
    # Handle M2M updates if provided
    if item_in.game_type_ids is not None:
        result = await db.execute(select(GameType).where(GameType.id.in_(item_in.game_type_ids)))
        game_types = result.scalars().all()
        item.game_types = list(game_types) # Convert to list to ensure it's compatible
        
    if item_in.game_server_ids is not None:
        result = await db.execute(select(GameServer).where(GameServer.id.in_(item_in.game_server_ids)))
        game_servers = result.scalars().all()
        item.game_servers = list(game_servers) # Convert to list
        
    # Update other fields
    update_data = item_in.model_dump(exclude={"game_type_ids", "game_server_ids"}, exclude_unset=True)
    for field, value in update_data.items():
        setattr(item, field, value)
        
    await db.commit()
    await db.refresh(item)
    return item

async def delete_item(db: AsyncSession, item_id: UUID):
    item = await db.get(ShopItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
        
    await db.delete(item)
    await db.commit()
