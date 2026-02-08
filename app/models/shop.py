from sqlalchemy import Column, ForeignKey, Integer, String, Text, Boolean, DateTime, Table
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.db.base_class import Base

# Association tables for Many-to-Many relationships
shop_item_game_types = Table(
    "shop_item_game_types",
    Base.metadata,
    Column("shop_item_id", UUID(as_uuid=True), ForeignKey("shop_items.id"), primary_key=True),
    Column("game_type_id", UUID(as_uuid=True), ForeignKey("game_types.id"), primary_key=True),
)

shop_item_game_servers = Table(
    "shop_item_game_servers",
    Base.metadata,
    Column("shop_item_id", UUID(as_uuid=True), ForeignKey("shop_items.id"), primary_key=True),
    Column("game_server_id", UUID(as_uuid=True), ForeignKey("game_servers.id"), primary_key=True),
)

class ShopCategory(Base):
    __tablename__ = "shop_categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, index=True)
    icon_url = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    items = relationship("ShopItem", back_populates="category", cascade="all, delete-orphan")

class ShopItem(Base):
    __tablename__ = "shop_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category_id = Column(UUID(as_uuid=True), ForeignKey("shop_categories.id"), nullable=True)
    
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    image_url = Column(String, nullable=True)
    price = Column(Integer, nullable=False) # Price in internal currency
    is_active = Column(Boolean, default=True)

    # Command template, e.g., "give {username} diamond 1"
    command = Column(String, nullable=False) 
    
    # Validation requirement
    # "steam" -> requires linked Steam account
    # "minecraft" -> requires linked Minecraft account (via ExternalLink or OAuth)
    # null -> no specific requirement
    required_platform = Column(String, nullable=True) 
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    category = relationship("ShopCategory", back_populates="items")
    
    # Many-to-Many relationships
    game_types = relationship("GameType", secondary=shop_item_game_types, backref="shop_items")
    game_servers = relationship("GameServer", secondary=shop_item_game_servers, backref="shop_items")

class ShopOrder(Base):
    __tablename__ = "shop_orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    item_id = Column(UUID(as_uuid=True), ForeignKey("shop_items.id"), nullable=False)
    game_server_id = Column(UUID(as_uuid=True), ForeignKey("game_servers.id"), nullable=False) # Where to deliver
    
    price_paid = Column(Integer, nullable=False)
    status = Column(String, default="PENDING", index=True) # PENDING, DELIVERED, FAILED
    
    # Snapshot of the command at the time of purchase (optional, but good for history)
    command = Column(String, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    
    user = relationship("User", backref="orders")
    item = relationship("ShopItem")
    game_server = relationship("GameServer")
