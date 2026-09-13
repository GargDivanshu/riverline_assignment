"""Patch/merge semantics and the tool-rejection error contract.

The live failure these exist to fix: correcting an existing credit-card fact to
add a recurring day ("25th of every month") was rejected because the
whole-object validator still demanded an amount be resupplied, even though the
amount was not changing. The rejection then carried an empty field name and no
real message (`invalid_fields: [""]`), so the model had no way to diagnose it
and spiraled into unrelated questions about years and month windows instead.
"""

from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.finance import FinancialFactInput, fact_result, merge_patch, shape_validation_errors


def _existing(**overrides) -> dict:
    base = {
        "category": "commitment",
        "label": "Credit card spending",
        "amount_paise": 1_250_000,
        "due_date": None,
        "certainty": "estimated",
        "min_amount_paise": 1_000_000,
        "max_amount_paise": 1_500_000,
        "usable_amount_paise": None,
        "restricted": False,
        "recurring_day_of_month": None,
        "timing_note": None,
    }
    base.update(overrides)
    return base


def _patch(**fields) -> FinancialFactInput:
    return FinancialFactInput(operation_id=uuid4(), fact_id=uuid4(), **fields)


def test_recurring_day_patch_preserves_exact_amount():
    # Test 1: salary ₹1,00,000 already stored; patching only recurring_day_of_month
    # must not touch the amount at all.
    existing = _existing(
        category="income", label="Salary", amount_paise=10_000_000,
        min_amount_paise=None, max_amount_paise=None, certainty="confirmed",
    )
    merged = merge_patch(existing, _patch(recurring_day_of_month=1))
    assert merged.amount_rupees == 100_000
    assert merged.recurring_day_of_month == 1


def test_recurring_day_patch_preserves_range():
    # Test 2: the exact live failure. Credit card spend ₹10k-15k already stored;
    # patching only recurring_day_of_month must keep the range untouched and must
    # not raise for "missing" an amount that was never being changed.
    merged = merge_patch(_existing(), _patch(recurring_day_of_month=25))
    assert merged.min_amount_rupees == 10_000
    assert merged.max_amount_rupees == 15_000
    assert merged.recurring_day_of_month == 25
    assert merged.category == "commitment"
    assert merged.label == "Credit card spending"


def test_new_fact_without_amount_is_rejected_with_a_real_message():
    # Test 3 + 5: a genuinely new fact (no fact_id) still requires an amount, and
    # the rejection must carry a real, non-empty message with no field to blame
    # (a whole-object rule) rather than the old empty-string field name.
    with pytest.raises(ValidationError) as excinfo:
        FinancialFactInput(operation_id=uuid4(), category="income", label="Salary", certainty="confirmed")
    errors = shape_validation_errors(excinfo.value)
    assert errors
    assert errors[0]["field"] is None
    assert errors[0]["message"] == "a monetary value is required when creating a new financial fact"
    assert "Value error" not in errors[0]["message"]


def test_shape_validation_errors_never_returns_an_empty_field_name():
    # The literal bug: loc=() used to become "" via "".join(...), which told the
    # model nothing. field must be None, never an empty string, when a validator
    # error isn't about one specific field.
    with pytest.raises(ValidationError) as excinfo:
        FinancialFactInput(
            operation_id=uuid4(), category="income", label="Shop income",
            min_amount_rupees=70_000, max_amount_rupees=60_000, certainty="estimated",
        )
    for error in shape_validation_errors(excinfo.value):
        assert error["field"] != ""
        assert error["message"]


def test_patch_does_not_require_amount_even_when_marking_resolved():
    # Test 8: "I paid that off" must keep working after the patch refactor —
    # marking resolved is itself a patch and must not require the amount either.
    merged = merge_patch(_existing(min_amount_paise=None, max_amount_paise=None), _patch(resolved=True))
    assert merged.amount_rupees == 12_500
    patch = _patch(resolved=True)
    assert patch.resolved is True


def test_correction_replaces_amount_and_clears_stale_range():
    # Test 7: ₹27k card bill corrected to ₹31k. A single new amount supersedes an
    # old range rather than sitting alongside it as a contradictory leftover.
    existing = _existing(category="commitment", label="Card bill", amount_paise=2_700_000)
    merged = merge_patch(existing, _patch(amount_rupees=31_000))
    assert merged.amount_rupees == 31_000
    assert merged.min_amount_rupees is None
    assert merged.max_amount_rupees is None


def test_new_range_recomputes_amount_instead_of_keeping_the_stale_point_value():
    # The reverse of the above: replacing a plain amount with a new range must
    # not leave the old point amount stale — the range's own midpoint takes over.
    existing = _existing(
        min_amount_paise=None, max_amount_paise=None, amount_paise=2_700_000,
    )
    merged = merge_patch(existing, _patch(min_amount_rupees=20_000, max_amount_rupees=24_000))
    assert merged.amount_rupees == 22_000
    assert merged.min_amount_rupees == 20_000
    assert merged.max_amount_rupees == 24_000


def test_recurring_day_and_due_date_are_mutually_exclusive_on_patch():
    # Setting one must clear the other rather than leaving a stale value from
    # whichever shape the fact used to be described as.
    existing = _existing(due_date=date(2026, 9, 25), recurring_day_of_month=None)
    merged = merge_patch(existing, _patch(recurring_day_of_month=25))
    assert merged.recurring_day_of_month == 25
    assert merged.due_date is None

    existing_recurring = _existing(due_date=None, recurring_day_of_month=25)
    merged_back = merge_patch(existing_recurring, _patch(due_date="2026-10-05"))
    assert merged_back.due_date == date(2026, 10, 5)
    assert merged_back.recurring_day_of_month is None


def test_unrelated_fields_are_left_untouched_by_a_narrow_patch():
    # certainty in particular: earlier code always overwrote it with the
    # "confirmed" default whenever the model omitted it on a correction call.
    # Since a real tool call for a correction still resends certainty in
    # practice (it is required by the tool schema), this is a defence for a
    # patch built without it, e.g. constructed directly as here.
    existing = _existing(certainty="estimated", restricted=True)
    merged = merge_patch(existing, FinancialFactInput(operation_id=uuid4(), fact_id=uuid4(), recurring_day_of_month=25))
    assert merged.certainty == "estimated"
    assert merged.restricted is True


def test_fact_result_reports_what_actually_persisted():
    # Item 26: a mutation's result must be self-sufficient, not something the
    # model has to re-derive from the whole workspace.
    merged = merge_patch(_existing(), _patch(recurring_day_of_month=25))
    result = fact_result(uuid4(), merged, resolved=False)
    assert result["min_amount_rupees"] == 10_000
    assert result["max_amount_rupees"] == 15_000
    assert result["recurring_day_of_month"] == 25
    assert result["resolved"] is False


def test_timing_note_round_trips_through_a_patch():
    merged = merge_patch(_existing(), _patch(timing_note="may arrive a day late"))
    assert merged.timing_note == "may arrive a day late"
    result = fact_result(uuid4(), merged, resolved=False)
    assert result["timing_note"] == "may arrive a day late"
