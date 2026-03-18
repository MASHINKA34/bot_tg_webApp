from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Telegram Bot
    BOT_TOKEN: str
    WEBAPP_URL: str = "http://localhost:8000"
    SECRET_KEY: str = "your_secret_key_12345"

    # PostgreSQL — та же БД что и Minecraft плагин
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "cookieclicker_unified"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "123"

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # Игровой баланс
    CLICK_VALUE: int = 1
    MAX_CLICKS_PER_SECOND: int = 15
    CLICK_UPGRADE_BASE_COST: int = 100
    CLICK_UPGRADE_MULTIPLIER: float = 1.5

    # Фермы
    FARM_AFK_LIMIT_HOURS: float = 2

    # Ежедневный бонус
    DAILY_BONUS_BASE: int = 100
    DAILY_BONUS_STREAK_MULTIPLIER: float = 1.2

    # Рефералы
    REFERRAL_BONUS: int = 500
    REFERRAL_BONUS_FOR_NEW_USER: int = 250

    class Config:
        env_file = ".env"


settings = Settings()
