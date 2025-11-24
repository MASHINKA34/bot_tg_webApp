from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.database import get_session
from backend.models import User
from backend.schemas import LeaderboardPlayer
from typing import List

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])

@router.get("/", response_model=List[LeaderboardPlayer])
async def get_leaderboard(limit: int = 10, db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(User).order_by(User.balance.desc()).limit(limit))
    users = result.scalars().all()
    
    return [
        LeaderboardPlayer(
            telegram_id=user.telegram_id,
            username=user.username or f"Player_{user.telegram_id}",
            balance=user.balance,
            total_clicks=user.total_clicks
        )
        for user in users
    ]
