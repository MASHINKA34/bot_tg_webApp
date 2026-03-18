-- ============================================================
-- Migration: TG WebApp → единая PostgreSQL БД
-- Запускать один раз: psql -U postgres -d cookieclicker_unified -f migration.sql
-- Minecraft плагин работает без изменений, новые колонки он игнорирует
-- ============================================================

-- 1. Добавить TG-специфичные колонки в таблицу плагина
ALTER TABLE cookieclicker_players
    ADD COLUMN IF NOT EXISTS telegram_id BIGINT UNIQUE,
    ADD COLUMN IF NOT EXISTS click_level INTEGER DEFAULT 1,
    ADD COLUMN IF NOT EXISTS last_activity TIMESTAMP,
    ADD COLUMN IF NOT EXISTS active_events TEXT,
    ADD COLUMN IF NOT EXISTS last_daily_claim TIMESTAMP,
    ADD COLUMN IF NOT EXISTS daily_streak INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS referral_code VARCHAR(16) UNIQUE,
    ADD COLUMN IF NOT EXISTS referrer_uuid VARCHAR(64),
    ADD COLUMN IF NOT EXISTS referral_count INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS referral_earnings BIGINT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS last_click_timestamp BIGINT,
    ADD COLUMN IF NOT EXISTS clicks_this_second INTEGER DEFAULT 0;

-- 2. Индексы для быстрого поиска по telegram_id и реферальному коду
CREATE INDEX IF NOT EXISTS idx_players_telegram_id ON cookieclicker_players(telegram_id);
CREATE INDEX IF NOT EXISTS idx_players_referral_code ON cookieclicker_players(referral_code);

-- 3. Таблица ферм для TG бота (пассивный доход)
CREATE TABLE IF NOT EXISTS tg_farms (
    id         SERIAL PRIMARY KEY,
    player_uuid VARCHAR(64) NOT NULL REFERENCES cookieclicker_players(uuid),
    farm_type   VARCHAR(32) NOT NULL,
    farm_name   VARCHAR(64) NOT NULL,
    level       INTEGER DEFAULT 1,
    income_per_hour INTEGER NOT NULL,
    last_collected TIMESTAMP DEFAULT NOW(),
    purchased_at   TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tg_farms_player_uuid ON tg_farms(player_uuid);

-- Готово. platform_locks и функции try_start_clicking / unlock_platform /
-- cleanup_old_locks уже существуют (созданы Minecraft плагином).
