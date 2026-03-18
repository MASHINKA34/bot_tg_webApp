from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
from typing import List
from backend import db_queries
from backend.schemas import BuyFarmRequest, FarmResponse
from backend.config import settings
import logging

router = APIRouter(prefix="/farms", tags=["farms"])
logger = logging.getLogger(__name__)

FARM_TYPES = {
    "small_farm":  {"name": "Мини-ферма",  "cost": 500,   "income": 50},
    "factory":     {"name": "Завод",        "cost": 2000,  "income": 250},
    "corporation": {"name": "Корпорация",   "cost": 10000, "income": 1500},
}


def _calc_accumulated(farm: dict, last_activity: datetime | None) -> tuple[int, bool]:
    """Вычислить накопленный доход фермы с учётом AFK лимита."""
    now = datetime.now(timezone.utc)

    last_collected = farm.get("last_collected") or now
    if last_collected.tzinfo is None:
        last_collected = last_collected.replace(tzinfo=timezone.utc)

    time_since_collect_h = (now - last_collected).total_seconds() / 3600

    is_active = True
    if last_activity:
        if last_activity.tzinfo is None:
            last_activity = last_activity.replace(tzinfo=timezone.utc)
        time_since_activity_h = (now - last_activity).total_seconds() / 3600
        is_active = time_since_activity_h < settings.FARM_AFK_LIMIT_HOURS

        if not is_active:
            production_time = max(
                0.0,
                time_since_collect_h - (time_since_activity_h - settings.FARM_AFK_LIMIT_HOURS),
            )
        else:
            production_time = time_since_collect_h
    else:
        production_time = time_since_collect_h

    accumulated = int(farm["income_per_hour"] * production_time)
    return accumulated, is_active


@router.get("/{telegram_id}", response_model=List[FarmResponse])
async def get_farms(telegram_id: int):
    """Получить список ферм игрока."""
    player = await db_queries.get_or_create_player(telegram_id)
    farms = await db_queries.get_farms(player["uuid"])

    last_activity = player.get("last_activity")

    result = []
    for farm in farms:
        accumulated, is_active = _calc_accumulated(farm, last_activity)
        result.append(
            FarmResponse(
                id=farm["id"],
                name=farm["farm_name"],
                level=farm["level"],
                income_per_hour=farm["income_per_hour"],
                accumulated=accumulated,
                is_active=is_active,
            )
        )
    return result


@router.post("/buy")
async def buy_farm(request: BuyFarmRequest):
    """Купить или улучшить ферму."""
    if request.farm_type not in FARM_TYPES:
        raise HTTPException(400, "Неизвестный тип фермы")

    player = await db_queries.get_or_create_player(request.telegram_id)
    player_uuid = player["uuid"]
    farm_info = FARM_TYPES[request.farm_type]

    if player["cookies"] < farm_info["cost"]:
        return {"success": False, "error": "Недостаточно средств"}

    existing = await db_queries.get_farm_by_type(player_uuid, request.farm_type)

    if existing:
        new_level = existing["level"] + 1
        new_income = int(farm_info["income"] * new_level)
        result = await db_queries.upgrade_farm(
            existing["id"], player_uuid, farm_info["cost"], new_level, new_income
        )
        return {
            "success": True,
            "farm_id": existing["id"],
            "balance": result["balance"],
            "level": result["level"],
        }
    else:
        result = await db_queries.buy_farm(
            player_uuid,
            request.farm_type,
            farm_info["name"],
            farm_info["cost"],
            farm_info["income"],
        )
        return {
            "success": True,
            "farm_id": result["farm"]["id"],
            "balance": result["balance"],
            "level": 1,
        }


@router.post("/collect/{farm_id}")
async def collect_farm(farm_id: int, telegram_id: int):
    """Собрать накопленный доход фермы."""
    player = await db_queries.get_or_create_player(telegram_id)
    player_uuid = player["uuid"]

    farm = await db_queries.get_farm_by_id(farm_id, player_uuid)
    if not farm:
        raise HTTPException(404, "Ферма не найдена")

    accumulated, _ = _calc_accumulated(farm, player.get("last_activity"))

    result = await db_queries.collect_farm_income(farm_id, player_uuid, accumulated)
    return {"success": True, "earned": result["earned"], "balance": result["balance"]}
