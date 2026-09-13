"""Cross-fact consistency for new income: catching a double-count that no
single-call grounding check can see.

The live failure: an aggregate income range (₹60k-75k) was already active.
Many turns later — after the card, rent, subscriptions, and cash were all
discussed in between — the person explained that range comes from two
clients and named one client's specific expected payment (₹35k by a date).
The individual tool call was entirely grounded (the amount and date were
both genuinely said) and get_financial_snapshot had already been called
right before it, so the range was sitting right there in context — yet the
model still created a second, additive income fact on top of it. This is a
relationship between two facts, not a property of either one alone, which is
exactly why the amount/date grounding checks (test_finance_grounding.py)
cannot catch it and a separate, deterministic check is needed.
"""

from uuid import uuid4

from app.finance import FinancialFactInput, income_overlap_risk
from app.models import MoneyFact


def _range_fact(min_rupees=60_000, max_rupees=75_000, label="Freelance income range") -> MoneyFact:
    return MoneyFact(
        id=str(uuid4()), label=label, amount_paise=(min_rupees + max_rupees) * 50,
        min_amount_paise=min_rupees * 100, max_amount_paise=max_rupees * 100, certainty="estimated",
    )


def _candidate(amount_rupees, label="Client payment expected", due_date=None) -> FinancialFactInput:
    return FinancialFactInput(
        operation_id=uuid4(), category="income", label=label, amount_rupees=amount_rupees,
        due_date=due_date, certainty="estimated",
    )


# Test A — distant aggregate/component: nothing in the guard depends on how
# recently the range was stated, only on it being active and the new
# candidate's own recent context mentioning the same source.
def test_a_distant_aggregate_still_triggers_reconciliation():
    aggregate = _range_fact()
    candidate = _candidate(35_000, due_date="2026-09-22")
    context = "I told you about my freelance income. There are two clients actually, one is reliable."
    result = income_overlap_risk(candidate, [aggregate], context)
    assert result is not None
    assert result["status"] == "needs_reconciliation"
    assert result["existing_range_rupees"] == [60_000, 75_000]
    assert result["candidate_amount_rupees"] == 35_000


# Test B — explicit component language: unambiguous, no question needed.
def test_b_explicit_component_language_needs_no_clarifying_question():
    aggregate = _range_fact()
    candidate = _candidate(35_000)
    context = "My sixty to seventy five thousand total comes from two clients. One pays thirty five thousand."
    result = income_overlap_risk(candidate, [aggregate], context)
    assert result is not None
    assert result["requires_clarifying_question"] is False


# Test C — explicit additive language: bypasses the guard entirely.
def test_c_explicit_additive_language_bypasses_the_guard():
    aggregate = _range_fact()
    candidate = _candidate(35_000, label="Extra freelance payment")
    context = "Apart from the sixty to seventy five thousand freelance range, I have another payment coming."
    assert income_overlap_risk(candidate, [aggregate], context) is None


# Test D — ambiguous later payment: needs a clarifying question.
def test_d_ambiguous_relationship_needs_a_clarifying_question():
    aggregate = _range_fact()
    candidate = _candidate(35_000, due_date="2026-09-22")
    context = "A client will pay me thirty five thousand next week."
    result = income_overlap_risk(candidate, [aggregate], context)
    assert result is not None
    assert result["requires_clarifying_question"] is True


# Test E — conversational distance: the guard evaluates overlap using active
# state (the stored fact), not proximity of the aggregate's own mention in
# recent text — the aggregate itself need not be freshly repeated at all.
def test_e_guard_uses_active_state_not_recency_of_the_aggregate_mention():
    aggregate = _range_fact()
    candidate = _candidate(35_000)
    # "freelance" never appears again here — only the candidate's own recent
    # turn, which still shares "client" with nothing in the aggregate's own
    # label except through context, is what ties it back.
    context = "One of my clients is going to pay me thirty five thousand."
    result = income_overlap_risk(candidate, [aggregate], context)
    assert result is not None


# Test F — no aggregate exists: create normally.
def test_f_no_existing_aggregate_creates_normally():
    candidate = _candidate(35_000, due_date="2026-09-22")
    assert income_overlap_risk(candidate, [], "a client will pay me thirty five thousand") is None


def test_a_correction_via_fact_id_is_never_subject_to_this_guard():
    aggregate = _range_fact()
    patch = FinancialFactInput(operation_id=uuid4(), fact_id=uuid4(), category="income", amount_rupees=35_000)
    assert income_overlap_risk(patch, [aggregate], "one client pays thirty five thousand") is None


def test_an_amount_larger_than_the_whole_range_is_not_treated_as_a_component():
    # ₹90k cannot plausibly be "part of" a ₹60k-75k range — this is a second,
    # genuinely separate income source even without additive language.
    aggregate = _range_fact()
    candidate = _candidate(90_000, label="Consulting retainer")
    context = "A separate consulting client pays me ninety thousand."
    assert income_overlap_risk(candidate, [aggregate], context) is None


def test_a_range_amount_with_no_shared_source_context_is_not_flagged():
    # Numerically inside the range, but nothing in the recent context ties it
    # to the same freelance/client source at all — an unrelated, genuinely
    # separate income mention should not be blocked on numeric coincidence
    # alone.
    aggregate = _range_fact()
    candidate = _candidate(30_000, label="Salary")
    context = "My day job pays me a fixed salary every month."
    assert income_overlap_risk(candidate, [aggregate], context) is None
