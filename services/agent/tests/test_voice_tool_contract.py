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


def _session(store):
    return SimpleNamespace(
        id="session-1", owner="owner-1", finance_store=store, created_monotonic=time.monotonic()
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
