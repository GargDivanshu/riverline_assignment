from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class MoneyFact(BaseModel):
    id: str
    label: str
    amount_paise: int | None = Field(default=None, ge=0, le=9_007_199_254_740_991)
    # Set together, only when the person gave a range rather than one figure (e.g. a
    # kirana owner's "sixty to seventy thousand" shop income). amount_paise then holds
    # the midpoint, used where the calculation needs one number; the real range stays
    # here for display and for picking a conservative bound in the projection.
    min_amount_paise: int | None = Field(default=None, ge=0, le=9_007_199_254_740_991)
    max_amount_paise: int | None = Field(default=None, ge=0, le=9_007_199_254_740_991)
    # Only for money that is only partly usable for this plan (protected savings with
    # a cap the person set). None means the full amount is usable.
    usable_amount_paise: int | None = Field(default=None, ge=0, le=9_007_199_254_740_991)
    # Money the person said cannot be used for this plan at all (e.g. business cash
    # that is not personal money). Still tracked and shown; excluded from every
    # calculation, not merely uncertain.
    restricted: bool = False
    due_date: date | None = None
    # Only for money that repeats on the same calendar day every month (salary,
    # rent, an EMI) rather than landing on one specific date. Mutually alternative
    # to due_date: a recurring fact has a cycle, not a single date, so the 30-day
    # projection expands it into every occurrence that falls in the window instead
    # of relying on one due_date.
    recurring_day_of_month: int | None = Field(default=None, ge=1, le=31)
    # A short caveat on top of a date or recurring day that isn't itself a date
    # ("may arrive as late as the 2nd"). Shown, never parsed or calculated with.
    timing_note: str | None = Field(default=None, max_length=140)
    certainty: Literal["confirmed", "estimated", "uncertain", "unknown"] = "unknown"


class PlanEvent(BaseModel):
    date: date
    label: str
    change_paise: int
    balance_paise: int


class PlanSummary(BaseModel):
    dated_income_paise: int = 0
    dated_outgoings_paise: int = 0
    projected_closing_paise: int | None = None
    lowest_balance_paise: int | None = None
    first_shortfall_date: date | None = None
    unplanned_fact_count: int = 0
    # The confirmed path above never counts uncertain money. This shows what changes
    # if it arrives — e.g. "the customer's twenty thousand could reduce the shortfall
    # to X" — without ever promoting it into the confirmed number itself.
    uncertain_income_paise: int = 0
    uncertain_outgoings_paise: int = 0
    conditional_closing_paise: int | None = None


class Workspace(BaseModel):
    revision: int = 0
    currency: Literal["INR"] = "INR"
    window_start: date
    window_end_exclusive: date
    opening_cash_paise: int | None = None
    # Individual cash facts, not just the aggregate above — needed so restricted
    # money (shop drawer cash) and a partial usable cap (a savings limit) stay
    # visible as their own line items, not folded invisibly into one number.
    opening_cash: list[MoneyFact] = Field(default_factory=list)
    income: list[MoneyFact] = Field(default_factory=list)
    commitments: list[MoneyFact] = Field(default_factory=list)
    expenses: list[MoneyFact] = Field(default_factory=list)
    plan_status: Literal["not_started", "building", "ready"] = "not_started"
    summary: PlanSummary = Field(default_factory=PlanSummary)
    timeline: list[PlanEvent] = Field(default_factory=list)
    voice_available: bool = False
