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


def test_financial_fact_accepts_a_range_and_fills_amount_rupees_with_midpoint():
    # A kirana owner's "sixty to seventy thousand" shop income — the range must be
    # kept, not collapsed to one guessed figure, while still giving every other part
    # of the system (which expects a single amount_rupees) something to work with.
    fact = FinancialFactInput(
        operation_id=uuid4(),
        category="income",
        label="Shop income",
        min_amount_rupees=60_000,
        max_amount_rupees=70_000,
        certainty="estimated",
    )
    assert fact.min_amount_rupees == 60_000
    assert fact.max_amount_rupees == 70_000
    assert fact.amount_rupees == 65_000


def test_financial_fact_rejects_incomplete_range():
    with pytest.raises(ValidationError):
        FinancialFactInput(
            operation_id=uuid4(), category="income", label="Shop income",
            min_amount_rupees=60_000, certainty="estimated",
        )


def test_financial_fact_rejects_inverted_range():
    with pytest.raises(ValidationError):
        FinancialFactInput(
            operation_id=uuid4(), category="income", label="Shop income",
            min_amount_rupees=70_000, max_amount_rupees=60_000, certainty="estimated",
        )


def test_financial_fact_rejects_missing_amount_and_range():
    with pytest.raises(ValidationError):
        FinancialFactInput(operation_id=uuid4(), category="income", label="Shop income")


def test_financial_fact_accepts_usable_cap_on_protected_savings():
    # Ananya's "sixty thousand saved, but I don't want to use more than fifteen".
    fact = FinancialFactInput(
        operation_id=uuid4(), category="opening_cash", label="Savings",
        amount_rupees=60_000, usable_amount_rupees=15_000,
    )
    assert fact.amount_rupees == 60_000
    assert fact.usable_amount_rupees == 15_000


def test_financial_fact_rejects_usable_cap_larger_than_amount():
    with pytest.raises(ValidationError):
        FinancialFactInput(
            operation_id=uuid4(), category="opening_cash", label="Savings",
            amount_rupees=15_000, usable_amount_rupees=60_000,
        )


def test_financial_fact_accepts_restricted_money():
    # Ramesh's shop-drawer cash: "No, I cannot use that. That is shop money."
    fact = FinancialFactInput(
        operation_id=uuid4(), category="opening_cash", label="Shop drawer cash",
        amount_rupees=15_000, restricted=True,
    )
    assert fact.restricted is True


def test_financial_fact_accepts_resolved_correction_with_fact_id():
    # "I paid that card off" must correct the existing fact, not create a new
    # "(paid)" one — the exact workaround observed live that left three separate
    # credit-card-shaped records instead of one.
    fact = FinancialFactInput(
        operation_id=uuid4(), category="commitment", label="Credit card repayment",
        amount_rupees=5_000, fact_id=uuid4(), resolved=True,
    )
    assert fact.resolved is True


def test_financial_fact_rejects_resolved_without_fact_id():
    # There is no such thing as recording a brand-new fact that is already paid —
    # "resolved" only ever corrects something that already exists.
    with pytest.raises(ValidationError):
        FinancialFactInput(
            operation_id=uuid4(), category="commitment", label="Credit card repayment",
            amount_rupees=5_000, resolved=True,
        )


def test_financial_fact_accepts_recurring_day_of_month_with_no_due_date():
    # The live failure this fixes: "salary arrives first of every month" is not a
    # due_date at all — dateparser has no concept of a repeating date, and forcing
    # it through due_date produced a tool_rejected loop that made a person hang
    # up. recurring_day_of_month is its own field, no due_date required.
    fact = FinancialFactInput(
        operation_id=uuid4(), category="income", label="Salary",
        amount_rupees=50_000, recurring_day_of_month=1, certainty="confirmed",
    )
    assert fact.recurring_day_of_month == 1
    assert fact.due_date is None


def test_financial_fact_rejects_recurring_day_of_month_out_of_range():
    with pytest.raises(ValidationError):
        FinancialFactInput(
            operation_id=uuid4(), category="income", label="Salary",
            amount_rupees=50_000, recurring_day_of_month=32,
        )


def test_financial_fact_extracts_recurring_day_from_due_date_text_as_a_fallback():
    # Defense in depth: even if a model lapses back into describing this through
    # due_date text instead of the dedicated field, the exact live phrasing must
    # resolve to a recurring fact, not an unparseable-date rejection.
    fact = FinancialFactInput(
        operation_id=uuid4(), category="income", label="Salary",
        amount_rupees=50_000, due_date="first of every month",
    )
    assert fact.recurring_day_of_month == 1
    assert fact.due_date is None


def test_financial_fact_extracts_recurring_day_from_numeric_due_date_text():
    fact = FinancialFactInput(
        operation_id=uuid4(), category="commitment", label="Rent",
        amount_rupees=15_000, due_date="5th of every month",
    )
    assert fact.recurring_day_of_month == 5
    assert fact.due_date is None
