"""
db_queries.py — все запросы к PostgreSQL через asyncpg.
Таблица: cookieclicker_players (общая с Minecraft плагином).
Дополнительные TG-таблицы: tg_farms.
"""

import uuid
import hashlib
import logging
from datetime import datetime
from typing import Optional

from backend.database import get_pool
from backend.config import settings

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def generate_referral_code(telegram_id: int, secret_key: str) -> str:
    hash_input = f"{telegram_id}{secret_key}"
    return hashlib.md5(hash_input.encode()).hexdigest()[:8].upper()


# ─────────────────────────────────────────────
# Player CRUD
# ─────────────────────────────────────────────

async def get_player_by_telegram_id(telegram_id: int) -> Optional[dict]:
    """Найти игрока по telegram_id. Возвращает dict или None."""
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM cookieclicker_players WHERE telegram_id = $1",
            telegram_id,
        )
        return dict(row) if row else None


async def get_or_create_player(telegram_id: int, username: str = None) -> dict:
    """
    Вернуть существующего игрока или создать нового TG-игрока.
    Новые TG-игроки получают случайный UUID (не связан с Minecraft до ручной привязки).
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM cookieclicker_players WHERE telegram_id = $1",
            telegram_id,
        )
        if row:
            return dict(row)

        new_uuid = str(uuid.uuid4())
        display_name = username or f"TG_{telegram_id}"
        ref_code = generate_referral_code(telegram_id, settings.SECRET_KEY)

        row = await conn.fetchrow(
            """
            INSERT INTO cookieclicker_players
                (uuid, name, cookies, per_click, clicker_clicks,
                 block_design, particle_design, menu_design,
                 telegram_id, click_level, last_activity, referral_code,
                 daily_streak, referral_count, referral_earnings,
                 clicks_this_second)
            VALUES
                ($1, $2, 0, $3, 0,
                 0, 0, 0,
                 $4, 1, NOW(), $5,
                 0, 0, 0,
                 0)
            RETURNING *
            """,
            new_uuid,
            display_name,
            settings.CLICK_VALUE,
            telegram_id,
            ref_code,
        )
        logger.info(f"Создан новый TG-игрок: telegram_id={telegram_id}, uuid={new_uuid}")
        return dict(row)


async def get_player_uuid(telegram_id: int) -> Optional[str]:
    """Быстро вернуть UUID игрока по telegram_id."""
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT uuid FROM cookieclicker_players WHERE telegram_id = $1",
            telegram_id,
        )
        return row["uuid"] if row else None


# ─────────────────────────────────────────────
# Click / stats updates
# ─────────────────────────────────────────────

async def update_after_click(
    player_uuid: str,
    clicks: int,
    earned: int,
    now_ms: int,
    clicks_this_second: int,
    active_events_json: Optional[str],
) -> dict:
    """Атомарно обновить статистику после успешного клика."""
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE cookieclicker_players
            SET
                cookies           = cookies + $2,
                clicker_clicks    = clicker_clicks + $3,
                last_activity     = NOW(),
                last_click_timestamp = $4,
                clicks_this_second   = $5,
                active_events        = $6
            WHERE uuid = $1
            RETURNING cookies, clicker_clicks, per_click, click_level
            """,
            player_uuid,
            earned,
            clicks,
            now_ms,
            clicks_this_second,
            active_events_json,
        )
        return dict(row) if row else {}


async def upgrade_click_power(player_uuid: str, cost: int, new_level: int, new_per_click: int) -> dict:
    """Апгрейд силы клика: снять монеты, увеличить уровень."""
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE cookieclicker_players
            SET cookies    = cookies - $2,
                click_level = $3,
                per_click   = $4,
                last_activity = NOW()
            WHERE uuid = $1 AND cookies >= $2
            RETURNING cookies, click_level, per_click
            """,
            player_uuid,
            cost,
            new_level,
            new_per_click,
        )
        return dict(row) if row else {}


async def get_player_rank(cookies: int) -> int:
    """Место игрока в топе по количеству печенек."""
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COUNT(*) AS cnt FROM cookieclicker_players WHERE cookies > $1",
            cookies,
        )
        return (row["cnt"] + 1) if row else 1


# ─────────────────────────────────────────────
# Daily bonus
# ─────────────────────────────────────────────

async def claim_daily_bonus(player_uuid: str, bonus: int, new_streak: int) -> int:
    """Начислить дневной бонус и обновить стрик. Возвращает новый баланс."""
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE cookieclicker_players
            SET cookies          = cookies + $2,
                last_daily_claim = NOW(),
                daily_streak     = $3,
                last_activity    = NOW()
            WHERE uuid = $1
            RETURNING cookies
            """,
            player_uuid,
            bonus,
            new_streak,
        )
        return row["cookies"] if row else 0


async def reset_streak(player_uuid: str) -> None:
    """Сбросить стрик если прошло >48 часов."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE cookieclicker_players SET daily_streak = 0 WHERE uuid = $1",
            player_uuid,
        )


# ─────────────────────────────────────────────
# Farms
# ─────────────────────────────────────────────

async def get_farms(player_uuid: str) -> list:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM tg_farms WHERE player_uuid = $1",
            player_uuid,
        )
        return [dict(r) for r in rows]


async def get_farm_by_id(farm_id: int, player_uuid: str) -> Optional[dict]:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM tg_farms WHERE id = $1 AND player_uuid = $2",
            farm_id,
            player_uuid,
        )
        return dict(row) if row else None


async def get_farm_by_type(player_uuid: str, farm_type: str) -> Optional[dict]:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM tg_farms WHERE player_uuid = $1 AND farm_type = $2",
            player_uuid,
            farm_type,
        )
        return dict(row) if row else None


async def buy_farm(player_uuid: str, farm_type: str, farm_name: str, cost: int, income: int) -> dict:
    """Купить новую ферму и снять монеты."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE cookieclicker_players SET cookies = cookies - $1, last_activity = NOW() WHERE uuid = $2",
                cost,
                player_uuid,
            )
            row = await conn.fetchrow(
                """
                INSERT INTO tg_farms (player_uuid, farm_type, farm_name, level, income_per_hour)
                VALUES ($1, $2, $3, 1, $4)
                RETURNING *
                """,
                player_uuid,
                farm_type,
                farm_name,
                income,
            )
            bal = await conn.fetchrow(
                "SELECT cookies FROM cookieclicker_players WHERE uuid = $1", player_uuid
            )
            return {"farm": dict(row), "balance": bal["cookies"]}


async def upgrade_farm(farm_id: int, player_uuid: str, cost: int, new_level: int, new_income: int) -> dict:
    """Улучшить существующую ферму."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE cookieclicker_players SET cookies = cookies - $1, last_activity = NOW() WHERE uuid = $2",
                cost,
                player_uuid,
            )
            await conn.execute(
                "UPDATE tg_farms SET level = $1, income_per_hour = $2 WHERE id = $3",
                new_level,
                new_income,
                farm_id,
            )
            bal = await conn.fetchrow(
                "SELECT cookies FROM cookieclicker_players WHERE uuid = $1", player_uuid
            )
            return {"balance": bal["cookies"], "level": new_level}


async def collect_farm_income(farm_id: int, player_uuid: str, earned: int) -> dict:
    """Собрать доход фермы."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE tg_farms SET last_collected = NOW() WHERE id = $1",
                farm_id,
            )
            row = await conn.fetchrow(
                """
                UPDATE cookieclicker_players
                SET cookies = cookies + $1, last_activity = NOW()
                WHERE uuid = $2
                RETURNING cookies
                """,
                earned,
                player_uuid,
            )
            return {"earned": earned, "balance": row["cookies"]}


# ─────────────────────────────────────────────
# Leaderboard
# ─────────────────────────────────────────────

async def get_leaderboard(limit: int = 10) -> list:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT telegram_id, name, cookies, clicker_clicks
            FROM cookieclicker_players
            ORDER BY cookies DESC
            LIMIT $1
            """,
            limit,
        )
        return [dict(r) for r in rows]


# ─────────────────────────────────────────────
# Referral
# ─────────────────────────────────────────────

async def get_player_by_referral_code(code: str) -> Optional[dict]:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM cookieclicker_players WHERE referral_code = $1",
            code,
        )
        return dict(row) if row else None


async def get_referrals_of(referrer_uuid: str) -> list:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM cookieclicker_players WHERE referrer_uuid = $1",
            referrer_uuid,
        )
        return [dict(r) for r in rows]


async def activate_referral(
    user_uuid: str,
    referrer_uuid: str,
    user_bonus: int,
    referrer_bonus: int,
) -> None:
    """Привязать реферала и начислить бонусы обеим сторонам."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE cookieclicker_players SET referrer_uuid = $1, cookies = cookies + $2 WHERE uuid = $3",
                referrer_uuid,
                user_bonus,
                user_uuid,
            )
            await conn.execute(
                """
                UPDATE cookieclicker_players
                SET referral_count    = referral_count + 1,
                    referral_earnings = referral_earnings + $1,
                    cookies           = cookies + $1
                WHERE uuid = $2
                """,
                referrer_bonus,
                referrer_uuid,
            )
