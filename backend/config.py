from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    BOT_TOKEN: str
    WEBAPP_URL: str = "http://localhost:8000"
    DATABASE_URL: str = "sqlite+aiosqlite:///./clicker.db"
    SECRET_KEY: str
    
    # Игровые настройки
    CLICK_VALUE: int = 1
    MAX_CLICKS_PER_SECOND: int = 100
    CLICK_UPGRADE_BASE_COST: int = 100
    CLICK_UPGRADE_MULTIPLIER: float = 1.5
    
    FARM_AFK_LIMIT_HOURS: float = 2
    DAILY_BONUS_BASE: int = 100
    DAILY_BONUS_STREAK_MULTIPLIER: float = 1.2
    
    class Config:
        env_file = ".env"

settings = Settings()