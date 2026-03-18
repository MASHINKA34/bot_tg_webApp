from fastapi import APIRouter, HTTPException
from typing import List
from backend import db_queries
from backend.schemas import ReferralInfo, ReferralStats, ActivateReferralRequest
from backend.config import settings
from backend.db_queries import generate_referral_code
from backend.database import get_pool
import logging

router = APIRouter(prefix="/referral", tags=["referral"])
logger = logging.getLogger(__name__)


@router.get("/info/{telegram_id}", response_model=ReferralInfo)
async def get_referral_info(telegram_id: int):
    """Получить реферальный код и статистику."""
    player = await db_queries.get_or_create_player(telegram_id)

    ref_code = player.get("referral_code")
    if not ref_code:
        ref_code = generate_referral_code(telegram_id, settings.SECRET_KEY)
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE cookieclicker_players SET referral_code = $1 WHERE uuid = $2",
                ref_code,
                player["uuid"],
            )

    return ReferralInfo(
        referral_code=ref_code,
        referral_count=player.get("referral_count") or 0,
        referral_earnings=player.get("referral_earnings") or 0,
        bonus_per_referral=settings.REFERRAL_BONUS,
    )


@router.get("/list/{telegram_id}", response_model=List[ReferralStats])
async def get_referrals(telegram_id: int):
    """Список приглашённых игроков."""
    player = await db_queries.get_player_by_telegram_id(telegram_id)
    if not player:
        return []

    referrals = await db_queries.get_referrals_of(player["uuid"])
    return [
        ReferralStats(
            telegram_id=ref.get("telegram_id"),
            username=ref.get("name") or f"Player_{ref.get('telegram_id', '?')}",
            balance=ref["cookies"],
            joined_at=(
                ref["last_activity"].strftime("%d.%m.%Y")
                if ref.get("last_activity")
                else "—"
            ),
        )
        for ref in referrals
    ]


@router.post("/activate")
async def activate_referral(request: ActivateReferralRequest):
    """Использовать реферальный код."""
    user = await db_queries.get_or_create_player(request.telegram_id)
    user_uuid = user["uuid"]

    if user.get("referrer_uuid"):
        return {"success": False, "error": "Вы уже использовали реферальный код"}

    referrer = await db_queries.get_player_by_referral_code(request.referral_code)
    if not referrer:
        return {"success": False, "error": "Неверный реферальный код"}

    if referrer["uuid"] == user_uuid:
        return {"success": False, "error": "Нельзя использовать свой реферальный код"}

    await db_queries.activate_referral(
        user_uuid=user_uuid,
        referrer_uuid=referrer["uuid"],
        user_bonus=settings.REFERRAL_BONUS_FOR_NEW_USER,
        referrer_bonus=settings.REFERRAL_BONUS,
    )

    logger.info(
        f"Реферал: {request.telegram_id} → {referrer.get('telegram_id')}, "
        f"бонусы: user={settings.REFERRAL_BONUS_FOR_NEW_USER}, referrer={settings.REFERRAL_BONUS}"
    )

    return {
        "success": True,
        "referrer_bonus": settings.REFERRAL_BONUS,
        "user_bonus": settings.REFERRAL_BONUS_FOR_NEW_USER,
        "referrer_username": referrer.get("name") or f"Player_{referrer.get('telegram_id', '?')}",
    }
