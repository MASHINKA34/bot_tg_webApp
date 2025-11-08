from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from backend.database import get_session
from backend.models import User, Farm
from backend.schemas import BuyFarmRequest, FarmResponse
from backend.config import settings
from typing import List

router = APIRouter(prefix="/farms", tags=["farms"])

FARM_TYPES = {
    "small_farm": {"name": "Мини-ферма", "cost": 500, "income": 50},
    "factory": {"name": "Завод", "cost": 2000, "income": 250},
    "corporation": {"name": "Корпорация", "cost": 10000, "income": 1500}
}

@router.get("/{telegram_id}", response_model=List[FarmResponse])
async def get_farms(telegram_id: int, db: AsyncSession = Depends(get_session)):
    user_result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = user_result.scalar_one_or_none()
    
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
        return []
    
    farms_result = await db.execute(select(Farm).where(Farm.user_id == user.id))
    farms = farms_result.scalars().all()
    
    now = datetime.utcnow()
    time_since_activity = (now - user.last_activity).total_seconds() / 3600
    
    farms_list = []
    for farm in farms:
        is_active = time_since_activity < settings.FARM_AFK_LIMIT_HOURS
        
        time_since_collect = (now - farm.last_collected).total_seconds() / 3600
        
        if time_since_activity >= settings.FARM_AFK_LIMIT_HOURS:
            production_time = max(0, time_since_collect - (time_since_activity - settings.FARM_AFK_LIMIT_HOURS))
        else:
            production_time = time_since_collect
        
        accumulated = int(farm.income_per_hour * production_time)
        
        farms_list.append(FarmResponse(
            id=farm.id,
            name=farm.name,
            level=farm.level,
            income_per_hour=farm.income_per_hour,
            accumulated=accumulated,
            is_active=is_active
        ))
    
    return farms_list

@router.post("/buy")
async def buy_farm(request: BuyFarmRequest, db: AsyncSession = Depends(get_session)):
    if request.farm_type not in FARM_TYPES:
        raise HTTPException(400, "Неизвестный тип фермы")
    
    user_result = await db.execute(select(User).where(User.telegram_id == request.telegram_id))
    user = user_result.scalar_one_or_none()
    
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
    
    farm_info = FARM_TYPES[request.farm_type]
    
    if user.balance < farm_info["cost"]:
        return {"success": False, "error": "Недостаточно средств"}

    existing_farm_result = await db.execute(
        select(Farm).where(Farm.user_id == user.id, Farm.farm_type == request.farm_type)
    )
    existing_farm = existing_farm_result.scalar_one_or_none()
    
    if existing_farm:

        existing_farm.level += 1
        existing_farm.income_per_hour = int(farm_info["income"] * existing_farm.level)
        user.balance -= farm_info["cost"]
        user.last_activity = datetime.utcnow()
        await db.commit()
        
        return {
            "success": True,
            "farm_id": existing_farm.id,
            "balance": user.balance,
            "level": existing_farm.level
        }
    else:
        new_farm = Farm(
            user_id=user.id,
            farm_type=request.farm_type,
            name=farm_info["name"],
            level=1,
            income_per_hour=farm_info["income"]
        )
        
        user.balance -= farm_info["cost"]
        user.last_activity = datetime.utcnow()
        
        db.add(new_farm)
        await db.commit()
        
        return {
            "success": True,
            "farm_id": new_farm.id,
            "balance": user.balance,
            "level": 1
        }

@router.post("/collect/{farm_id}")
async def collect_farm(farm_id: int, telegram_id: int, db: AsyncSession = Depends(get_session)):
    user_result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = user_result.scalar_one_or_none()
    
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
    
    farm_result = await db.execute(select(Farm).where(Farm.id == farm_id, Farm.user_id == user.id))
    farm = farm_result.scalar_one_or_none()
    
    if not farm:
        raise HTTPException(404, "Ферма не найдена")
    
    now = datetime.utcnow()
    time_since_activity = (now - user.last_activity).total_seconds() / 3600
    is_active = time_since_activity < settings.FARM_AFK_LIMIT_HOURS
    
    time_passed = (now - farm.last_collected).total_seconds() / 3600
    if is_active:
        earned = int(farm.income_per_hour * time_passed)
    else:
        active_time = max(0, settings.FARM_AFK_LIMIT_HOURS - time_since_activity)
        earned = int(farm.income_per_hour * active_time)
    
    user.balance += earned
    farm.last_collected = now
    user.last_activity = now
    
    await db.commit()
    
    return {"success": True, "earned": earned, "balance": user.balance}
