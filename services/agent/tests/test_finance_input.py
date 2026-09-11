from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.finance import FinancialFactInput


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
