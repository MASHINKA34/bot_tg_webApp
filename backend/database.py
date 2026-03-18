import asyncpg
import logging

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


async def init_db(dsn: str) -> None:
    """Инициализировать пул соединений к PostgreSQL."""
    global _pool
    _pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10)
    logger.info("✅ asyncpg pool создан")


async def close_db() -> None:
    """Закрыть пул при остановке приложения."""
    global _pool
    if _pool:
        await _pool.close()
        logger.info("🛑 asyncpg pool закрыт")


def get_pool() -> asyncpg.Pool:
    """Вернуть активный пул соединений."""
    if _pool is None:
        raise RuntimeError("Database pool is not initialized. Call init_db() first.")
    return _pool
