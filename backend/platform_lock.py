from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

class PlatformLockManager:
    """
    Manager for platform locking to prevent simultaneous clicking
    Менеджер блокировки платформ для предотвращения одновременных кликов
    """
    
    @staticmethod
    async def can_click(player_id: int, platform: str, db: AsyncSession) -> Dict[str, any]:
        """
        Check if player can click on specified platform
        
        Args:
            player_id: Internal database player ID
            platform: 'minecraft' or 'telegram'
            db: Database session
        
        Returns:
            {
                "can_click": bool,
                "blocked_by": str | None  # 'minecraft' | 'telegram' | None
            }
        """
        try:
            # Вызов SQL функции try_start_clicking
            result = await db.execute(
                text("SELECT * FROM try_start_clicking(:player_id, :platform)"),
                {"player_id": player_id, "platform": platform}
            )
            row = result.fetchone()
            
            if row:
                can_click = row[0]
                blocked_by = row[1]
                
                if not can_click:
                    logger.info(f"Player {player_id} is blocked by {blocked_by} platform")
                
                return {
                    "can_click": can_click,
                    "blocked_by": blocked_by
                }
                
        except Exception as e:
            logger.error(f"Error checking platform lock: {e}", exc_info=True)
        
        # Fail-safe: allow clicking on error
        logger.warning(f"Platform lock check failed for player {player_id}, allowing click (fail-safe)")
        return {"can_click": True, "blocked_by": None}
    
    @staticmethod
    async def unlock_player(player_id: int, db: AsyncSession) -> bool:
        """
        Force unlock player (admin action)
        
        Args:
            player_id: Internal database player ID
            db: Database session
        
        Returns:
            True if successful, False otherwise
        """
        try:
            await db.execute(
                text("SELECT unlock_platform(:player_id)"),
                {"player_id": player_id}
            )
            await db.commit()
            logger.info(f"Successfully unlocked player {player_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error unlocking player {player_id}: {e}", exc_info=True)
            return False
