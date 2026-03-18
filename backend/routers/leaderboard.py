from fastapi import APIRouter
from typing import List
from backend import db_queries
from backend.schemas import LeaderboardPlayer

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


@router.get("/", response_model=List[LeaderboardPlayer])
async def get_leaderboard(limit: int = 10):
    """
    Топ игроков по количеству печенек.
    Включает и Minecraft-игроков и TG-игроков (общая таблица).
    """
    rows = await db_queries.get_leaderboard(limit)
    return [
        LeaderboardPlayer(
            telegram_id=row.get("telegram_id"),
            username=row.get("name") or f"Player_{row.get('telegram_id', '?')}",
            balance=row["cookies"],
            total_clicks=row["clicker_clicks"],
        )
        for row in rows
    ]
