from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from backend.database import get_session
from backend.models import User
from backend.config import settings

router = APIRouter(prefix="/daily", tags=["daily"])

@router.post("/claim/{telegram_id}")
async def claim_daily(telegram_id: int, db: AsyncSession = Depends(get_session)):
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
        await db.flush()
    
    now = datetime.utcnow()
    
    if user.last_daily_claim:
        time_since = (now - user.last_daily_claim).total_seconds() / 3600
        if time_since < 24:
            hours_left = 24 - time_since
            return {
                "success": False, 
                "error": "Бонус уже забран",
                "time_left_hours": hours_left
            }
        
        if time_since > 48:
            user.daily_streak = 0
    
    user.daily_streak += 1
    bonus = int(settings.DAILY_BONUS_BASE * (settings.DAILY_BONUS_STREAK_MULTIPLIER ** (user.daily_streak - 1)))
    
    user.balance += bonus
    user.last_daily_claim = now
    user.last_activity = now
    
    await db.commit()
    
    return {
        "success": True,
        "bonus": bonus,
        "streak": user.daily_streak,
        "balance": user.balance
    }

@router.get("/status/{telegram_id}")
async def get_daily_status(telegram_id: int, db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    
    if not user or not user.last_daily_claim:
        return {
            "available": True,
            "streak": user.daily_streak if user else 0,
            "time_left_seconds": 0
        }
    
    now = datetime.utcnow()
    time_since = (now - user.last_daily_claim).total_seconds()
    time_left = max(0, (24 * 3600) - time_since)
    
    return {
        "available": time_left == 0,
        "streak": user.daily_streak,
        "time_left_seconds": int(time_left)
    }