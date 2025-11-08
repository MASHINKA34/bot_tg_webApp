from sqlalchemy import BigInteger, Integer, Float, DateTime, String, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from datetime import datetime

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str] = mapped_column(String, nullable=True)
    
    balance: Mapped[int] = mapped_column(Integer, default=0)
    total_clicks: Mapped[int] = mapped_column(Integer, default=0)
    click_level: Mapped[int] = mapped_column(Integer, default=1)
    click_power: Mapped[int] = mapped_column(Integer, default=1)
    
    last_click_time: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    clicks_this_second: Mapped[int] = mapped_column(Integer, default=0)
    last_activity: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    last_daily_claim: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    daily_streak: Mapped[int] = mapped_column(Integer, default=0)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Farm(Base):
    __tablename__ = "farms"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    
    farm_type: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    level: Mapped[int] = mapped_column(Integer, default=1)
    income_per_hour: Mapped[int] = mapped_column(Integer)
    
    last_collected: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)