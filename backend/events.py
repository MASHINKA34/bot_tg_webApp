"""
events.py — система событий (Golden Cookie, Cookie Explosion).
Полностью на Python, состояние хранится в active_events TEXT(JSON) в БД.
Синхронизировано с логикой Minecraft плагина.
"""

import json
import random
import logging
from datetime import datetime, timezone
from typing import Optional, Dict

from backend.database import get_pool

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Константы (из MC config.yml)
# ─────────────────────────────────────────────
GOLDEN_COOKIE_CHANCE = 10000        # 1 из 10 000
COOKIE_EXPLOSION_CHANCE = 5000      # 1 из 5 000
GOLDEN_DURATION_SECONDS = 60
EXPLOSION_DURATION_SECONDS = 30
COOKIE_AMOUNT = 20
COOKIES_PER_COOKIE_MULTIPLIER = 10
PER_CLICK_MULTIPLIER = 2


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_event(active_events_str: Optional[str]) -> Optional[Dict]:
    """Распарсить JSON строку события."""
    if not active_events_str:
        return None
    try:
        return json.loads(active_events_str)
    except (json.JSONDecodeError, TypeError):
        return None


def _is_expired(event: Dict) -> bool:
    """Проверить, истёк ли срок события."""
    try:
        expires_at = datetime.fromisoformat(event["expires_at"])
        return datetime.now(timezone.utc) >= expires_at
    except (KeyError, ValueError):
        return True


async def _save_event(player_uuid: str, event: Optional[Dict]) -> None:
    """Сохранить (или очистить) событие в БД."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE cookieclicker_players SET active_events = $1 WHERE uuid = $2",
            json.dumps(event) if event else None,
            player_uuid,
        )


class EventManager:
    """
    Менеджер событий — синхронизирован с MC плагином.

    События:
    - Golden Cookie  : x2 к кликам на 60 сек  (шанс 1/10 000)
    - Cookie Explosion: 20 печенек по x10 за каждую (шанс 1/5 000)
    """

    PER_CLICK_MULTIPLIER = PER_CLICK_MULTIPLIER

    # ─────────────────────────────────────────
    # Получить активное событие
    # ─────────────────────────────────────────

    @staticmethod
    async def get_active_event(player_uuid: str) -> Optional[Dict]:
        """
        Вернуть активное событие игрока.
        Автоматически очищает истёкшие события.
        """
        pool = get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT active_events FROM cookieclicker_players WHERE uuid = $1",
                player_uuid,
            )
        if not row:
            return None

        event = _parse_event(row["active_events"])
        if event is None:
            return None

        if _is_expired(event):
            await _save_event(player_uuid, None)
            return None

        return event

    # ─────────────────────────────────────────
    # Триггер случайного события при клике
    # ─────────────────────────────────────────

    @staticmethod
    async def check_event_trigger(player_uuid: str) -> Optional[Dict]:
        """
        Проверить случайный триггер события.
        Вызывается после каждого клика.
        """
        # Сначала проверяем — нет ли уже активного события
        existing = await EventManager.get_active_event(player_uuid)
        if existing:
            return None

        try:
            # Golden Cookie (1/10 000)
            if random.randint(1, GOLDEN_COOKIE_CHANCE) == 1:
                from datetime import timedelta
                now = datetime.now(timezone.utc)
                event = {
                    "type": "golden_cookie",
                    "started_at": now.isoformat(),
                    "expires_at": (now + timedelta(seconds=GOLDEN_DURATION_SECONDS)).isoformat(),
                    "multiplier": PER_CLICK_MULTIPLIER,
                }
                await _save_event(player_uuid, event)
                logger.info(f"🌟 Golden Cookie активирован для {player_uuid}")
                return {
                    "type": "golden_cookie",
                    "duration": GOLDEN_DURATION_SECONDS,
                    "multiplier": PER_CLICK_MULTIPLIER,
                    "message": "🌟 ЗОЛОТОЕ ПЕЧЕНЬЕ! x2 к кликам на 60 секунд!",
                }

            # Cookie Explosion (1/5 000)
            elif random.randint(1, COOKIE_EXPLOSION_CHANCE) == 1:
                from datetime import timedelta
                now = datetime.now(timezone.utc)
                event = {
                    "type": "cookie_explosion",
                    "started_at": now.isoformat(),
                    "expires_at": (now + timedelta(seconds=EXPLOSION_DURATION_SECONDS)).isoformat(),
                    "cookies_left": COOKIE_AMOUNT,
                    "cookie_value": COOKIES_PER_COOKIE_MULTIPLIER,
                }
                await _save_event(player_uuid, event)
                logger.info(f"💥 Cookie Explosion активирован для {player_uuid}")
                return {
                    "type": "cookie_explosion",
                    "duration": EXPLOSION_DURATION_SECONDS,
                    "cookies_total": COOKIE_AMOUNT,
                    "cookies_left": COOKIE_AMOUNT,
                    "message": f"💥 ВЗРЫВ ПЕЧЕНЕК! Собери {COOKIE_AMOUNT} печенек!",
                }

        except Exception as exc:
            logger.error(f"Ошибка триггера события: {exc}", exc_info=True)

        return None

    # ─────────────────────────────────────────
    # Собрать печеньку из Cookie Explosion
    # ─────────────────────────────────────────

    @staticmethod
    async def collect_explosion_cookie(player_uuid: str) -> Dict:
        """
        Собрать одну печеньку из Cookie Explosion.
        Начисляет reward = per_click * COOKIES_PER_COOKIE_MULTIPLIER.
        """
        pool = get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT active_events, per_click FROM cookieclicker_players WHERE uuid = $1",
                player_uuid,
            )

        if not row:
            return {"success": False, "error": "Игрок не найден"}

        event = _parse_event(row["active_events"])
        if not event or event.get("type") != "cookie_explosion":
            return {"success": False, "error": "Нет активного Cookie Explosion"}

        if _is_expired(event):
            await _save_event(player_uuid, None)
            return {"success": False, "error": "Событие истекло"}

        cookies_left = event.get("cookies_left", 0)
        if cookies_left <= 0:
            await _save_event(player_uuid, None)
            return {"success": False, "error": "Все печеньки уже собраны"}

        # Начислить награду
        reward = row["per_click"] * COOKIES_PER_COOKIE_MULTIPLIER
        cookies_left -= 1

        if cookies_left == 0:
            # Событие завершено
            await _save_event(player_uuid, None)
        else:
            event["cookies_left"] = cookies_left
            await _save_event(player_uuid, event)

        # Начислить монеты
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE cookieclicker_players SET cookies = cookies + $1 WHERE uuid = $2",
                reward,
                player_uuid,
            )

        return {"success": True, "reward": reward, "cookies_left": cookies_left}

    # ─────────────────────────────────────────
    # Очистить событие
    # ─────────────────────────────────────────

    @staticmethod
    async def clear_event(player_uuid: str) -> None:
        await _save_event(player_uuid, None)
