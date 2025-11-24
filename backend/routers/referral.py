from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from backend.database import get_session
from backend.models import User
from backend.schemas import ReferralInfo, ReferralStats, ActivateReferralRequest
from backend.config import settings
from typing import List
import hashlib

router = APIRouter(prefix="/referral", tags=["referral"])

def generate_referral_code(telegram_id: int) -> str:
    hash_input = f"{telegram_id}{settings.SECRET_KEY}"
    return hashlib.md5(hash_input.encode()).hexdigest()[:8].upper()

@router.get("/info/{telegram_id}", response_model=ReferralInfo)
async def get_referral_info(telegram_id: int, db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    
    if not user:
        referral_code = generate_referral_code(telegram_id)
        user = User(
            telegram_id=telegram_id,
            balance=0,
            total_clicks=0,
            click_level=1,
            click_power=settings.CLICK_VALUE,
            referral_code=referral_code
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    if not user.referral_code:
        user.referral_code = generate_referral_code(telegram_id)
        await db.commit()
    
    return ReferralInfo(
        referral_code=user.referral_code,
        referral_count=user.referral_count,
        referral_earnings=user.referral_earnings,
        bonus_per_referral=settings.REFERRAL_BONUS
    )

@router.get("/list/{telegram_id}", response_model=List[ReferralStats])
async def get_referrals(telegram_id: int, db: AsyncSession = Depends(get_session)):
    result = await db.execute(
        select(User).where(User.referrer_id == telegram_id)
    )
    referrals = result.scalars().all()
    
    return [
        ReferralStats(
            telegram_id=ref.telegram_id,
            username=ref.username or f"Player_{ref.telegram_id}",
            balance=ref.balance,
            joined_at=ref.created_at.strftime("%d.%m.%Y")
        )
        for ref in referrals
    ]

@router.post("/activate")
async def activate_referral(request: ActivateReferralRequest, db: AsyncSession = Depends(get_session)):
    user_result = await db.execute(
        select(User).where(User.telegram_id == request.telegram_id)
    )
    user = user_result.scalar_one_or_none()
    
    if not user:
        referral_code = generate_referral_code(request.telegram_id)
        user = User(
            telegram_id=request.telegram_id,
            balance=0,
            total_clicks=0,
            click_level=1,
            click_power=settings.CLICK_VALUE,
            referral_code=referral_code
        )
        db.add(user)
        await db.flush()

    if user.referrer_id is not None:
        return {
            "success": False,
            "error": "Вы уже использовали реферальный код"
        }

    referrer_result = await db.execute(
        select(User).where(User.referral_code == request.referral_code)
    )
    referrer = referrer_result.scalar_one_or_none()
    
    if not referrer:
        return {
            "success": False,
            "error": "Неверный реферальный код"
        }

    if referrer.telegram_id == request.telegram_id:
        return {
            "success": False,
            "error": "Нельзя использовать свой реферальный код"
        }
    
    user.referrer_id = referrer.telegram_id

    referrer.referral_count += 1
    referrer.balance += settings.REFERRAL_BONUS
    referrer.referral_earnings += settings.REFERRAL_BONUS
    
    user.balance += settings.REFERRAL_BONUS_FOR_NEW_USER
    
    await db.commit()
    
    return {
        "success": True,
        "referrer_bonus": settings.REFERRAL_BONUS,
        "user_bonus": settings.REFERRAL_BONUS_FOR_NEW_USER,
        "referrer_username": referrer.username or f"Player_{referrer.telegram_id}"
    }
