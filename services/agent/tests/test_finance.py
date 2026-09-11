from datetime import date

from app.finance import build_workspace


def test_projection_uses_only_dated_non_uncertain_facts_and_keeps_paise_exactly():
    state = build_workspace(
        [
            {"id": "cash", "category": "opening_cash", "label": "Cash available", "amount_paise": 100_000, "due_date": None, "certainty": "confirmed"},
            {"id": "salary", "category": "income", "label": "Salary", "amount_paise": 70_000, "due_date": date(2026, 9, 12), "certainty": "confirmed"},
            {"id": "emi", "category": "commitment", "label": "EMI", "amount_paise": 250_000, "due_date": date(2026, 9, 13), "certainty": "confirmed"},
            {"id": "food", "category": "expense", "label": "Food", "amount_paise": 20_000, "due_date": None, "certainty": "estimated"},
            {"id": "freelance", "category": "income", "label": "Freelance", "amount_paise": 90_000, "due_date": date(2026, 9, 14), "certainty": "uncertain"},
        ],
        revision=5,
        start=date(2026, 9, 11),
        end=date(2026, 10, 11),
    )

    assert state.plan_status == "ready"
    assert state.summary.dated_income_paise == 70_000
    assert state.summary.dated_outgoings_paise == 250_000
    assert state.summary.projected_closing_paise == -80_000
    assert state.summary.first_shortfall_date == date(2026, 9, 13)
    assert state.summary.unplanned_fact_count == 1
    assert [event.balance_paise for event in state.timeline] == [170_000, -80_000]
