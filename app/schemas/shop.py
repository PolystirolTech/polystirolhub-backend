from typing import Optional, List
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel

# --- Shop Category Schemas ---

class ShopCategoryBase(BaseModel):
    name: str
    slug: Optional[str] = None
    icon_url: Optional[str] = None

class ShopCategoryCreate(ShopCategoryBase):
    pass

class ShopCategoryUpdate(ShopCategoryBase):
    pass

class ShopCategoryResponse(ShopCategoryBase):
    id: UUID
    created_at: datetime

    class Config:
        from_attributes = True

# --- Shop Item Schemas ---

class ShopItemBase(BaseModel):
    name: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    price: int
    command: str
    is_active: bool = True
    category_id: Optional[UUID] = None
    required_platform: Optional[str] = None # steam, minecraft, or None

class ShopItemCreate(ShopItemBase):
    game_type_ids: List[UUID] = []
    game_server_ids: List[UUID] = []

class ShopItemUpdate(ShopItemBase):
    game_type_ids: Optional[List[UUID]] = None
    game_server_ids: Optional[List[UUID]] = None

class ShopItemResponse(ShopItemBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    # We return IDs to keep it simple, or full objects if needed. 
    # For now, let's just assume the frontend might need to know availability.
    # But usually, the frontend filters items *before* showing them.
    
    class Config:
        from_attributes = True

# --- Shop Order Schemas ---

class ShopOrderCreate(BaseModel):
    item_id: UUID
    game_server_id: UUID

class ShopOrderResponse(BaseModel):
    id: UUID
    user_id: UUID
    item_id: UUID
    game_server_id: UUID
    price_paid: int
    status: str
    created_at: datetime
    delivered_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- Server Polling Schemas ---

class PendingCommandResponse(BaseModel):
    order_id: UUID
    command: str
    username: str
    target_username: Optional[str] = None # The specific game nickname (mc_name or steam_id) if available
    user_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True
