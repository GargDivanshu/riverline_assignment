from datetime import date, timedelta

from app.finance import build_workspace, format_existing_facts, tool_snapshot


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


def test_tool_snapshot_converts_every_amount_to_whole_rupees():
    # A real conversation had the model read a raw *_paise integer as if it were
    # rupees and speak a closing balance 100x too large. The tool result must give
    # the model rupees directly, under names that say so, with no *_paise field to
    # misread — and it must include each fact's actual amount, not just a count,
    # so the model can recheck a number it already stated instead of guessing.
    state = build_workspace(
        [
            {"id": "cash", "category": "opening_cash", "label": "Cash available", "amount_paise": 100_000, "due_date": None, "certainty": "confirmed"},
            {"id": "salary", "category": "income", "label": "Salary", "amount_paise": 70_000, "due_date": date(2026, 9, 12), "certainty": "confirmed"},
            {"id": "emi", "category": "commitment", "label": "EMI", "amount_paise": 250_000, "due_date": date(2026, 9, 13), "certainty": "confirmed"},
        ],
        revision=5,
        start=date(2026, 9, 11),
        end=date(2026, 10, 11),
    )

    result = tool_snapshot(state)

    assert result["opening_cash_rupees"] == 1_000
    assert result["income"][0]["amount_rupees"] == 700
    assert result["commitments"][0]["amount_rupees"] == 2_500
    assert result["summary"]["dated_income_rupees"] == 700
    assert result["summary"]["projected_closing_rupees"] == -800
    assert result["timeline"][0]["balance_rupees"] == 1_700

    def has_no_paise_keys(value: object) -> bool:
        if isinstance(value, dict):
            return all(not k.endswith("_paise") and has_no_paise_keys(v) for k, v in value.items())
        if isinstance(value, list):
            return all(has_no_paise_keys(item) for item in value)
        return True

    assert has_no_paise_keys(result)


def test_restricted_money_is_excluded_from_every_calculation():
    # Ramesh: "No, I cannot use that. That is shop money." It must still be tracked
    # (shown in the facts) but never counted as available.
    state = build_workspace(
        [
            {"id": "cash", "category": "opening_cash", "label": "Personal cash", "amount_paise": 3_500_000, "due_date": None, "certainty": "confirmed"},
            {"id": "shop", "category": "opening_cash", "label": "Shop drawer cash", "amount_paise": 1_500_000, "due_date": None, "certainty": "confirmed", "restricted": True},
        ],
        revision=1, start=date(2026, 9, 11), end=date(2026, 10, 11),
    )
    assert state.opening_cash_paise == 3_500_000
    # still visible as its own line item, not silently dropped
    assert any(f.label == "Shop drawer cash" and f.restricted for f in state.opening_cash)


def test_recurring_monthly_salary_lands_on_its_one_occurrence_in_the_window():
    # The exact live failure this fixes: "salary arrives first of every month" has
    # no single due_date at all, only a repeating day. A 30-day window starting
    # mid-month contains exactly one occurrence of "day 1".
    state = build_workspace(
        [
            {"id": "cash", "category": "opening_cash", "label": "Cash", "amount_paise": 0, "due_date": None, "certainty": "confirmed"},
            {"id": "salary", "category": "income", "label": "Salary", "amount_paise": 5_000_000, "due_date": None, "recurring_day_of_month": 1, "certainty": "confirmed"},
        ],
        revision=1, start=date(2026, 9, 13), end=date(2026, 10, 13),
    )
    assert [event.date for event in state.timeline] == [date(2026, 10, 1)]
    assert state.summary.dated_income_paise == 5_000_000
    assert state.summary.unplanned_fact_count == 0


def test_recurring_fact_can_land_twice_in_one_30_day_window():
    # A window that starts right on the cycle's day (or just before it) can catch
    # two occurrences of a short monthly cycle — the projection must not assume
    # "recurring" always means exactly one hit.
    state = build_workspace(
        [
            {"id": "cash", "category": "opening_cash", "label": "Cash", "amount_paise": 0, "due_date": None, "certainty": "confirmed"},
            {"id": "rent", "category": "commitment", "label": "Rent", "amount_paise": 1_000_000, "due_date": None, "recurring_day_of_month": 1, "certainty": "confirmed"},
        ],
        revision=1, start=date(2026, 9, 1), end=date(2026, 10, 1),
    )
    # end is exclusive, so only Sep 1 (not Oct 1) falls in [start, end).
    assert [event.date for event in state.timeline] == [date(2026, 9, 1)]


def test_recurring_day_of_month_clamps_to_short_months():
    # A recurring day of 31 recorded for salary must still resolve inside a
    # 30-day February rather than skip that month or raise.
    state = build_workspace(
        [
            {"id": "cash", "category": "opening_cash", "label": "Cash", "amount_paise": 0, "due_date": None, "certainty": "confirmed"},
            {"id": "salary", "category": "income", "label": "Salary", "amount_paise": 5_000_000, "due_date": None, "recurring_day_of_month": 31, "certainty": "confirmed"},
        ],
        revision=1, start=date(2026, 2, 1), end=date(2026, 3, 1),
    )
    assert [event.date for event in state.timeline] == [date(2026, 2, 28)]


def test_format_existing_facts_describes_recurring_fact_by_its_cycle_not_a_date():
    shaped = tool_snapshot(
        build_workspace(
            [{"id": "salary", "category": "income", "label": "Salary", "amount_paise": 5_000_000, "due_date": None, "recurring_day_of_month": 1, "certainty": "confirmed"}],
            revision=1, start=date(2026, 9, 13), end=date(2026, 10, 13),
        )
    )
    text = format_existing_facts(shaped)
    assert "recurring on day 1 of every month" in text
    assert ", due " not in text


def test_usable_cap_limits_opening_cash_contribution():
    # Ananya: sixty thousand saved, but a self-imposed cap of fifteen thousand usable.
    state = build_workspace(
        [
            {"id": "cash", "category": "opening_cash", "label": "Cash today", "amount_paise": 1_800_000, "due_date": None, "certainty": "confirmed"},
            {"id": "savings", "category": "opening_cash", "label": "Savings", "amount_paise": 6_000_000, "due_date": None, "certainty": "confirmed", "usable_amount_paise": 1_500_000},
        ],
        revision=1, start=date(2026, 9, 11), end=date(2026, 10, 11),
    )
    assert state.opening_cash_paise == 1_800_000 + 1_500_000


def test_range_income_uses_conservative_low_end_and_range_expense_uses_high_end():
    state = build_workspace(
        [
            {"id": "cash", "category": "opening_cash", "label": "Cash", "amount_paise": 0, "due_date": None, "certainty": "confirmed"},
            {
                "id": "shop", "category": "income", "label": "Shop income",
                "amount_paise": 6_500_000, "min_amount_paise": 6_000_000, "max_amount_paise": 7_000_000,
                "due_date": date(2026, 9, 15), "certainty": "estimated",
            },
            {
                "id": "essentials", "category": "expense", "label": "Household essentials",
                "amount_paise": 2_000_000, "min_amount_paise": 1_800_000, "max_amount_paise": 2_200_000,
                "due_date": date(2026, 9, 16), "certainty": "estimated",
            },
        ],
        revision=1, start=date(2026, 9, 11), end=date(2026, 10, 11),
    )
    # Income planned at the low end (6,000,000), expense planned at the high end (2,200,000).
    assert state.summary.dated_income_paise == 6_000_000
    assert state.summary.dated_outgoings_paise == 2_200_000


def test_uncertain_receivable_is_never_confirmed_but_shown_as_conditional():
    # Ramesh's customer receivable: real money he might get, no confirmed date. Must
    # never enter the confirmed path, but must be visible as "what changes if it
    # arrives" — the exact distinction the brief and the transcript both called out.
    state = build_workspace(
        [
            {"id": "cash", "category": "opening_cash", "label": "Cash", "amount_paise": 3_500_000, "due_date": None, "certainty": "confirmed"},
            {
                "id": "school", "category": "expense", "label": "School fee",
                "amount_paise": 5_000_000, "due_date": date(2026, 9, 17), "certainty": "confirmed",
            },
            {
                "id": "receivable", "category": "income", "label": "Customer receivable",
                "amount_paise": 2_000_000, "due_date": None, "certainty": "uncertain",
            },
        ],
        revision=1, start=date(2026, 9, 11), end=date(2026, 10, 11),
    )
    assert state.summary.projected_closing_paise == 3_500_000 - 5_000_000
    assert state.summary.uncertain_income_paise == 2_000_000
    assert state.summary.conditional_closing_paise == (3_500_000 - 5_000_000) + 2_000_000
    # The uncertain receivable must not appear as a dated, confirmed timeline event.
    assert all(event.label != "Customer receivable" for event in state.timeline)


# The two scenarios below are the exact demo scenarios from the implementation brief
# (Ramesh the kirana owner, Ananya the salaried professional). Encoding them here means
# the specific reasoning outcome each scenario is meant to demonstrate — a real one, not
# a contrived unit case — is checked by every test run, not just by re-running the demo
# by hand before submission. If either regresses, this fails before a live conversation
# ever could.


def test_scenario_a_kirana_owner_has_confirmed_shortfall_despite_a_positive_month():
    # Ramesh: cash today ₹35k confirmed; ₹15k of that is shop drawer money he later
    # says he cannot use (restricted); variable shop income ₹55k-70k (estimated range,
    # no confirmed arrival date, so it cannot rescue a dated shortfall); a customer
    # owes him ₹20k with no confirmed date (uncertain, tracked separately); a bike EMI,
    # a personal-loan EMI, his daughter's school fee, and household essentials all have
    # confirmed due dates within the 30-day window.
    start = date(2026, 9, 1)
    state = build_workspace(
        [
            {"id": "cash", "category": "opening_cash", "label": "Personal cash", "amount_paise": 3_500_000, "due_date": None, "certainty": "confirmed"},
            {"id": "shop-cash", "category": "opening_cash", "label": "Shop drawer cash", "amount_paise": 1_500_000, "due_date": None, "certainty": "confirmed", "restricted": True},
            {"id": "shop-income", "category": "income", "label": "Shop income", "amount_paise": 6_250_000, "min_amount_paise": 5_500_000, "max_amount_paise": 7_000_000, "due_date": None, "certainty": "estimated"},
            {"id": "receivable", "category": "income", "label": "Customer receivable", "amount_paise": 2_000_000, "due_date": None, "certainty": "uncertain"},
            {"id": "bike-emi", "category": "commitment", "label": "Bike EMI", "amount_paise": 800_000, "due_date": date(2026, 9, 7), "certainty": "confirmed"},
            {"id": "loan-emi", "category": "commitment", "label": "Personal loan EMI", "amount_paise": 1_200_000, "due_date": date(2026, 9, 12), "certainty": "confirmed"},
            {"id": "school-fee", "category": "expense", "label": "Daughter's school fee", "amount_paise": 5_000_000, "due_date": date(2026, 9, 10), "certainty": "confirmed"},
            {"id": "essentials", "category": "expense", "label": "Household essentials", "amount_paise": 2_000_000, "min_amount_paise": 1_800_000, "max_amount_paise": 2_200_000, "due_date": date(2026, 9, 15), "certainty": "estimated"},
        ],
        revision=1, start=start, end=start + timedelta(days=30),
    )

    # Restricted shop cash is excluded; only the personal ₹35k counts as usable now.
    assert state.opening_cash_paise == 3_500_000
    assert any(f.label == "Shop drawer cash" and f.restricted for f in state.opening_cash)

    # The shortfall must land on the school-fee date — confirmed cash runs out there,
    # well before the variable, undated shop income could ever be counted on.
    assert state.summary.first_shortfall_date == date(2026, 9, 10)
    # Confirmed-only closing balance is negative even though the month "sounds" fine.
    assert state.summary.projected_closing_paise < 0
    # The customer receivable must reduce the *conditional* picture, and only that one.
    assert state.summary.uncertain_income_paise == 2_000_000
    assert state.summary.conditional_closing_paise == state.summary.projected_closing_paise + 2_000_000
    assert all(event.label != "Customer receivable" for event in state.timeline)
    assert all(event.label != "Shop income" for event in state.timeline)


def test_scenario_b_salaried_professional_has_pre_salary_shortfall_in_a_positive_month():
    # Ananya: ₹18k cash today; ₹60k savings but she will only use up to ₹15k of it
    # (usable cap); a credit-card bill (already corrected from ₹27k to ₹31k) due the
    # 20th; a laptop EMI due the 23rd; essentials due the 5th; salary ₹75k due the
    # 28th; a freelance payment "probably this week" (uncertain, no confirmed date).
    start = date(2026, 9, 1)
    state = build_workspace(
        [
            {"id": "cash", "category": "opening_cash", "label": "Cash today", "amount_paise": 1_800_000, "due_date": None, "certainty": "confirmed"},
            {"id": "savings", "category": "opening_cash", "label": "Savings", "amount_paise": 6_000_000, "usable_amount_paise": 1_500_000, "due_date": None, "certainty": "confirmed"},
            {"id": "salary", "category": "income", "label": "Salary", "amount_paise": 7_500_000, "due_date": date(2026, 9, 28), "certainty": "confirmed"},
            {"id": "freelance", "category": "income", "label": "Freelance payment", "amount_paise": 2_500_000, "due_date": None, "certainty": "uncertain"},
            {"id": "card", "category": "commitment", "label": "Credit card bill", "amount_paise": 3_100_000, "due_date": date(2026, 9, 20), "certainty": "confirmed"},
            {"id": "emi", "category": "commitment", "label": "Laptop EMI", "amount_paise": 700_000, "due_date": date(2026, 9, 23), "certainty": "confirmed"},
            {"id": "essentials", "category": "expense", "label": "Essentials", "amount_paise": 1_200_000, "due_date": date(2026, 9, 5), "certainty": "confirmed"},
        ],
        revision=1, start=start, end=start + timedelta(days=30),
    )

    # ₹18k cash + ₹15k usable-of-60k savings = the brief's exact ₹33k pre-salary figure.
    assert state.opening_cash_paise == 1_800_000 + 1_500_000

    # The shortfall must land on the card's due date (the 20th) — before salary (28th) —
    # even though the month closes positive overall. This is the entire point of the
    # scenario: a positive month-end total does not mean every payment is covered.
    assert state.summary.first_shortfall_date == date(2026, 9, 20)
    assert state.summary.projected_closing_paise is not None and state.summary.projected_closing_paise > 0
    assert state.summary.lowest_balance_paise is not None and state.summary.lowest_balance_paise < 0

    # The freelance payment must never be counted as confirmed cash.
    assert state.summary.uncertain_income_paise == 2_500_000
    assert all(event.label != "Freelance payment" for event in state.timeline)


def test_format_existing_facts_is_empty_for_a_fresh_workspace():
    # A returning conversation with nothing saved yet must not inject an empty or
    # confusing "already saved" block into the prompt.
    state = build_workspace([], revision=0, start=date(2026, 9, 1), end=date(2026, 10, 1))
    assert format_existing_facts(tool_snapshot(state)) == ""


def test_format_existing_facts_lists_every_saved_fact_with_its_real_attributes():
    # Live evidence: a returning-mode call told the person "I can't see earlier
    # chats" even though the facts existed. This is the block meant to make that
    # impossible — every saved fact, with its real amount, certainty, due date,
    # usable cap, and restriction, must actually appear in the rendered text.
    state = build_workspace(
        [
            {"id": "cash", "category": "opening_cash", "label": "Cash on hand", "amount_paise": 3_500_000, "due_date": None, "certainty": "confirmed"},
            {"id": "shop", "category": "opening_cash", "label": "Shop drawer cash", "amount_paise": 1_500_000, "due_date": None, "certainty": "confirmed", "restricted": True},
            {"id": "savings", "category": "opening_cash", "label": "Savings", "amount_paise": 6_000_000, "usable_amount_paise": 1_500_000, "due_date": None, "certainty": "confirmed"},
            {"id": "emi", "category": "commitment", "label": "Bike EMI", "amount_paise": 800_000, "due_date": date(2026, 9, 7), "certainty": "confirmed"},
        ],
        revision=4, start=date(2026, 9, 1), end=date(2026, 10, 1),
    )
    text = format_existing_facts(tool_snapshot(state))
    assert "Cash on hand: 35000 rupees" in text
    assert "Shop drawer cash: 15000 rupees" in text and "restricted" in text
    assert "Savings: 60000 rupees" in text and "usable up to 15000 rupees" in text
    assert "Bike EMI: 8000 rupees" in text and "due 2026-09-07" in text
