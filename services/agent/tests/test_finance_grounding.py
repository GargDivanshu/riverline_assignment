"""Grounding checks: a tool call must be evidenced by what was actually said.

Three live failures, all in one call, none of them tool_rejected at the time:

1. "I have eighteen thousand rupees" was saved as opening_cash = 10000.
2. "I have a ₹22,000 card bill" (no date at all) was saved with due_date =
   2026-09-25, certainty confirmed.
3. "the rent was already paid" resolved four unrelated subscriptions along
   with rent — each of the five calls "succeeded" individually.

None of these were schema violations; the data was well-formed and the tool
calls succeeded. These tests cover the deterministic checks that now catch
each one before it reaches the database.
"""

from uuid import uuid4

from app.finance import (
    FinancialFactInput,
    amount_matches_utterance,
    date_is_evidenced,
    resolution_target_check,
)
from app.numbers import extract_rupee_amounts


def _fact(**fields) -> FinancialFactInput:
    fields.setdefault("category", "opening_cash")
    fields.setdefault("label", "Bank cash available")
    fields.setdefault("certainty", "confirmed")
    return FinancialFactInput(operation_id=uuid4(), **fields)


# --- Test 1 / 11: exact amount must match what was actually said -----------


def test_amount_matching_the_utterance_is_never_blocked():
    fact = _fact(amount_rupees=18_000)
    assert amount_matches_utterance(fact, "I have eighteen thousand rupees available.") is None


def test_amount_disagreeing_with_the_utterance_is_rejected():
    # The exact live failure: "eighteen thousand" spoken, 10000 proposed.
    fact = _fact(amount_rupees=10_000)
    reason = amount_matches_utterance(fact, "I have eighteen thousand rupees available in my bank.")
    assert reason is not None
    assert "10000" in reason or "10_000" in reason.replace(",", "")


def test_amount_check_is_skipped_for_a_stated_range():
    # Speech states ranges far too loosely ("sixty to seventy thousand") for a
    # deterministic word check to be fair — the range mechanism is already
    # covered by its own dedicated validation.
    fact = _fact(category="income", label="Freelance income", min_amount_rupees=60_000, max_amount_rupees=70_000, certainty="estimated")
    assert amount_matches_utterance(fact, "I make around sixty five thousand a month.") is None


def test_amount_check_does_not_block_when_nothing_extractable_from_utterance():
    # No confident candidate in the utterance means no evidence either way —
    # never a reason to block a plausible amount.
    fact = _fact(amount_rupees=18_000)
    assert amount_matches_utterance(fact, "I have some money saved up, not sure exactly.") is None


def test_amount_check_only_applies_to_a_newly_stated_amount():
    # A patch that never touches amount_rupees at all must not be checked
    # against it — this is a correction to something unrelated.
    fact = FinancialFactInput(operation_id=uuid4(), fact_id=uuid4(), recurring_day_of_month=25)
    assert amount_matches_utterance(fact, "totally unrelated sentence with ninety thousand in it") is None


# --- Test 2 / 3 / 10: a date must be evidenced, never invented --------------


def test_due_date_with_no_supporting_words_at_all_is_rejected():
    # The exact live failure: no date mentioned anywhere, yet a due_date was
    # about to be saved as confirmed.
    fact = _fact(category="commitment", label="Credit card bill", amount_rupees=22_000, due_date="2026-09-25")
    utterance = "this month I have some twenty-two thousand rupees in the card bill which I need to be paying"
    assert date_is_evidenced(fact, utterance) is False


def test_due_date_explicitly_stated_is_accepted():
    fact = _fact(category="commitment", label="Credit card bill", amount_rupees=22_000, due_date="2026-09-25")
    utterance = "I have a twenty-two thousand rupee card bill due on the 25th"
    assert date_is_evidenced(fact, utterance) is True


def test_recurring_day_with_no_supporting_words_is_rejected():
    fact = _fact(category="income", label="Salary", amount_rupees=75_000, recurring_day_of_month=1)
    assert date_is_evidenced(fact, "my salary is seventy five thousand a month") is False


def test_recurring_day_explicitly_stated_is_accepted():
    fact = _fact(category="income", label="Salary", amount_rupees=75_000, recurring_day_of_month=1)
    assert date_is_evidenced(fact, "my salary arrives on the first of every month") is True


def test_no_date_field_present_never_needs_evidence():
    fact = _fact(amount_rupees=18_000)
    assert date_is_evidenced(fact, "I have eighteen thousand rupees") is True


def test_a_system_prompt_example_date_does_not_leak_into_evidence():
    # A card bill example date living in the instructions is never something
    # the person said — the check only ever looks at the actual utterance.
    fact = _fact(category="commitment", label="Credit card bill", amount_rupees=22_000, due_date="2026-09-25")
    assert date_is_evidenced(fact, "twenty two thousand rupees for the card") is False


# --- Test 4 / 5 / 9: a resolution must be targeted, not batched -------------


def test_resolving_the_one_named_fact_is_allowed():
    reason = resolution_target_check(
        "Rent",
        "the rent was actually paid earlier on, by the 5th of this month",
        ["GPT subscription", "AI subscription", "Adobe subscription"],
    )
    assert reason is None


def test_resolving_an_unrelated_fact_from_the_same_batch_is_rejected():
    # The exact live failure: this statement only ever named rent.
    for unrelated_label in ["GPT subscription", "AI subscription", "Adobe subscription"]:
        reason = resolution_target_check(
            unrelated_label,
            "the rent was actually paid earlier on, by the 5th of this month",
            ["Rent", "GPT subscription", "AI subscription", "Adobe subscription"],
        )
        assert reason is not None, f"{unrelated_label} should have been rejected"


def test_explicit_multi_resolution_allows_each_named_item():
    utterance = "Rent and Adobe have already been paid"
    others_for_rent = ["GPT subscription", "AI subscription", "Adobe subscription"]
    others_for_adobe = ["Rent", "GPT subscription", "AI subscription"]
    assert resolution_target_check("Rent", utterance, others_for_rent) is None
    assert resolution_target_check("Adobe subscription", utterance, others_for_adobe) is None
    # Still correctly rejects the ones not named.
    assert resolution_target_check("GPT subscription", utterance, others_for_rent) is not None


def test_ambiguous_generic_reference_is_rejected():
    reason = resolution_target_check("HDFC card", "I paid the card", ["ICICI card"])
    assert reason is not None


def test_no_utterance_context_does_not_block():
    # A resolution reached without any tracked utterance (e.g. a non-voice
    # caller) is not something this check can evaluate — it must not block.
    assert resolution_target_check("Rent", "", ["GPT subscription"]) is None


# --- The underlying number extractor ---------------------------------------


def test_extract_rupee_amounts_reads_indian_spoken_numbers():
    assert extract_rupee_amounts("eighteen thousand rupees") == [18_000]
    assert extract_rupee_amounts("one lakh twenty five thousand") == [125_000]
    assert extract_rupee_amounts("twenty-two hundred rupees") == [2_200]
    assert extract_rupee_amounts("₹22,000 for the card") == [22_000]
