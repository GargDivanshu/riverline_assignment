from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class MoneyFact(BaseModel):
    id: str
    label: str
    amount_paise: int | None = Field(default=None, ge=0, le=9_007_199_254_740_991)
    due_date: date | None = None
    certainty: Literal["confirmed", "estimated", "uncertain", "unknown"] = "unknown"


class Workspace(BaseModel):
    revision: int = 0
    currency: Literal["INR"] = "INR"
    window_start: date
    window_end_exclusive: date
    opening_cash_paise: int | None = None
    income: list[MoneyFact] = Field(default_factory=list)
    commitments: list[MoneyFact] = Field(default_factory=list)
    expenses: list[MoneyFact] = Field(default_factory=list)
    plan_status: Literal["not_started"] = "not_started"
    voice_available: bool = False
