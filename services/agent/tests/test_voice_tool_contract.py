"""The model's only channel for tool-outcome truth is the result_callback payload.

The live failure this exists to guard against: the model said "I tried to save
that timing update, but it didn't go through" and "the update is still being
processed" when no tool call had actually failed at all — logs showed zero
tool_rejected/tool_failed events. That fabrication happens in the model's own
free text and can't be unit tested directly, but the one thing code *can*
guarantee is that the payload the model receives from record_financial_fact and
get_financial_snapshot never itself contains anything but a real, immediate
outcome: "success" (with the actual persisted data) or "rejected" (with a real
reason) — never "pending" or "processing", and never a success claim for
something that didn't actually persist.
"""

import asyncio
import time
from datetime import date, timedelta
from types import SimpleNamespace
from uuid import uuid4

from app.finance import build_workspace, fact_result, merge_patch, FactNotFoundError
from app.voice.pipeline import _get_snapshot, _record_fact


def _to_row(item):
    return {
        "category": item.category,
        "label": item.label,
        "amount_paise": item.amount_rupees * 100,
        "due_date": item.due_date,
        "certainty": item.certainty,
        "min_amount_paise": item.min_amount_rupees * 100 if item.min_amount_rupees is not None else None,
        "max_amount_paise": item.max_amount_rupees * 100 if item.max_amount_rupees is not None else None,
        "usable_amount_paise": item.usable_amount_rupees * 100 if item.usable_amount_rupees is not None else None,
        "restricted": item.restricted,
        "recurring_day_of_month": item.recurring_day_of_month,
        "timing_note": item.timing_note,
    }


class FakeFinanceStore:
    """An in-memory stand-in exercising the real merge_patch/build_workspace/
    fact_result logic — the same functions FinanceStore.record() calls — without
    needing a live Postgres, so _record_fact's actual contract-shaping code runs
    end to end exactly as it does against the real store."""

    def __init__(self):
        self._facts: dict[str, dict] = {}
        self.revision = 0

    async def record(self, user_id, item):
        if item.fact_id:
            key = str(item.fact_id)
            existing = self._facts.get(key)
            if existing is None:
                raise FactNotFoundError("no active financial fact exists with this id")
            merged = merge_patch(existing, item)
            if item.resolved:
                del self._facts[key]
            else:
                self._facts[key] = _to_row(merged)
            fact_id, persisted, resolved = key, merged, item.resolved
        else:
            fact_id = str(uuid4())
            self._facts[fact_id] = _to_row(item)
            persisted, resolved = item, False
        self.revision += 1
        workspace = await self.workspace(user_id)
        return workspace, fact_result(fact_id, persisted, resolved=resolved)

    async def workspace(self, user_id):
        rows = [{"id": key, **value} for key, value in self._facts.items()]
        start = date(2026, 9, 13)
        return build_workspace(rows, self.revision, start, start + timedelta(days=30))

    async def record_conversation_event(self, *args, **kwargs):
        return None


def _session(store, utterance="", recent=None):
    return SimpleNamespace(
        id="session-1",
        owner="owner-1",
        finance_store=store,
        created_monotonic=time.monotonic(),
        last_user_utterance=utterance,
        recent_user_utterances=recent if recent is not None else ([utterance] if utterance else []),
    )


def _params(arguments):
    captured = {}

    async def result_callback(payload):
        captured["payload"] = payload

    return SimpleNamespace(arguments=arguments, result_callback=result_callback), captured


def test_successful_create_reports_a_real_persisted_fact_never_a_pending_state():
    async def scenario():
        store = FakeFinanceStore()
        session = _session(store)
        params, captured = _params(
            {"category": "income", "label": "Salary", "amount_rupees": 75_000, "certainty": "confirmed"}
        )
        await _record_fact(params, session)
        payload = captured["payload"]
        assert payload["status"] == "success"
        assert payload["fact"]["amount_rupees"] == 75_000
        assert payload["revision"] == store.revision
        # The exact bug this guards against: nothing in this contract can ever
        # claim an in-between state the model might narrate as "still processing".
        assert payload["status"] in {"success", "rejected"}

    asyncio.run(scenario())


def test_patch_preserving_a_range_reports_the_real_merged_fact():
    # The live failure: patching a recurring day onto a ranged expense must
    # report back the actual persisted range, not something the model has to
    # guess at or that could be silently wrong.
    async def scenario():
        store = FakeFinanceStore()
        session = _session(store)
        create_params, create_captured = _params(
            {
                "category": "commitment",
                "label": "Credit card spending",
                "min_amount_rupees": 10_000,
                "max_amount_rupees": 15_000,
                "certainty": "estimated",
            }
        )
        await _record_fact(create_params, session)
        fact_id = create_captured["payload"]["fact"]["id"]

        patch_params, patch_captured = _params({"fact_id": fact_id, "recurring_day_of_month": 25})
        await _record_fact(patch_params, session)
        payload = patch_captured["payload"]
        assert payload["status"] == "success"
        assert payload["fact"]["min_amount_rupees"] == 10_000
        assert payload["fact"]["max_amount_rupees"] == 15_000
        assert payload["fact"]["recurring_day_of_month"] == 25

    asyncio.run(scenario())


def test_rejection_carries_a_real_message_never_a_fabricated_pending_status():
    async def scenario():
        store = FakeFinanceStore()
        session = _session(store)
        params, captured = _params({"category": "income", "label": "Salary", "certainty": "confirmed"})
        await _record_fact(params, session)
        payload = captured["payload"]
        assert payload["status"] == "rejected"
        assert payload["error_code"] == "financial_fact_validation_failed"
        assert payload["errors"][0]["message"]
        assert payload["status"] != "processing"
        assert payload["status"] != "pending"

    asyncio.run(scenario())


def test_patch_to_a_stale_fact_id_gets_its_own_explicit_error_code():
    async def scenario():
        store = FakeFinanceStore()
        session = _session(store)
        params, captured = _params({"fact_id": str(uuid4()), "recurring_day_of_month": 5})
        await _record_fact(params, session)
        payload = captured["payload"]
        assert payload["status"] == "rejected"
        assert payload["error_code"] == "fact_not_found"

    asyncio.run(scenario())


def test_amount_mismatch_is_rejected_before_it_ever_reaches_the_store():
    # The exact live failure end to end: "eighteen thousand" spoken, 10000
    # proposed by the tool call — must never persist.
    async def scenario():
        store = FakeFinanceStore()
        session = _session(store, utterance="I have eighteen thousand rupees available in my bank.")
        params, captured = _params(
            {"category": "opening_cash", "label": "Bank cash", "amount_rupees": 10_000, "certainty": "confirmed"}
        )
        await _record_fact(params, session)
        payload = captured["payload"]
        assert payload["status"] == "rejected"
        assert payload["error_code"] == "amount_transcript_mismatch"
        assert payload["proposed_amount_rupees"] == 10_000
        assert 18_000 in payload["user_amount_rupees"]
        assert store._facts == {}  # nothing persisted

    asyncio.run(scenario())


def test_unevidenced_due_date_is_rejected_before_it_ever_reaches_the_store():
    # The exact other live failure: no date mentioned at all, yet a due_date
    # was about to be saved as confirmed.
    async def scenario():
        store = FakeFinanceStore()
        session = _session(
            store,
            utterance="this month I have some twenty-two thousand rupees in the card bill which I need to be paying",
        )
        params, captured = _params(
            {
                "category": "commitment",
                "label": "Credit card bill",
                "amount_rupees": 22_000,
                "due_date": "2026-09-25",
                "certainty": "confirmed",
            }
        )
        await _record_fact(params, session)
        payload = captured["payload"]
        assert payload["status"] == "rejected"
        assert payload["error_code"] == "date_not_evidenced"
        assert store._facts == {}

    asyncio.run(scenario())


def test_resolving_an_unnamed_fact_is_rejected_even_though_the_id_is_real():
    # The exact live failure: "the rent was already paid" must not resolve a
    # completely unrelated subscription just because fact_id points at a real,
    # active fact.
    async def scenario():
        store = FakeFinanceStore()
        session = _session(store)
        rent_params, rent_captured = _params(
            {"category": "expense", "label": "Rent", "amount_rupees": 15_000, "certainty": "confirmed"}
        )
        await _record_fact(rent_params, session)
        gpt_params, gpt_captured = _params(
            {"category": "expense", "label": "GPT subscription", "amount_rupees": 2_000, "certainty": "confirmed"}
        )
        await _record_fact(gpt_params, session)
        gpt_id = gpt_captured["payload"]["fact"]["id"]

        session.last_user_utterance = "the rent was actually paid earlier on, by the 5th of this month"
        resolve_params, resolve_captured = _params({"fact_id": gpt_id, "resolved": True})
        await _record_fact(resolve_params, session)
        payload = resolve_captured["payload"]
        assert payload["status"] == "rejected"
        assert payload["error_code"] == "resolution_not_evidenced"
        assert store._facts[gpt_id]  # GPT subscription is still active

    asyncio.run(scenario())


def test_resolving_the_actually_named_fact_still_works():
    async def scenario():
        store = FakeFinanceStore()
        session = _session(store)
        rent_params, rent_captured = _params(
            {"category": "expense", "label": "Rent", "amount_rupees": 15_000, "certainty": "confirmed"}
        )
        await _record_fact(rent_params, session)
        rent_id = rent_captured["payload"]["fact"]["id"]

        session.last_user_utterance = "the rent was actually paid earlier on, by the 5th of this month"
        resolve_params, resolve_captured = _params({"fact_id": rent_id, "resolved": True})
        await _record_fact(resolve_params, session)
        payload = resolve_captured["payload"]
        assert payload["status"] == "success"
        assert rent_id not in store._facts  # resolved facts are removed by the fake store

    asyncio.run(scenario())


def test_income_overlap_blocks_the_exact_live_double_count_end_to_end():
    # The exact live failure through the real _record_fact code path: an
    # aggregate income range is already active; several unrelated facts get
    # recorded in between; the person then explains it comes from two
    # clients and names one client's specific payment. The candidate must
    # come back needs_reconciliation, not silently persist as new income.
    async def scenario():
        store = FakeFinanceStore()
        session = _session(store)

        range_params, _ = _params(
            {
                "category": "income",
                "label": "Freelance income range",
                "min_amount_rupees": 60_000,
                "max_amount_rupees": 75_000,
                "certainty": "estimated",
            }
        )
        await _record_fact(range_params, session)

        # Unrelated facts recorded in between, exactly as in the transcript.
        for args, utterance in [
            ({"category": "commitment", "label": "Credit card payment", "amount_rupees": 22_000, "recurring_day_of_month": 25, "certainty": "estimated"}, "the card is due on the 25th of every month"),
            ({"category": "expense", "label": "Rent", "amount_rupees": 15_000, "certainty": "confirmed"}, "my rent is fifteen thousand"),
            ({"category": "opening_cash", "label": "Savings balance", "amount_rupees": 18_000, "certainty": "confirmed"}, "I have eighteen thousand in savings"),
        ]:
            p, _ = _params(args)
            session.last_user_utterance = utterance
            session.recent_user_utterances.append(utterance)
            await _record_fact(p, session)

        session.recent_user_utterances.append(
            "I told you about my freelance income, there are two clients actually, one is reliable"
        )
        session.last_user_utterance = "yes, thirty five thousand, by the 22nd"
        session.recent_user_utterances.append(session.last_user_utterance)

        client_params, client_captured = _params(
            {
                "category": "income",
                "label": "Client payment expected",
                "amount_rupees": 35_000,
                "due_date": "2026-09-22",
                "certainty": "estimated",
            }
        )
        await _record_fact(client_params, session)
        payload = client_captured["payload"]
        assert payload["status"] == "needs_reconciliation"
        assert payload["existing_range_rupees"] == [60_000, 75_000]
        # Nothing new was persisted — only the original range fact exists.
        income_facts = [f for f in store._facts.values() if f["category"] == "income"]
        assert len(income_facts) == 1

    asyncio.run(scenario())


def test_snapshot_reports_real_committed_revision():
    async def scenario():
        store = FakeFinanceStore()
        session = _session(store)
        create_params, _ = _params(
            {"category": "opening_cash", "label": "Cash", "amount_rupees": 18_000, "certainty": "confirmed"}
        )
        await _record_fact(create_params, session)

        snapshot_params, captured = _params({})
        await _get_snapshot(snapshot_params, session)
        payload = captured["payload"]
        assert payload["status"] == "success"
        assert payload["revision"] == store.revision
        assert payload["workspace"]["opening_cash_rupees"] == 18_000

    asyncio.run(scenario())
