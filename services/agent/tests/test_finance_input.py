from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.finance import FinancialFactInput


def _fact(due_date):
    return FinancialFactInput(
        operation_id=uuid4(),
        category="commitment",
        label="Fee",
        amount_rupees=1_000,
        due_date=due_date,
    )


def test_financial_fact_accepts_spoken_rupees_and_month_end_date():
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    next_month = today.replace(day=28) + timedelta(days=4)

    fact = FinancialFactInput(
        operation_id=uuid4(),
        category="commitment",
        label="Daughter school fees",
        amount_rupees="₹1,02,000",
        due_date="end of this month",
    )

    assert fact.amount_rupees == 102_000
    assert fact.due_date == next_month - timedelta(days=next_month.day)


def test_financial_fact_accepts_yesterday_today_tomorrow():
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()

    def fact_with(due_date: str) -> FinancialFactInput:
        return FinancialFactInput(
            operation_id=uuid4(),
            category="income",
            label="Salary",
            amount_rupees=75_000,
            due_date=due_date,
        )

    assert fact_with("yesterday").due_date == today - timedelta(days=1)
    assert fact_with("today").due_date == today
    assert fact_with("tomorrow").due_date == today + timedelta(days=1)


def test_financial_fact_resolves_relative_phrase_a_whitelist_would_miss():
    # The whole point of adding a real parser: this exact phrasing was never going to
    # be one of a hand-picked set of strings, and it shouldn't need to be.
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    assert _fact("in 10 days").due_date == today + timedelta(days=10)


def test_financial_fact_rejects_unparseable_date_phrase():
    with pytest.raises(ValidationError):
        _fact("sometime whenever, you know")


def test_financial_fact_rejects_date_resolved_far_outside_plausible_window():
    # A guess that lands wildly outside any reasonable planning window is exactly as
    # untrustworthy as a phrase that fails to parse at all, and must be rejected the
    # same way rather than silently saved as fact.
    with pytest.raises(ValidationError):
        _fact("in 300 days")
