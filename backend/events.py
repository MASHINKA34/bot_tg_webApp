from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select
from backend.models import Player
from datetime import datetime
from typing import Optional, Dict
import json
import random
import logging

logger = logging.getLogger(__name__)

class EventManager:
    """
    Event Manager - СИНХРОНИЗИРОВАНО с MC плагином
    
    События:
    - Golden Cookie: x2 к кликам на 60 секунд (шанс 1/10000)
    - Cookie Explosion: 20 печенек по x10 награды за каждую (шанс 1/5000)
    """
    
    # Настройки из MC config.yml
    GOLDEN_COOKIE_CHANCE = 10000      # 1 из 10000
    COOKIE_EXPLOSION_CHANCE = 5000    # 1 из 5000
    GOLDEN_DURATION_SECONDS = 60
    EXPLOSION_DURATION_SECONDS = 30
    COOKIE_AMOUNT = 20
    COOKIES_PER_COOKIE_MULTIPLIER = 10
    PER_CLICK_MULTIPLIER = 2
    
    @staticmethod
    async def check_event_trigger(player_id: int, db: AsyncSession) -> Optional[Dict]:
        """
        Проверить триггер события при клике (как в MC)
        
        Returns:
            Dict с данными события или None
        """
        try:
            # Golden Cookie (1/10000 шанс)
            if random.randint(1, EventManager.GOLDEN_COOKIE_CHANCE) == 1:
                result = await db.execute(
                    text("SELECT activate_golden_cookie(:player_id)"),
                    {"player_id": player_id}
                )
                event_data = result.scalar()
                
                logger.info(f"🌟 Golden Cookie activated for player {player_id}")
                
                return {
                    "type": "golden_cookie",
                    "duration": EventManager.GOLDEN_DURATION_SECONDS,
                    "multiplier": EventManager.PER_CLICK_MULTIPLIER,
                    "message": "🌟 ЗОЛОТОЕ ПЕЧЕНЬЕ! x2 к кликам на 60 секунд!"
                }
            
            # Cookie Explosion (1/5000 шанс)
            elif random.randint(1, EventManager.COOKIE_EXPLOSION_CHANCE) == 1:
                result = await db.execute(
                    text("SELECT activate_cookie_explosion(:player_id, :cookie_count)"),
                    {
                        "player_id": player_id,
                        "cookie_count": EventManager.COOKIE_AMOUNT
                    }
                )
                event_data = result.scalar()
                
                logger.info(f"💥 Cookie Explosion activated for player {player_id}")
                
                return {
                    "type": "cookie_explosion",
                    "duration": EventManager.EXPLOSION_DURATION_SECONDS,
                    "cookies_total": EventManager.COOKIE_AMOUNT,
                    "cookies_left": EventManager.COOKIE_AMOUNT,
                    "message": f"💥 ВЗРЫВ ПЕЧЕНЕК! Собери {EventManager.COOKIE_AMOUNT} печенек!"
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error checking event trigger: {e}", exc_info=True)
            return None
    
    @staticmethod
    async def get_active_event(player_id: int, db: AsyncSession) -> Optional[Dict]:
        """
        Получить активное событие игрока
        
        Returns:
            Dict с данными события или None
        """
        try:
            result = await db.execute(
                text("SELECT check_active_events(:player_id)"),
                {"player_id": player_id}
            )
            event_json = result.scalar()
            
            if event_json:
                return dict(event_json)
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting active event: {e}", exc_info=True)
            return None
    
    @staticmethod
    async def is_golden_cookie_active(player_id: int, db: AsyncSession) -> bool:
        """
        Проверить активно ли Golden Cookie событие
        """
        event = await EventManager.get_active_event(player_id, db)
        return event is not None and event.get("type") == "golden_cookie"
    
    @staticmethod
    async def collect_explosion_cookie(player_id: int, db: AsyncSession) -> Dict:
        """
        Собрать печеньку из Cookie Explosion
        
        Returns:
            {
                "success": bool,
                "reward": int,
                "cookies_left": int,
                "error": str (если success=False)
            }
        """
        try:
            result = await db.execute(
                text("SELECT collect_explosion_cookie(:player_id)"),
                {"player_id": player_id}
            )
            result_json = result.scalar()
            
            await db.commit()
            
            if result_json:
                return dict(result_json)
            
            return {"success": False, "error": "Unknown error"}
            
        except Exception as e:
            logger.error(f"Error collecting explosion cookie: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    @staticmethod
    async def clear_event(player_id: int, db: AsyncSession) -> None:
        """
        Очистить активное событие (когда истек срок)
        """
        try:
            result = await db.execute(
                select(Player).where(Player.id == player_id)
            )
            player = result.scalar_one_or_none()
            
            if player:
                player.active_events = None
                await db.commit()
                
        except Exception as e:
            logger.error(f"Error clearing event: {e}", exc_info=True)
