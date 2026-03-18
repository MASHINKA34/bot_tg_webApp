"""
link.py — привязка Minecraft аккаунта к Telegram.

Эндпоинты:
  GET  /api/link/preview   — проверить оба аккаунта и вернуть их статистику
  POST /api/link/minecraft — выполнить привязку с выбором источника прогресса

source в POST:
  "minecraft" — сохранить прогресс Minecraft (cookies/per_click/clicker_clicks из MC)
  "telegram"  — сохранить прогресс Telegram  (cookies/per_click/clicker_clicks из TG)
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from backend.database import get_pool
import logging

router = APIRouter(prefix="/link", tags=["link"])
logger = logging.getLogger(__name__)


class LinkRequest(BaseModel):
    telegram_id: int
    minecraft_username: str
    source: str = "minecraft"  # "minecraft" или "telegram"


# ─────────────────────────────────────────────
# Preview: показать оба аккаунта до привязки
# ─────────────────────────────────────────────

@router.get("/preview")
async def preview_link(telegram_id: int, minecraft_username: str):
    """
    Вернуть статистику обоих аккаунтов для отображения выбора.
    Не изменяет данные в БД.
    """
    pool = get_pool()
    async with pool.acquire() as conn:

        # Найти MC игрока (ещё не привязанного)
        mc_row = await conn.fetchrow(
            """
            SELECT * FROM cookieclicker_players
            WHERE LOWER(name) = LOWER($1) AND telegram_id IS NULL
            """,
            minecraft_username,
        )

        if not mc_row:
            already = await conn.fetchrow(
                "SELECT telegram_id FROM cookieclicker_players WHERE LOWER(name) = LOWER($1)",
                minecraft_username,
            )
            if already and already["telegram_id"] == telegram_id:
                return {"success": False, "error": "Этот Minecraft аккаунт уже привязан к вашему Telegram"}
            if already and already["telegram_id"] is not None:
                return {"success": False, "error": "Этот Minecraft аккаунт уже привязан к другому Telegram"}
            return {
                "success": False,
                "error": (
                    f"Minecraft игрок '{minecraft_username}' не найден. "
                    f"Убедитесь что имя написано точно и вы хотя бы раз заходили на сервер."
                ),
            }

        # Найти TG игрока
        tg_row = await conn.fetchrow(
            "SELECT * FROM cookieclicker_players WHERE telegram_id = $1",
            telegram_id,
        )

        return {
            "success": True,
            "mc_player": {
                "name": mc_row["name"],
                "cookies": mc_row["cookies"],
                "per_click": mc_row["per_click"],
                "clicker_clicks": mc_row["clicker_clicks"],
            },
            "tg_player": {
                "cookies": tg_row["cookies"],
                "per_click": tg_row["per_click"],
                "click_level": tg_row.get("click_level") or 1,
                "clicker_clicks": tg_row["clicker_clicks"] or 0,
            } if tg_row else None,
        }


# ─────────────────────────────────────────────
# Link: выполнить привязку
# ─────────────────────────────────────────────

@router.post("/minecraft")
async def link_minecraft(request: LinkRequest):
    """
    Привязать Minecraft аккаунт к Telegram аккаунту.

    source="minecraft" — взять cookies/per_click/clicker_clicks из MC строки.
    source="telegram"  — взять cookies/per_click/clicker_clicks из TG строки.

    В любом случае сохраняются TG-специфичные данные:
      click_level, daily_streak, referral_code, referrer_uuid, tg_farms и т.д.
    """
    pool = get_pool()
    async with pool.acquire() as conn:

        # 1. Найти строку Minecraft (telegram_id IS NULL, имя совпадает)
        mc_row = await conn.fetchrow(
            """
            SELECT * FROM cookieclicker_players
            WHERE LOWER(name) = LOWER($1) AND telegram_id IS NULL
            """,
            request.minecraft_username,
        )

        if not mc_row:
            already = await conn.fetchrow(
                "SELECT telegram_id FROM cookieclicker_players WHERE LOWER(name) = LOWER($1)",
                request.minecraft_username,
            )
            if already and already["telegram_id"] == request.telegram_id:
                return {"success": False, "error": "Этот Minecraft аккаунт уже привязан к вашему Telegram"}
            if already and already["telegram_id"] is not None:
                return {"success": False, "error": "Этот Minecraft аккаунт уже привязан к другому Telegram"}
            return {
                "success": False,
                "error": (
                    f"Minecraft игрок '{request.minecraft_username}' не найден. "
                    f"Убедитесь что имя написано точно и вы хотя бы раз заходили на сервер."
                ),
            }

        mc_uuid = mc_row["uuid"]

        # 2. Найти текущую TG-only строку (если есть)
        tg_row = await conn.fetchrow(
            "SELECT * FROM cookieclicker_players WHERE telegram_id = $1",
            request.telegram_id,
        )

        async with conn.transaction():
            if tg_row:
                tg_uuid = tg_row["uuid"]

                # ── Выбор источника прогресса ───────────────────────────────
                if request.source == "telegram":
                    # Берём cookies/per_click из TG, остальное из MC
                    final_cookies       = tg_row["cookies"] or 0
                    final_per_click     = tg_row["per_click"] or 1
                    final_clicker_clicks = tg_row["clicker_clicks"] or 0
                    logger.info(
                        f"Источник: Telegram — cookies={final_cookies}, "
                        f"per_click={final_per_click}"
                    )
                else:
                    # source="minecraft" (по умолчанию)
                    # Берём cookies/per_click из MC строки в БД
                    final_cookies       = mc_row["cookies"]
                    final_per_click     = mc_row["per_click"] or 1
                    final_clicker_clicks = mc_row["clicker_clicks"]
                    logger.info(
                        f"Источник: Minecraft — cookies={final_cookies}, "
                        f"per_click={final_per_click}"
                    )

                # ── TG-специфичные поля всегда берём из TG строки ───────────
                final_click_level   = tg_row.get("click_level") or 1
                final_daily_streak  = tg_row.get("daily_streak") or 0
                final_last_daily    = tg_row.get("last_daily_claim")
                final_ref_code      = mc_row.get("referral_code") or tg_row.get("referral_code")
                final_ref_uuid      = mc_row.get("referrer_uuid") or tg_row.get("referrer_uuid")
                final_ref_count     = (mc_row.get("referral_count") or 0) + (tg_row.get("referral_count") or 0)
                final_ref_earn      = (mc_row.get("referral_earnings") or 0) + (tg_row.get("referral_earnings") or 0)

                # Шаг 1: Перенести фермы TG на Minecraft UUID
                await conn.execute(
                    "UPDATE tg_farms SET player_uuid = $1 WHERE player_uuid = $2",
                    mc_uuid, tg_uuid,
                )

                # Шаг 2: Удалить platform_lock старого TG UUID
                await conn.execute(
                    "DELETE FROM platform_locks WHERE player_uuid = $1::uuid",
                    tg_uuid,
                )

                # Шаг 3: Удалить старую TG-only строку (снимает UNIQUE constraint на telegram_id)
                await conn.execute(
                    "DELETE FROM cookieclicker_players WHERE uuid = $1",
                    tg_uuid,
                )

                # Шаг 4: Обновить MC строку — telegram_id уже свободен
                await conn.execute(
                    """
                    UPDATE cookieclicker_players SET
                        telegram_id       = $1,
                        cookies           = $2,
                        per_click         = $3,
                        clicker_clicks    = $4,
                        click_level       = $5,
                        daily_streak      = $6,
                        last_daily_claim  = $7,
                        referral_code     = $8,
                        referrer_uuid     = $9,
                        referral_count    = $10,
                        referral_earnings = $11,
                        last_activity     = NOW()
                    WHERE uuid = $12
                    """,
                    request.telegram_id,
                    final_cookies,
                    final_per_click,
                    final_clicker_clicks,
                    final_click_level,
                    final_daily_streak,
                    final_last_daily,
                    final_ref_code,
                    final_ref_uuid,
                    final_ref_count,
                    final_ref_earn,
                    mc_uuid,
                )

                logger.info(
                    f"Аккаунты объединены: TG {request.telegram_id} → MC '{mc_row['name']}' "
                    f"(source={request.source}, cookies={final_cookies})"
                )

            else:
                # TG аккаунта не было — просто привязываем telegram_id к MC строке
                # click_level ставим 1 если в MC не было
                await conn.execute(
                    """
                    UPDATE cookieclicker_players SET
                        telegram_id  = $1,
                        click_level  = COALESCE(click_level, 1),
                        last_activity = NOW()
                    WHERE uuid = $2
                    """,
                    request.telegram_id,
                    mc_uuid,
                )
                logger.info(f"TG {request.telegram_id} привязан к MC '{mc_row['name']}' (нет TG строки)")

        return {
            "success": True,
            "mc_name": mc_row["name"],
            "mc_uuid": mc_uuid,
            "source": request.source,
            "message": f"Minecraft аккаунт '{mc_row['name']}' успешно привязан!",
        }
