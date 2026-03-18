from fastapi import APIRouter, HTTPException, Header
from datetime import datetime, timezone
from backend import db_queries
from backend.schemas import ClickRequest
from backend.config import settings
from backend.platform_lock import PlatformLockManager
from backend.events import EventManager
import logging

router = APIRouter(prefix="/clicker", tags=["clicker"])
logger = logging.getLogger(__name__)


@router.post("/click")
async def process_click(
    request: ClickRequest,
    init_data: str = Header(None, alias="X-Telegram-Init-Data"),
):
    """
    Обработать клик:
    1. Найти / создать игрока
    2. Проверить platform lock (блокирует если кликает в Minecraft)
    3. Проверить CPS лимит
    4. Применить множитель события (Golden Cookie)
    5. Начислить печеньки
    6. Попробовать триггер нового события
    """

    # ── 1. Получить / создать игрока ─────────────────────────────────
    player = await db_queries.get_or_create_player(request.telegram_id)
    player_uuid = player["uuid"]

    # ── 2. Platform lock ─────────────────────────────────────────────
    lock = await PlatformLockManager.can_click(player_uuid, "telegram")
    if not lock["can_click"]:
        blocked_by = lock["blocked_by"]
        logger.warning(f"Игрок {request.telegram_id} заблокирован '{blocked_by}'")
        return {
            "success": False,
            "error": f"⛔ Вы уже кликаете в {blocked_by}!",
            "blocked_by": blocked_by,
            "message": (
                "Закройте Minecraft, чтобы продолжить в Telegram"
                if blocked_by == "minecraft"
                else None
            ),
        }

    # ── 3. CPS protection ────────────────────────────────────────────
    # Фронтенд буферизует клики и отправляет пачками (N кликов за раз).
    # Вместо полного отказа — обрезаем до разрешённого лимита за секунду.
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    last_ts = player.get("last_click_timestamp") or 0
    time_diff_sec = (now_ms - last_ts) / 1000.0

    if time_diff_sec < 1.0:
        used_this_second = player.get("clicks_this_second") or 0
    else:
        used_this_second = 0  # новая секунда — счётчик сброшен

    available = max(0, settings.MAX_CLICKS_PER_SECOND - used_this_second)
    allowed_clicks = min(request.clicks, available)

    if allowed_clicks <= 0:
        # Все слоты этой секунды исчерпаны
        return {
            "success": False,
            "error": f"⚡ Слишком быстро! Максимум {settings.MAX_CLICKS_PER_SECOND} кликов в секунду",
            "max_cps": settings.MAX_CLICKS_PER_SECOND,
        }

    clicks_this_second = used_this_second + allowed_clicks

    # ── 4. Событие — Golden Cookie ────────────────────────────────────
    active_event = await EventManager.get_active_event(player_uuid)
    multiplier = 1
    if active_event and active_event.get("type") == "golden_cookie":
        multiplier = EventManager.PER_CLICK_MULTIPLIER
        logger.info(f"Golden Cookie: multiplier={multiplier} для {request.telegram_id}")

    # ── 5. Начислить печеньки ─────────────────────────────────────────
    per_click = player.get("per_click") or settings.CLICK_VALUE
    # Считаем только разрешённые клики
    earned = per_click * allowed_clicks * multiplier

    # Определяем JSON события для сохранения в БД
    import json
    events_json: str | None = (
        json.dumps(active_event) if active_event else player.get("active_events")
    )

    updated = await db_queries.update_after_click(
        player_uuid=player_uuid,
        clicks=allowed_clicks,
        earned=earned,
        now_ms=now_ms,
        clicks_this_second=clicks_this_second,
        active_events_json=events_json,
    )

    logger.info(
        f"Клик: telegram_id={request.telegram_id}, "
        f"allowed={allowed_clicks}/{request.clicks}, earned={earned}, "
        f"balance={updated.get('cookies')}"
    )

    # ── 6. Триггер нового события ─────────────────────────────────────
    new_event = await EventManager.check_event_trigger(player_uuid)

    response = {
        "success": True,
        "earned": earned,
        "balance": updated.get("cookies", 0),
        "total_clicks": updated.get("clicker_clicks", 0),
        "click_power": updated.get("per_click", per_click),
        "clicks_processed": allowed_clicks,
        "multiplier": multiplier,
    }
    if new_event:
        response["event_triggered"] = new_event
    if active_event:
        response["active_event"] = active_event

    return response


@router.get("/stats/{telegram_id}")
async def get_stats(telegram_id: int):
    """Получить статистику игрока (создаёт новую запись если не существует)."""
    player = await db_queries.get_or_create_player(telegram_id)
    player_uuid = player["uuid"]

    upgrade_cost = int(
        settings.CLICK_UPGRADE_BASE_COST
        * (settings.CLICK_UPGRADE_MULTIPLIER ** (player["click_level"] - 1))
    )

    rank = await db_queries.get_player_rank(player["cookies"])
    active_event = await EventManager.get_active_event(player_uuid)

    # Реальный статус блокировки из platform_locks (read-only, не захватывает lock)
    # is_locked = True только если ДРУГАЯ платформа (minecraft) держит лок.
    # Если лок принадлежит самому telegram — это нормально, не блокировать.
    lock_status = await PlatformLockManager.get_lock_status(player_uuid)
    locked_by_other = (
        lock_status["is_locked"] and lock_status["locked_by"] == "minecraft"
    )

    last_activity = player.get("last_activity")
    return {
        "balance": player["cookies"],
        "total_clicks": player["clicker_clicks"],
        "click_level": player["click_level"],
        "click_power": player["per_click"],
        "upgrade_cost": upgrade_cost,
        "rank": rank,
        "last_activity": last_activity.isoformat() if last_activity else None,
        "is_locked": locked_by_other,
        "locked_by": lock_status["locked_by"] if locked_by_other else None,
        "active_event": active_event,
    }


@router.post("/upgrade")
async def upgrade_click(request: ClickRequest):
    """Улучшить силу клика — аддитивно (+25% от текущего, мин. 1)."""
    player = await db_queries.get_player_by_telegram_id(request.telegram_id)
    if not player:
        raise HTTPException(404, "Player not found")

    player_uuid = player["uuid"]
    current_level = player["click_level"]
    current_per_click = player["per_click"] or settings.CLICK_VALUE

    upgrade_cost = int(
        settings.CLICK_UPGRADE_BASE_COST
        * (settings.CLICK_UPGRADE_MULTIPLIER ** (current_level - 1))
    )

    if player["cookies"] < upgrade_cost:
        return {"success": False, "error": f"Недостаточно средств. Нужно: {upgrade_cost}"}

    new_level = current_level + 1

    # Аддитивный прирост: +25% от текущего per_click, минимум settings.CLICK_VALUE (1).
    # Это сохраняет прогресс из Minecraft (например 665) и не сбрасывает его в level*1.
    increment = max(current_per_click // 4, settings.CLICK_VALUE)
    new_per_click = current_per_click + increment

    updated = await db_queries.upgrade_click_power(player_uuid, upgrade_cost, new_level, new_per_click)
    if not updated:
        return {"success": False, "error": "Недостаточно средств (race condition)"}

    next_cost = int(
        settings.CLICK_UPGRADE_BASE_COST
        * (settings.CLICK_UPGRADE_MULTIPLIER ** new_level)
    )

    logger.info(
        f"Апгрейд клика: telegram_id={request.telegram_id}, "
        f"level {current_level}→{new_level}, "
        f"per_click {current_per_click}→{new_per_click} (+{increment})"
    )

    return {
        "success": True,
        "new_level": updated["click_level"],
        "new_power": updated["per_click"],
        "balance": updated["cookies"],
        "next_upgrade_cost": next_cost,
    }


@router.post("/collect_explosion_cookie")
async def collect_explosion_cookie(request: ClickRequest):
    """Собрать одну печеньку из Cookie Explosion события."""
    player = await db_queries.get_player_by_telegram_id(request.telegram_id)
    if not player:
        raise HTTPException(404, "Player not found")

    result = await EventManager.collect_explosion_cookie(player["uuid"])

    if not result["success"]:
        return {"success": False, "error": result.get("error", "Unknown error")}

    # Перечитать баланс
    updated = await db_queries.get_player_by_telegram_id(request.telegram_id)
    return {
        "success": True,
        "reward": result["reward"],
        "cookies_left": result["cookies_left"],
        "balance": updated["cookies"] if updated else 0,
        "message": f"🍪 +{result['reward']} cookies!",
    }


@router.post("/force_unlock/{telegram_id}")
async def force_unlock(telegram_id: int):
    """Admin: принудительно разблокировать игрока."""
    uuid = await db_queries.get_player_uuid(telegram_id)
    if not uuid:
        raise HTTPException(404, "Player not found")

    success = await PlatformLockManager.unlock_player(uuid)
    if success:
        return {"success": True, "message": f"Player {telegram_id} unlocked"}
    raise HTTPException(500, "Failed to unlock player")
