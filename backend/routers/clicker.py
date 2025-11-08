from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from backend.database import get_session
from backend.models import User
from backend.schemas import ClickRequest, UserStats
from backend.config import settings

router = APIRouter(prefix="/clicker", tags=["clicker"])

@router.post("/click")
async def process_click(request: ClickRequest, db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(User).where(User.telegram_id == request.telegram_id))
    user = result.scalar_one_or_none()
    
    if not user:
        user = User(
            telegram_id=request.telegram_id,
            balance=0,
            total_clicks=0,
            click_level=1,
            click_power=settings.CLICK_VALUE
        )
        db.add(user)
        await db.flush()
    
    clicks_count = request.clicks
    earned = user.click_power * clicks_count
    
    user.balance += earned
    user.total_clicks += clicks_count
    user.last_activity = datetime.utcnow()
    
    await db.commit()
    
    return {
        "success": True,
        "earned": earned,
        "balance": user.balance,
        "total_clicks": user.total_clicks,
        "click_power": user.click_power,
        "clicks_processed": clicks_count
    }

@router.get("/stats/{telegram_id}")
async def get_stats(telegram_id: int, db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    
    if not user:
        user = User(
            telegram_id=telegram_id,
            balance=0,
            total_clicks=0,
            click_level=1,
            click_power=settings.CLICK_VALUE
        )
        db.add(user)
        await db.commit()
    
    upgrade_cost = int(settings.CLICK_UPGRADE_BASE_COST * (settings.CLICK_UPGRADE_MULTIPLIER ** (user.click_level - 1)))
    
    all_users = await db.execute(select(User).order_by(User.balance.desc()))
    users_list = all_users.scalars().all()
    rank = next((i+1 for i, u in enumerate(users_list) if u.telegram_id == telegram_id), 0)
    
    return {
        "balance": user.balance,
        "total_clicks": user.total_clicks,
        "click_level": user.click_level,
        "click_power": user.click_power,
        "upgrade_cost": upgrade_cost,
        "rank": rank
    }

@router.post("/upgrade")
async def upgrade_click(request: ClickRequest, db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(User).where(User.telegram_id == request.telegram_id))
    user = result.scalar_one_or_none()
    
    if not user:
        user = User(
            telegram_id=request.telegram_id,
            balance=0,
            total_clicks=0,
            click_level=1,
            click_power=settings.CLICK_VALUE
        )
        db.add(user)
        await db.flush()
    
    upgrade_cost = int(settings.CLICK_UPGRADE_BASE_COST * (settings.CLICK_UPGRADE_MULTIPLIER ** (user.click_level - 1)))
    
    if user.balance < upgrade_cost:
        return {"success": False, "error": f"Недостаточно средств"}
    
    user.balance -= upgrade_cost
    user.click_level += 1
    user.click_power = user.click_level * settings.CLICK_VALUE
    user.last_activity = datetime.utcnow()
    
    await db.commit()
    
    next_cost = int(settings.CLICK_UPGRADE_BASE_COST * (settings.CLICK_UPGRADE_MULTIPLIER ** user.click_level))
    
    return {
        "success": True,
        "new_level": user.click_level,
        "new_power": user.click_power,
        "balance": user.balance,
        "next_upgrade_cost": next_cost
    }
