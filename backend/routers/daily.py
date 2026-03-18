from fastapi import APIRouter
from datetime import datetime, timezone
from backend import db_queries
from backend.config import settings
import logging

router = APIRouter(prefix="/daily", tags=["daily"])
logger = logging.getLogger(__name__)


@router.post("/claim/{telegram_id}")
async def claim_daily(telegram_id: int):
    """Забрать ежедневный бонус (раз в 24 часа, стрик сбрасывается после 48 ч)."""
    player = await db_queries.get_or_create_player(telegram_id)
    player_uuid = player["uuid"]

    now = datetime.now(timezone.utc)
    last_claim = player.get("last_daily_claim")

    if last_claim:
        # last_claim может быть naive datetime (PostgreSQL TIMESTAMP WITHOUT TIME ZONE)
        if last_claim.tzinfo is None:
            last_claim = last_claim.replace(tzinfo=timezone.utc)
        time_since_hours = (now - last_claim).total_seconds() / 3600

        if time_since_hours < 24:
            hours_left = 24 - time_since_hours
            return {
                "success": False,
                "error": "Бонус уже забран",
                "time_left_hours": round(hours_left, 2),
            }

        # Сбросить стрик если прошло больше 48 часов
        if time_since_hours > 48:
            await db_queries.reset_streak(player_uuid)
            player = await db_queries.get_player_by_telegram_id(telegram_id)

    current_streak = (player.get("daily_streak") or 0)
    new_streak = current_streak + 1
    bonus = int(
        settings.DAILY_BONUS_BASE
        * (settings.DAILY_BONUS_STREAK_MULTIPLIER ** (new_streak - 1))
    )

    new_balance = await db_queries.claim_daily_bonus(player_uuid, bonus, new_streak)

    logger.info(f"Daily bonus: telegram_id={telegram_id}, streak={new_streak}, bonus={bonus}")

    return {
        "success": True,
        "bonus": bonus,
        "streak": new_streak,
        "balance": new_balance,
    }


@router.get("/status/{telegram_id}")
async def get_daily_status(telegram_id: int):
    """Проверить доступность дневного бонуса."""
    player = await db_queries.get_or_create_player(telegram_id)
    last_claim = player.get("last_daily_claim")

    if not last_claim:
        return {
            "available": True,
            "streak": player.get("daily_streak") or 0,
            "time_left_seconds": 0,
        }

    now = datetime.now(timezone.utc)
    if last_claim.tzinfo is None:
        last_claim = last_claim.replace(tzinfo=timezone.utc)

    time_since = (now - last_claim).total_seconds()
    time_left = max(0.0, (24 * 3600) - time_since)

    return {
        "available": time_left == 0,
        "streak": player.get("daily_streak") or 0,
        "time_left_seconds": int(time_left),
    }
