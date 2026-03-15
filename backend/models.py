from sqlalchemy import BigInteger, Integer, String, DateTime, Text, CheckConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from datetime import datetime

class Base(DeclarativeBase):
    pass

class Player(Base):
    """
    Unified player table - ПОЛНАЯ СИНХРОНИЗАЦИЯ MC + TG
    Механики из MC плагина как эталон
    """
    __tablename__ = "players"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    
    # Identifiers
    minecraft_uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=True, index=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=True, index=True)
    username: Mapped[str] = mapped_column(String(64), nullable=True)
    
    # Core clicker data (СИНХРОНИЗИРОВАНО)
    cookies: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    per_click: Mapped[int] = mapped_column(BigInteger, default=1, nullable=False)
    total_clicks: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    click_level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    
    # Design settings (MC + TG)
    block_design: Mapped[int] = mapped_column(BigInteger, default=0)
    particle_design: Mapped[int] = mapped_column(BigInteger, default=0)
    menu_design: Mapped[int] = mapped_column(BigInteger, default=0)
    
    # Platform lock & activity tracking
    active_platform: Mapped[str] = mapped_column(String(10), nullable=True, index=True)
    last_activity: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    last_click_timestamp: Mapped[int] = mapped_column(BigInteger, nullable=True)
    clicks_this_second: Mapped[int] = mapped_column(Integer, default=0)
    last_move_timestamp: Mapped[int] = mapped_column(BigInteger, nullable=True)
    
    # Events (JSON string) - НОВОЕ!
    # Формат: {"type": "golden_cookie", "started_at": "...", "expires_at": "...", ...}
    active_events: Mapped[str] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        CheckConstraint(
            "active_platform IN ('minecraft', 'telegram') OR active_platform IS NULL",
            name='check_active_platform'
        ),
    )


class PlayerUpgrade(Base):
    """
    Player purchases from shops (СИНХРОНИЗИРОВАНО с MC)
    - per_click shop
    - block_design shop
    - particle_design shop
    - menu_design shop
    """
    __tablename__ = "player_upgrades"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    shop_type: Mapped[str] = mapped_column(String(32), nullable=False)
    item_id: Mapped[int] = mapped_column(Integer, nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=1)
    purchased_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
