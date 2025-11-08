from pydantic import BaseModel
from typing import Optional, List

class ClickRequest(BaseModel):
    telegram_id: int
    clicks: int = 1  

class UserStats(BaseModel):
    balance: int
    total_clicks: int
    click_level: int
    click_power: int
    upgrade_cost: int
    rank: int

class FarmResponse(BaseModel):
    id: int
    name: str
    level: int
    income_per_hour: int
    accumulated: int
    is_active: bool

class BuyFarmRequest(BaseModel):
    telegram_id: int
    farm_type: str

class LeaderboardPlayer(BaseModel):
    telegram_id: int
    username: str
    balance: int
    total_clicks: int