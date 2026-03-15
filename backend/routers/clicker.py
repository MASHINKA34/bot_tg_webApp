from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from backend.database import get_session
from backend.models import Player
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
    db: AsyncSession = Depends(get_session),
    init_data: str = Header(None, alias="X-Telegram-Init-Data")
):
    """
    Process click with:
    - Platform locking
    - CPS protection
    - Event triggers (Golden Cookie, Cookie Explosion)
    - Event multipliers
    
    ПОЛНАЯ СИНХРОНИЗАЦИЯ с MC плагином
    """
    
    # Get or create player
    result = await db.execute(
        select(Player).where(Player.telegram_id == request.telegram_id)
    )
    player = result.scalar_one_or_none()
    
    if not player:
        player = Player(
            telegram_id=request.telegram_id,
            cookies=0,
            total_clicks=0,
            click_level=1,
            per_click=settings.CLICK_VALUE
        )
        db.add(player)
        await db.flush()
        logger.info(f"Created new player: telegram_id={request.telegram_id}")
    
    # ========================================
    # 🔒 PLATFORM LOCK CHECK
    # ========================================
    lock_result = await PlatformLockManager.can_click(player.id, "telegram", db)
    
    if not lock_result["can_click"]:
        blocked_by = lock_result["blocked_by"]
        logger.warning(f"Player {player.telegram_id} blocked by {blocked_by}")
        
        return {
            "success": False,
            "error": f"⛔ Вы уже кликаете в {blocked_by}!",
            "blocked_by": blocked_by,
            "message": "Закройте Minecraft, чтобы продолжить в Telegram" if blocked_by == "minecraft" else None
        }
    
    # ========================================
    # ⚡ CPS PROTECTION
    # ========================================
    now = datetime.utcnow()
    current_timestamp_ms = int(now.timestamp() * 1000)
    
    if player.last_click_timestamp:
        time_diff = (current_timestamp_ms - player.last_click_timestamp) / 1000.0
        
        if time_diff < 1:
            player.clicks_this_second += request.clicks
            
            if player.clicks_this_second > 15:
                logger.warning(f"CPS limit exceeded for player {player.telegram_id}")
                return {
                    "success": False,
                    "error": "⚡ Слишком быстро! Максимум 15 кликов в секунду",
                    "max_cps": 15,
                    "current_cps": player.clicks_this_second
                }
        else:
            player.clicks_this_second = request.clicks
    else:
        player.clicks_this_second = request.clicks
    
    player.last_click_timestamp = current_timestamp_ms
    
    # ========================================
    # 🎯 EVENT HANDLING
    # ========================================
    
    # Проверить активное событие
    active_event = await EventManager.get_active_event(player.id, db)
    
    # Применить множитель Golden Cookie
    multiplier = 1
    if active_event and active_event.get("type") == "golden_cookie":
        multiplier = EventManager.PER_CLICK_MULTIPLIER
        logger.info(f"Golden Cookie active for {player.telegram_id}, multiplier={multiplier}")
    
    # Посчитать заработок
    earned = player.per_click * request.clicks * multiplier
    
    # Обновить статистику
    player.cookies += earned
    player.total_clicks += request.clicks
    player.last_activity = now
    
    await db.commit()
    
    # Проверить триггер нового события (ПОСЛЕ клика)
    new_event = await EventManager.check_event_trigger(player.id, db)
    if new_event:
        await db.commit()
    
    logger.info(f"Click processed: telegram_id={player.telegram_id}, earned={earned}, total={player.cookies}")
    
    response = {
        "success": True,
        "earned": earned,
        "balance": player.cookies,
        "total_clicks": player.total_clicks,
        "click_power": player.per_click,
        "clicks_processed": request.clicks,
        "multiplier": multiplier
    }
    
    # Добавить информацию о новом событии
    if new_event:
        response["event_triggered"] = new_event
    
    # Добавить информацию об активном событии
    if active_event:
        response["active_event"] = active_event
    
    return response


@router.get("/stats/{telegram_id}")
async def get_stats(telegram_id: int, db: AsyncSession = Depends(get_session)):
    """
    Get player stats including active events
    """
    result = await db.execute(
        select(Player).where(Player.telegram_id == telegram_id)
    )
    player = result.scalar_one_or_none()
    
    if not player:
        player = Player(
            telegram_id=telegram_id,
            cookies=0,
            total_clicks=0,
            click_level=1,
            per_click=settings.CLICK_VALUE
        )
        db.add(player)
        await db.commit()
        await db.refresh(player)
    
    # Calculate upgrade cost
    upgrade_cost = int(
        settings.CLICK_UPGRADE_BASE_COST * 
        (settings.CLICK_UPGRADE_MULTIPLIER ** (player.click_level - 1))
    )
    
    # Get rank
    all_players = await db.execute(
        select(Player).order_by(Player.cookies.desc())
    )
    players_list = all_players.scalars().all()
    rank = next((i+1 for i, p in enumerate(players_list) if p.telegram_id == telegram_id), 0)
    
    # Get active event
    active_event = await EventManager.get_active_event(player.id, db)
    
    return {
        "balance": player.cookies,
        "total_clicks": player.total_clicks,
        "click_level": player.click_level,
        "click_power": player.per_click,
        "upgrade_cost": upgrade_cost,
        "rank": rank,
        "active_platform": player.active_platform,
        "last_activity": player.last_activity.isoformat() if player.last_activity else None,
        "is_locked": player.active_platform is not None and player.active_platform != "telegram",
        "active_event": active_event  # НОВОЕ!
    }


@router.post("/upgrade")
async def upgrade_click(
    request: ClickRequest, 
    db: AsyncSession = Depends(get_session)
):
    """
    Upgrade click power (как в MC per_click shop)
    """
    result = await db.execute(
        select(Player).where(Player.telegram_id == request.telegram_id)
    )
    player = result.scalar_one_or_none()
    
    if not player:
        raise HTTPException(404, "Player not found")
    
    upgrade_cost = int(
        settings.CLICK_UPGRADE_BASE_COST * 
        (settings.CLICK_UPGRADE_MULTIPLIER ** (player.click_level - 1))
    )
    
    if player.cookies < upgrade_cost:
        return {
            "success": False, 
            "error": f"Недостаточно средств. Нужно: {upgrade_cost}"
        }
    
    # Apply upgrade
    player.cookies -= upgrade_cost
    player.click_level += 1
    player.per_click = player.click_level * settings.CLICK_VALUE
    player.last_activity = datetime.utcnow()
    
    await db.commit()
    
    next_cost = int(
        settings.CLICK_UPGRADE_BASE_COST * 
        (settings.CLICK_UPGRADE_MULTIPLIER ** player.click_level)
    )
    
    return {
        "success": True,
        "new_level": player.click_level,
        "new_power": player.per_click,
        "balance": player.cookies,
        "next_upgrade_cost": next_cost
    }


@router.post("/collect_explosion_cookie")
async def collect_explosion_cookie(
    request: ClickRequest,
    db: AsyncSession = Depends(get_session)
):
    """
    Собрать печеньку из Cookie Explosion события
    
    НОВОЕ! Синхронизировано с MC
    """
    result = await db.execute(
        select(Player).where(Player.telegram_id == request.telegram_id)
    )
    player = result.scalar_one_or_none()
    
    if not player:
        raise HTTPException(404, "Player not found")
    
    # Собрать печеньку
    collect_result = await EventManager.collect_explosion_cookie(player.id, db)
    
    if not collect_result["success"]:
        return {
            "success": False,
            "error": collect_result.get("error", "Unknown error")
        }
    
    # Обновить баланс игрока
    await db.refresh(player)
    
    return {
        "success": True,
        "reward": collect_result["reward"],
        "cookies_left": collect_result["cookies_left"],
        "balance": player.cookies,
        "message": f"🍪 +{collect_result['reward']} cookies!"
    }


@router.post("/force_unlock/{telegram_id}")
async def force_unlock(telegram_id: int, db: AsyncSession = Depends(get_session)):
    """
    Admin endpoint to force unlock player
    """
    result = await db.execute(
        select(Player).where(Player.telegram_id == telegram_id)
    )
    player = result.scalar_one_or_none()
    
    if not player:
        raise HTTPException(404, "Player not found")
    
    success = await PlatformLockManager.unlock_player(player.id, db)
    
    if success:
        return {"success": True, "message": f"Player {telegram_id} unlocked"}
    else:
        raise HTTPException(500, "Failed to unlock player")
