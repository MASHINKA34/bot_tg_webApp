"""
platform_lock.py — проверка блокировки платформ через общую PostgreSQL БД.

Использует ту же функцию try_start_clicking() что и Minecraft плагин.
UUID игрока берётся из cookieclicker_players.uuid по telegram_id.
"""

import logging
from typing import Optional

from backend.database import get_pool

logger = logging.getLogger(__name__)


class PlatformLockManager:
    """
    Проверка и снятие блокировки платформы.
    Minecraft плагин блокирует через ту же PostgreSQL функцию.
    """

    @staticmethod
    async def can_click(player_uuid: str, platform: str) -> dict:
        """
        Проверить, может ли игрок кликать на данной платформе.

        Args:
            player_uuid: UUID игрока (из cookieclicker_players.uuid)
            platform:    'telegram' или 'minecraft'

        Returns:
            {"can_click": bool, "blocked_by": str | None}
        """
        pool = get_pool()
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM try_start_clicking($1::uuid, $2)",
                    player_uuid,
                    platform,
                )
                if row is not None:
                    can_click = row["can_click"]
                    blocked_by = row["blocked_by"]
                    if not can_click:
                        logger.info(
                            f"Игрок {player_uuid} заблокирован платформой '{blocked_by}'"
                        )
                    return {"can_click": can_click, "blocked_by": blocked_by}
        except Exception as exc:
            logger.error(f"Ошибка проверки platform lock: {exc}", exc_info=True)

        # Fail-safe: разрешить клик если БД недоступна
        logger.warning(f"Platform lock check failed для {player_uuid}, allowing (fail-safe)")
        return {"can_click": True, "blocked_by": None}

    @staticmethod
    async def get_lock_status(player_uuid: str) -> dict:
        """
        Проверить статус блокировки игрока (READ-ONLY, не обновляет lock).

        Returns:
            {"is_locked": bool, "locked_by": str | None}
        """
        pool = get_pool()
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    """SELECT platform, locked_at,
                              (locked_at > NOW() - INTERVAL '5 minutes') AS fresh
                       FROM platform_locks
                       WHERE player_uuid = $1::uuid""",
                    player_uuid,
                )
                if row:
                    platform = row["platform"]
                    locked_at = row["locked_at"]
                    fresh = row["fresh"]
                    logger.info(
                        f"get_lock_status({player_uuid}): "
                        f"platform={platform}, locked_at={locked_at}, fresh={fresh}"
                    )
                    if fresh:
                        return {"is_locked": True, "locked_by": platform}
                    else:
                        logger.info(f"Лок устарел (>5 мин), считаем разблокированным")
                        return {"is_locked": False, "locked_by": None}
                logger.info(f"get_lock_status({player_uuid}): нет записи в platform_locks")
                return {"is_locked": False, "locked_by": None}
        except Exception as exc:
            logger.error(f"Ошибка проверки статуса lock: {exc}", exc_info=True)
            return {"is_locked": False, "locked_by": None}

    @staticmethod
    async def unlock_player(player_uuid: str) -> bool:
        """
        Принудительно разблокировать игрока (admin-действие).

        Args:
            player_uuid: UUID игрока

        Returns:
            True если успешно
        """
        pool = get_pool()
        try:
            async with pool.acquire() as conn:
                await conn.execute(
                    "SELECT unlock_platform($1::uuid)",
                    player_uuid,
                )
            logger.info(f"Игрок {player_uuid} разблокирован")
            return True
        except Exception as exc:
            logger.error(f"Ошибка разблокировки {player_uuid}: {exc}", exc_info=True)
            return False
