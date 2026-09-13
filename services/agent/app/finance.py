"""Persistent facts and deterministic, explainable 30-day cash projection."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import asyncpg
import dateparser
from loguru import logger
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

# A financial due date must never be a silent wrong guess. dateparser resolves far more
# phrasing than any hand-written whitelist ever will, but it can also confidently return
# a date in the wrong month for a genuinely ambiguous phrase (observed: "3rd week of the
# month" resolved to a date outside the current month entirely). Bounding the accepted
# window catches that failure mode the same way an unparseable phrase is caught — as a
# rejection the model turns into one clarifying question, not a number it treats as fact.
_MAX_PAST_DAYS = 45
_MAX_FUTURE_DAYS = 180

from app.models import MoneyFact, PlanEvent, PlanSummary, Workspace


class FactNotFoundError(ValueError):
    """A correction (fact_id given) named an id that isn't an active fact.

    Distinct from every other rejection: the person and the model both said
    something coherent, there is simply no such fact to patch (stale id, or a
    fact that was already resolved/deleted). This must reach the model as an
    explicit, nameable reason — never lumped in with a generic validation
    failure the model has to guess at.
    """


class FinancialFactInput(BaseModel):
    """A fact the model has heard clearly; amounts are always integer rupees here."""

    operation_id: UUID
    # Required only for a brand-new fact (enforced below, since a static schema
    # field can't be "required unless fact_id is given"). A correction that only
    # changes one unrelated detail (a recurring day, a restriction, marking paid)
    # never needs to restate what the fact already is.
    category: str | None = None
    label: str | None = Field(default=None, min_length=1, max_length=120)
    # Optional here only because a range (min+max) can stand in for it; the model
    # validator below always fills it with the range's midpoint when that happens, so
    # every consumer past construction can treat it as a real number.
    amount_rupees: int | None = Field(default=None, ge=0, le=100_000_000)
    min_amount_rupees: int | None = Field(default=None, ge=0, le=100_000_000)
    max_amount_rupees: int | None = Field(default=None, ge=0, le=100_000_000)
    # Only when part of amount_rupees cannot be used for this plan (a savings cap the
    # person set). Omit when the full amount is usable.
    usable_amount_rupees: int | None = Field(default=None, ge=0, le=100_000_000)
    # True only when the person said this money cannot be used for this plan at all.
    restricted: bool = False
    due_date: date | None = None
    # A calendar day (1-31) for money that repeats every month on the same day —
    # salary, rent, an EMI — rather than landing on one specific date. This exists
    # because dateparser has no concept of "the first of every month" at all: a
    # live call asked for a recurring salary date, every phrasing of it was
    # rejected as an unparseable due_date, and the person hung up mid-call after a
    # multi-turn loop demanding "a specific date... which year". A repeating
    # obligation is not a date parsing gap to patch, it is a different shape of
    # fact than due_date represents, so it gets its own field.
    recurring_day_of_month: int | None = Field(default=None, ge=1, le=31)
    # A short free-text nuance on top of a date or recurring day that isn't itself a
    # date — "may arrive as late as the 2nd", "sometimes a day early". Never parsed
    # or used in the calculation; purely something to show back to the person so
    # their own caveat isn't silently dropped. Deliberately just a string: a real
    # arrival-window model is a bigger feature than one call for this exists to fix.
    timing_note: str | None = Field(default=None, max_length=140)
    certainty: str = "confirmed"
    fact_id: UUID | None = None
    # True only when the person said this specific fact is now paid, settled, or no
    # longer applies. Retires it (excludes it from every future snapshot and
    # calculation) rather than deleting it, and requires fact_id: there is no such
    # thing as recording a brand-new fact that is already resolved — a "paid" status
    # is only ever a correction to something that already exists.
    resolved: bool = False

    @model_validator(mode="before")
    @classmethod
    def extract_recurring_from_due_date_text(cls, data: object) -> object:
        """Defense in depth for the exact failure that made a person hang up.

        The prompt now tells the model to use recurring_day_of_month directly for
        a repeating monthly obligation, but a live model can still fall back into
        habit and describe it through due_date instead ("the first of every
        month"). Catching that phrasing here — before it ever reaches the
        unparseable-date rejection — means a lapse in prompting degrades to the
        right behaviour instead of the tool_rejected loop this is fixing.
        """
        if not isinstance(data, dict):
            return data
        due = data.get("due_date")
        if not isinstance(due, str) or data.get("recurring_day_of_month") is not None:
            return data
        if not re.search(r"every month|each month|monthly", due, re.IGNORECASE):
            return data
        match = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\b", due)
        day = int(match.group(1)) if match else None
        if day is None:
            words = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5}
            for word, value in words.items():
                if word in due.lower():
                    day = value
                    break
        if day is None or not (1 <= day <= 31):
            return data
        return {**data, "recurring_day_of_month": day, "due_date": None}

    @field_validator("amount_rupees", "min_amount_rupees", "max_amount_rupees", "usable_amount_rupees", mode="before")
    @classmethod
    def normalize_amount(cls, value: object) -> object:
        if value is None or isinstance(value, int):
            return value
        if isinstance(value, str):
            cleaned = re.sub(r"[^0-9]", "", value)
            if cleaned:
                return int(cleaned)
        raise ValueError("amount must be a whole number of rupees")

    @model_validator(mode="after")
    def resolve_range_and_usable_cap(self) -> FinancialFactInput:
        if self.min_amount_rupees is not None or self.max_amount_rupees is not None:
            if self.min_amount_rupees is None or self.max_amount_rupees is None:
                raise ValueError("a range needs both min_amount_rupees and max_amount_rupees")
            if self.min_amount_rupees > self.max_amount_rupees:
                raise ValueError("min_amount_rupees must not exceed max_amount_rupees")
            if self.amount_rupees is None:
                self.amount_rupees = round((self.min_amount_rupees + self.max_amount_rupees) / 2)
        # Required for a brand-new fact — there is nothing to fall back to. Never
        # required when fact_id is given: a correction only changes what it
        # actually mentions, and the real bug this guards against is precisely a
        # correction ("add a recurring day to this expense") being rejected for
        # not resupplying an amount that was never changing in the first place.
        # _merge_patch fills the real amount in from the existing fact before this
        # validator ever runs a second time on the merged, complete object.
        if self.amount_rupees is None and self.fact_id is None:
            raise ValueError("a monetary value is required when creating a new financial fact")
        if self.category is None and self.fact_id is None:
            raise ValueError("category is required when creating a new financial fact")
        if not self.label and self.fact_id is None:
            raise ValueError("label is required when creating a new financial fact")
        if (
            self.usable_amount_rupees is not None
            and self.amount_rupees is not None
            and self.usable_amount_rupees > self.amount_rupees
        ):
            raise ValueError("usable_amount_rupees must not exceed amount_rupees")
        if self.resolved and not self.fact_id:
            raise ValueError("resolved requires fact_id: only an existing fact can be marked paid")
        return self

    @field_validator("due_date", mode="before")
    @classmethod
    def normalize_due_date(cls, value: object) -> object:
        if value is None or isinstance(value, date):
            return value
        if not isinstance(value, str):
            raise TypeError("date must be text")
        text = value.strip().lower()
        today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
        if text == "today":
            return today
        if text == "yesterday":
            return today - timedelta(days=1)
        if text == "tomorrow":
            return today + timedelta(days=1)
        if text in {"end of this month", "month end", "by month end"}:
            next_month = today.replace(day=28) + timedelta(days=4)
            return next_month - timedelta(days=next_month.day)
        if text in {"end of next month", "next month end"}:
            next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
            after_next = next_month.replace(day=28) + timedelta(days=4)
            return after_next - timedelta(days=after_next.day)
        for pattern in ("%B %d", "%b %d", "%d %B", "%d %b"):
            try:
                parsed = (
                    datetime.strptime(value.strip(), pattern)
                    .replace(tzinfo=ZoneInfo("Asia/Kolkata"))
                    .date()
                    .replace(year=today.year)
                )
                return parsed if parsed >= today else parsed.replace(year=today.year + 1)
            except ValueError:
                continue
        if re.match(r"^\d{4}-\d{2}-\d{2}$", value.strip()):
            return value  # Let pydantic's own ISO-date coercion handle this directly.
        parsed_dt = dateparser.parse(
            value,
            settings={
                "RELATIVE_BASE": datetime.combine(today, datetime.min.time()),
                "PREFER_DATES_FROM": "future",
            },
        )
        if parsed_dt is None:
            raise ValueError("date phrase could not be understood")
        parsed_date = parsed_dt.date()
        window_start = today - timedelta(days=_MAX_PAST_DAYS)
        window_end = today + timedelta(days=_MAX_FUTURE_DAYS)
        if not (window_start <= parsed_date <= window_end):
            raise ValueError("date phrase resolved outside a plausible window")
        return parsed_date

    @field_validator("fact_id", mode="before")
    @classmethod
    def normalize_empty_fact_id(cls, value: object) -> object:
        return None if isinstance(value, str) and value in {"", "null", "None"} else value

    @field_validator("category")
    @classmethod
    def valid_category(cls, value: str | None) -> str | None:
        if value is not None and value not in {"opening_cash", "income", "commitment", "expense"}:
            raise ValueError("unsupported category")
        return value

    @field_validator("certainty")
    @classmethod
    def valid_certainty(cls, value: str) -> str:
        value = {"certain": "confirmed", "likely": "estimated", "variable": "uncertain"}.get(
            value, value
        )
        if value not in {"confirmed", "estimated", "uncertain", "unknown"}:
            raise ValueError("unsupported certainty")
        return value


def _rupees(paise: int | None) -> int | None:
    return None if paise is None else paise // 100


def merge_patch(existing: dict, patch: FinancialFactInput) -> FinancialFactInput:
    """A correction (fact_id given) only changes what it actually mentions.

    The live bug this exists to fix: adding a recurring day to an existing ranged
    expense was rejected because the whole-object validator demanded an amount
    again, even though the amount was not changing. `patch.model_fields_set` is
    pydantic's own record of which fields the caller actually passed — as opposed
    to fields that simply took their default — so it is the correct signal for
    "the model is changing this" versus "the model didn't mention this, leave it
    alone." The result is re-validated as a complete object exactly like a new
    fact would be, so every cross-field invariant (range order, usable cap) still
    holds against the real, final values.
    """
    base = {
        "category": existing["category"],
        "label": existing["label"],
        "amount_rupees": _rupees(existing["amount_paise"]),
        "min_amount_rupees": _rupees(existing.get("min_amount_paise")),
        "max_amount_rupees": _rupees(existing.get("max_amount_paise")),
        "usable_amount_rupees": _rupees(existing.get("usable_amount_paise")),
        "restricted": existing.get("restricted", False),
        "due_date": existing.get("due_date"),
        "recurring_day_of_month": existing.get("recurring_day_of_month"),
        "timing_note": existing.get("timing_note"),
        "certainty": existing["certainty"],
    }
    fields_set = patch.model_fields_set
    for field in fields_set:
        if field in base:
            base[field] = getattr(patch, field)
    # A single new amount supersedes an old range rather than sitting alongside
    # it (a correction replaces what it corrects, per the same rule that already
    # applies to "paid" and to a due date turning into a recurring day) — and
    # conversely a new range must not be evaluated against the old point amount.
    if "amount_rupees" in fields_set and not ({"min_amount_rupees", "max_amount_rupees"} & fields_set):
        base["min_amount_rupees"] = None
        base["max_amount_rupees"] = None
    if ({"min_amount_rupees", "max_amount_rupees"} & fields_set) and "amount_rupees" not in fields_set:
        base["amount_rupees"] = None  # let the range recompute its own midpoint below
    # due_date and recurring_day_of_month describe the same concept two ways;
    # setting one must clear the other rather than leave a stale value from
    # whichever shape the fact used to be.
    if "recurring_day_of_month" in fields_set and patch.recurring_day_of_month is not None:
        base["due_date"] = None
    if "due_date" in fields_set and patch.due_date is not None:
        base["recurring_day_of_month"] = None
    return FinancialFactInput(
        operation_id=patch.operation_id, fact_id=patch.fact_id, resolved=patch.resolved, **base
    )


def fact_result(fact_id: object, persisted: FinancialFactInput, *, resolved: bool) -> dict:
    """The single-fact confirmation a mutation returns (item 26): what actually
    persisted, in the same shape the model already reads elsewhere, so it never
    has to guess or re-derive it from the whole workspace."""
    result: dict = {
        "id": str(fact_id),
        "category": persisted.category,
        "label": persisted.label,
        "amount_rupees": persisted.amount_rupees,
        "due_date": persisted.due_date.isoformat() if persisted.due_date else None,
        "certainty": persisted.certainty,
        "resolved": resolved,
    }
    if persisted.recurring_day_of_month is not None:
        result["recurring_day_of_month"] = persisted.recurring_day_of_month
    if persisted.timing_note:
        result["timing_note"] = persisted.timing_note
    if persisted.min_amount_rupees is not None:
        result["min_amount_rupees"] = persisted.min_amount_rupees
        result["max_amount_rupees"] = persisted.max_amount_rupees
    if persisted.usable_amount_rupees is not None:
        result["usable_amount_rupees"] = persisted.usable_amount_rupees
    if persisted.restricted:
        result["restricted"] = True
    return result


def shape_validation_errors(error: ValidationError | ValueError) -> list[dict]:
    """Turn a rejection into machine-readable detail the model can act on.

    The bug this fixes: a whole-model validator (no single field to blame) has
    an empty `loc`, and the previous mapping turned that into a bare `""` field
    name with the real message thrown away entirely — the model had no way to
    know a save failed because of a genuinely fixable, nameable reason. Every
    entry here always carries a real message; `field` is None only when the
    problem is not about any one field.
    """
    if isinstance(error, ValidationError):
        details = []
        for item in error.errors():
            field = ".".join(str(part) for part in item["loc"]) or None
            message = item["msg"]
            if message.startswith("Value error, "):
                message = message[len("Value error, ") :]
            details.append({"field": field, "message": message})
        return details
    return [{"field": None, "message": str(error)}]


SCHEMA = """
CREATE TABLE IF NOT EXISTS riverline_finance_workspaces (
  id uuid PRIMARY KEY,
  user_id text NOT NULL UNIQUE,
  revision integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS riverline_finance_operations (
  workspace_id uuid NOT NULL REFERENCES riverline_finance_workspaces(id) ON DELETE CASCADE,
  operation_id uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (workspace_id, operation_id)
);
CREATE TABLE IF NOT EXISTS riverline_finance_facts (
  id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES riverline_finance_workspaces(id) ON DELETE CASCADE,
  category text NOT NULL CHECK (category IN ('opening_cash', 'income', 'commitment', 'expense')),
  label text NOT NULL,
  amount_paise bigint NOT NULL CHECK (amount_paise >= 0),
  due_date date NULL,
  certainty text NOT NULL CHECK (certainty IN ('confirmed', 'estimated', 'uncertain', 'unknown')),
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
-- Added after the initial launch: a range, a partial-usability cap, and a hard
-- restriction flag. ALTER ... IF NOT EXISTS so this stays safe to run against a
-- database created before these columns existed.
ALTER TABLE riverline_finance_facts ADD COLUMN IF NOT EXISTS min_amount_paise bigint NULL;
ALTER TABLE riverline_finance_facts ADD COLUMN IF NOT EXISTS max_amount_paise bigint NULL;
ALTER TABLE riverline_finance_facts ADD COLUMN IF NOT EXISTS usable_amount_paise bigint NULL;
ALTER TABLE riverline_finance_facts ADD COLUMN IF NOT EXISTS restricted boolean NOT NULL DEFAULT false;
ALTER TABLE riverline_finance_facts ADD COLUMN IF NOT EXISTS recurring_day_of_month integer NULL;
ALTER TABLE riverline_finance_facts ADD COLUMN IF NOT EXISTS timing_note text NULL;
CREATE INDEX IF NOT EXISTS riverline_finance_facts_workspace_idx
  ON riverline_finance_facts(workspace_id, active, due_date);
CREATE TABLE IF NOT EXISTS riverline_conversations (
  id uuid PRIMARY KEY,
  user_id text NOT NULL,
  mode text NOT NULL CHECK (mode IN ('new', 'returning')),
  status text NOT NULL DEFAULT 'starting',
  started_at timestamptz NOT NULL DEFAULT now(),
  ended_at timestamptz NULL,
  failure_code text NULL
);
CREATE INDEX IF NOT EXISTS riverline_conversations_owner_idx
  ON riverline_conversations(user_id, started_at DESC);
CREATE TABLE IF NOT EXISTS riverline_conversation_events (
  id bigserial PRIMARY KEY,
  conversation_id uuid NOT NULL REFERENCES riverline_conversations(id) ON DELETE CASCADE,
  event_type text NOT NULL,
  role text NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
  content text NULL,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  elapsed_ms integer NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS riverline_conversation_events_conversation_idx
  ON riverline_conversation_events(conversation_id, id);
"""


class FinanceStore:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.pool: asyncpg.Pool | None = None

    async def open(self) -> None:
        self.pool = await asyncpg.create_pool(
            self.database_url, min_size=1, max_size=5, command_timeout=5
        )
        async with self.pool.acquire() as connection:
            await connection.execute(SCHEMA)
        logger.info("finance_store_ready")

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()
            self.pool = None

    def _pool(self) -> asyncpg.Pool:
        if not self.pool:
            raise RuntimeError("finance store is not ready")
        return self.pool

    async def _workspace_id(self, connection: asyncpg.Connection, user_id: str) -> UUID:
        row = await connection.fetchrow(
            """INSERT INTO riverline_finance_workspaces (id, user_id) VALUES ($1, $2)
               ON CONFLICT (user_id) DO UPDATE SET updated_at = riverline_finance_workspaces.updated_at
               RETURNING id""",
            uuid4(),
            user_id,
        )
        return row["id"]

    async def record(self, user_id: str, item: FinancialFactInput) -> tuple[Workspace, dict]:
        """Create a new fact, or PATCH an existing one when item.fact_id is given.

        A patch merges onto the existing row (merge_patch) rather than validating
        the incoming call as if it were a complete new object — the live bug this
        fixes was exactly that: correcting one detail (a recurring day) onto an
        existing fact was rejected for not resupplying its amount, which was never
        changing. Returns the refreshed workspace and a confirmation of the one
        fact that was actually written, so the caller never has to guess what
        persisted.
        """
        fact_id = item.fact_id
        persisted = item
        resolved = item.resolved
        async with self._pool().acquire() as connection, connection.transaction():
            workspace_id = await self._workspace_id(connection, user_id)
            inserted = await connection.fetchval(
                """INSERT INTO riverline_finance_operations (workspace_id, operation_id) VALUES ($1, $2)
                   ON CONFLICT DO NOTHING RETURNING operation_id""",
                workspace_id,
                item.operation_id,
            )
            if inserted:
                if item.fact_id:
                    existing = await connection.fetchrow(
                        """SELECT category, label, amount_paise, due_date, certainty,
                                  min_amount_paise, max_amount_paise, usable_amount_paise,
                                  restricted, recurring_day_of_month, timing_note
                           FROM riverline_finance_facts
                           WHERE id=$1 AND workspace_id=$2 AND active=true
                           FOR UPDATE""",
                        item.fact_id,
                        workspace_id,
                    )
                    if existing is None:
                        raise FactNotFoundError("no active financial fact exists with this id")
                    persisted = merge_patch(dict(existing), item)
                    min_paise = (
                        persisted.min_amount_rupees * 100
                        if persisted.min_amount_rupees is not None
                        else None
                    )
                    max_paise = (
                        persisted.max_amount_rupees * 100
                        if persisted.max_amount_rupees is not None
                        else None
                    )
                    usable_paise = (
                        persisted.usable_amount_rupees * 100
                        if persisted.usable_amount_rupees is not None
                        else None
                    )
                    await connection.execute(
                        """UPDATE riverline_finance_facts SET category=$3, label=$4, amount_paise=$5,
                           due_date=$6, certainty=$7, min_amount_paise=$8, max_amount_paise=$9,
                           usable_amount_paise=$10, restricted=$11, active=$12,
                           recurring_day_of_month=$13, timing_note=$14, updated_at=now()
                           WHERE id=$1 AND workspace_id=$2""",
                        item.fact_id,
                        workspace_id,
                        persisted.category,
                        persisted.label,
                        persisted.amount_rupees * 100,
                        persisted.due_date,
                        persisted.certainty,
                        min_paise,
                        max_paise,
                        usable_paise,
                        persisted.restricted,
                        not item.resolved,
                        persisted.recurring_day_of_month,
                        persisted.timing_note,
                    )
                else:
                    fact_id = uuid4()
                    min_paise = (
                        item.min_amount_rupees * 100 if item.min_amount_rupees is not None else None
                    )
                    max_paise = (
                        item.max_amount_rupees * 100 if item.max_amount_rupees is not None else None
                    )
                    usable_paise = (
                        item.usable_amount_rupees * 100
                        if item.usable_amount_rupees is not None
                        else None
                    )
                    await connection.execute(
                        """INSERT INTO riverline_finance_facts
                           (id, workspace_id, category, label, amount_paise, due_date, certainty,
                            min_amount_paise, max_amount_paise, usable_amount_paise, restricted,
                            recurring_day_of_month, timing_note)
                           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)""",
                        fact_id,
                        workspace_id,
                        item.category,
                        item.label,
                        item.amount_rupees * 100,
                        item.due_date,
                        item.certainty,
                        min_paise,
                        max_paise,
                        usable_paise,
                        item.restricted,
                        item.recurring_day_of_month,
                        item.timing_note,
                    )
                await connection.execute(
                    "UPDATE riverline_finance_workspaces SET revision=revision+1, updated_at=now() WHERE id=$1",
                    workspace_id,
                )
        logger.info("finance_fact_recorded category={} owner_present=true", item.category)
        workspace = await self.workspace(user_id)
        return workspace, fact_result(fact_id, persisted, resolved=resolved)

    async def workspace(self, user_id: str) -> Workspace:
        start = datetime.now(ZoneInfo("Asia/Kolkata")).date()
        end = start + timedelta(days=30)
        async with self._pool().acquire() as connection:
            workspace_id = await self._workspace_id(connection, user_id)
            workspace = await connection.fetchrow(
                "SELECT revision FROM riverline_finance_workspaces WHERE id=$1", workspace_id
            )
            rows = await connection.fetch(
                """SELECT id, category, label, amount_paise, due_date, certainty,
                          min_amount_paise, max_amount_paise, usable_amount_paise, restricted,
                          recurring_day_of_month, timing_note
                   FROM riverline_finance_facts WHERE workspace_id=$1 AND active=true ORDER BY created_at""",
                workspace_id,
            )
        facts = [
            {
                "id": str(row["id"]),
                "category": row["category"],
                "label": row["label"],
                "amount_paise": row["amount_paise"],
                "due_date": row["due_date"],
                "certainty": row["certainty"],
                "min_amount_paise": row["min_amount_paise"],
                "max_amount_paise": row["max_amount_paise"],
                "usable_amount_paise": row["usable_amount_paise"],
                "restricted": row["restricted"],
                "recurring_day_of_month": row["recurring_day_of_month"],
                "timing_note": row["timing_note"],
            }
            for row in rows
        ]
        return build_workspace(facts, int(workspace["revision"]), start, end)

    async def start_conversation(self, conversation_id: str, user_id: str, mode: str) -> None:
        await self._pool().execute(
            """INSERT INTO riverline_conversations (id, user_id, mode)
               VALUES ($1, $2, $3) ON CONFLICT (id) DO NOTHING""",
            UUID(conversation_id),
            user_id,
            mode,
        )

    async def record_conversation_event(
        self,
        conversation_id: str,
        event_type: str,
        *,
        role: str | None = None,
        content: str | None = None,
        elapsed_ms: int | None = None,
        metadata: dict | None = None,
    ) -> None:
        await self._pool().execute(
            """INSERT INTO riverline_conversation_events
               (conversation_id, event_type, role, content, elapsed_ms, metadata)
               VALUES ($1, $2, $3, $4, $5, $6::jsonb)""",
            UUID(conversation_id),
            event_type,
            role,
            content,
            elapsed_ms,
            json.dumps(metadata or {}),
        )

    async def finish_conversation(
        self, conversation_id: str, status: str, failure_code: str | None = None
    ) -> None:
        await self._pool().execute(
            """UPDATE riverline_conversations SET status=$2, ended_at=now(), failure_code=$3
               WHERE id=$1""",
            UUID(conversation_id),
            status,
            failure_code,
        )

    async def conversations(self, user_id: str) -> list[dict]:
        rows = await self._pool().fetch(
            """SELECT id, mode, status, started_at, ended_at, failure_code
               FROM riverline_conversations WHERE user_id=$1 ORDER BY started_at DESC LIMIT 30""",
            user_id,
        )
        return [dict(row) for row in rows]

    async def conversation(self, user_id: str, conversation_id: str) -> dict | None:
        row = await self._pool().fetchrow(
            """SELECT id, mode, status, started_at, ended_at, failure_code
               FROM riverline_conversations WHERE id=$1 AND user_id=$2""",
            UUID(conversation_id),
            user_id,
        )
        if not row:
            return None
        events = await self._pool().fetch(
            """SELECT id, event_type, role, content, occurred_at, elapsed_ms, metadata
               FROM riverline_conversation_events WHERE conversation_id=$1 ORDER BY id""",
            UUID(conversation_id),
        )
        result = dict(row)
        result["events"] = [dict(event) for event in events]
        return result


def _planning_amount(fact: MoneyFact, category: str) -> int:
    """The conservative figure to plan with for a fact given as a range.

    Income uses the low end so a variable-income person is never assumed to have
    more confirmed money than their worst realistic month. Commitments and expenses
    use the high end so a payment is never assumed to be smaller than it might be.
    A fact given as one exact number is unaffected.
    """
    if fact.min_amount_paise is not None and fact.max_amount_paise is not None:
        return fact.min_amount_paise if category == "income" else fact.max_amount_paise
    return fact.amount_paise or 0


def _month_day(year: int, month: int, day: int) -> date:
    """The given day in a month, clamped to that month's actual last day.

    A day_of_month of 31 recorded for salary must still land somewhere sensible
    in a 30-day February, rather than raising or silently skipping that month.
    """
    import calendar

    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def _recurring_occurrences(day_of_month: int, start: date, end: date) -> list[date]:
    """Every date within [start, end) this monthly cycle lands on.

    A fixed 30-day window against a ~30-31 day cycle can contain zero, one, or
    (only when the window starts right before the cycle's day) two occurrences —
    never assume exactly one. Three consecutive months is a safe bound: no 30-day
    window can span more than that.
    """
    occurrences = []
    year, month = start.year, start.month
    for _ in range(3):
        candidate = _month_day(year, month, day_of_month)
        if start <= candidate < end:
            occurrences.append(candidate)
        month += 1
        if month > 12:
            month, year = 1, year + 1
    return sorted(occurrences)


def build_workspace(facts: list[dict], revision: int, start: date, end: date) -> Workspace:
    grouped = {"income": [], "commitment": [], "expense": [], "opening_cash": []}
    for fact in facts:
        grouped[fact["category"]].append(
            # `if key in fact`: a present key (even with a None value, e.g. no range
            # given) passes through; a genuinely absent key (fact dicts built before
            # these fields existed) is left out entirely so MoneyFact's own default
            # applies, rather than raising a KeyError or passing an invalid None into
            # a non-Optional field like `restricted`.
            MoneyFact(**{key: fact[key] for key in MoneyFact.model_fields if key in fact})
        )
    # Restricted money (the person said it cannot be used for this plan) is tracked
    # and shown but never contributes to any calculation. A usable cap on otherwise
    # confirmed cash (protected savings) counts only up to that cap.
    usable_cash_facts = [f for f in grouped["opening_cash"] if not f.restricted]
    cash = sum(
        f.usable_amount_paise if f.usable_amount_paise is not None else (f.amount_paise or 0)
        for f in usable_cash_facts
    )
    opening = cash if grouped["opening_cash"] else None
    dated: list[tuple[date, int, str]] = []
    unplanned = 0
    uncertain_income = 0
    uncertain_outgoings = 0
    for category in ("income", "commitment", "expense"):
        for fact in grouped[category]:
            if fact.restricted:
                continue
            amount = _planning_amount(fact, category)
            if fact.certainty == "uncertain":
                # Categorically different from "unplanned": this is known to be
                # unconfirmed, not merely missing a date. Never enters the confirmed
                # path; shown separately so the model can describe what changes if
                # it arrives, without promoting it to a fact.
                if category == "income":
                    uncertain_income += amount
                else:
                    uncertain_outgoings += amount
                continue
            sign = 1 if category == "income" else -1
            if fact.recurring_day_of_month:
                occurrences = _recurring_occurrences(fact.recurring_day_of_month, start, end)
                if not occurrences:
                    # The cycle's day genuinely doesn't fall inside this specific
                    # 30-day window (possible near a month boundary) — tracked,
                    # not silently dropped, same as any other fact with no dated
                    # occurrence in range.
                    unplanned += 1
                    continue
                for occurrence in occurrences:
                    dated.append((occurrence, sign * amount, fact.label))
                continue
            if not fact.due_date:
                unplanned += 1
                continue
            if not start <= fact.due_date < end:
                continue
            dated.append((fact.due_date, sign * amount, fact.label))
    dated.sort(key=lambda event: (event[0], event[1]))
    timeline: list[PlanEvent] = []
    lowest = cash if opening is not None else None
    shortfall = None
    income_total = 0
    outgoing_total = 0
    for when, change, label in dated:
        cash += change
        if change > 0:
            income_total += change
        else:
            outgoing_total += -change
        if lowest is None or cash < lowest:
            lowest = cash
        if cash < 0 and shortfall is None:
            shortfall = when
        timeline.append(PlanEvent(date=when, label=label, change_paise=change, balance_paise=cash))
    conditional_closing = (
        cash + uncertain_income - uncertain_outgoings if opening is not None else None
    )
    fact_count = sum(len(values) for values in grouped.values())
    return Workspace(
        revision=revision,
        window_start=start,
        window_end_exclusive=end,
        opening_cash_paise=opening,
        opening_cash=grouped["opening_cash"],
        income=grouped["income"],
        commitments=grouped["commitment"],
        expenses=grouped["expense"],
        plan_status="not_started"
        if not fact_count
        else ("ready" if dated and opening is not None else "building"),
        summary=PlanSummary(
            dated_income_paise=income_total,
            dated_outgoings_paise=outgoing_total,
            projected_closing_paise=cash if opening is not None else None,
            lowest_balance_paise=lowest,
            first_shortfall_date=shortfall,
            unplanned_fact_count=unplanned,
            uncertain_income_paise=uncertain_income,
            uncertain_outgoings_paise=uncertain_outgoings,
            conditional_closing_paise=conditional_closing,
        ),
        timeline=timeline,
    )


def _fact_dict(fact: MoneyFact) -> dict:
    result = {
        "id": fact.id,
        "label": fact.label,
        "amount_rupees": _rupees(fact.amount_paise),
        "due_date": fact.due_date.isoformat() if fact.due_date else None,
        "certainty": fact.certainty,
    }
    if fact.min_amount_paise is not None:
        result["min_amount_rupees"] = _rupees(fact.min_amount_paise)
        result["max_amount_rupees"] = _rupees(fact.max_amount_paise)
    if fact.usable_amount_paise is not None:
        result["usable_amount_rupees"] = _rupees(fact.usable_amount_paise)
    if fact.restricted:
        result["restricted"] = True
    if fact.recurring_day_of_month is not None:
        result["recurring_day_of_month"] = fact.recurring_day_of_month
    if fact.timing_note:
        result["timing_note"] = fact.timing_note
    return result


def tool_snapshot(snapshot: Workspace) -> dict:
    """Shape a Workspace for a voice tool result: every amount in whole rupees.

    A prior shape exposed raw *_paise integers (and only fact counts, not amounts)
    directly to the model. It read a paise value as if it were rupees and spoke a
    closing balance 100x too large, and separately had no way to recheck an amount
    it had already stated because the actual figures were never in the snapshot.
    This has nothing to do with any particular voice engine, so it lives here next
    to the calculation it shapes rather than in a pipecat-importing pipeline module.
    """
    summary = snapshot.summary
    return {
        "revision": snapshot.revision,
        "plan_status": snapshot.plan_status,
        "opening_cash_rupees": _rupees(snapshot.opening_cash_paise),
        "opening_cash": [_fact_dict(fact) for fact in snapshot.opening_cash],
        "income": [_fact_dict(fact) for fact in snapshot.income],
        "commitments": [_fact_dict(fact) for fact in snapshot.commitments],
        "expenses": [_fact_dict(fact) for fact in snapshot.expenses],
        "summary": {
            "dated_income_rupees": _rupees(summary.dated_income_paise),
            "dated_outgoings_rupees": _rupees(summary.dated_outgoings_paise),
            "projected_closing_rupees": _rupees(summary.projected_closing_paise),
            "lowest_balance_rupees": _rupees(summary.lowest_balance_paise),
            "first_shortfall_date": (
                summary.first_shortfall_date.isoformat() if summary.first_shortfall_date else None
            ),
            "unplanned_fact_count": summary.unplanned_fact_count,
            # Never part of the confirmed numbers above. Only for describing what
            # changes if uncertain money arrives — e.g. "the shortfall could be
            # lower if the client payment comes in time" — not for stating it as
            # confirmed or promoting it into the plan on your own.
            "uncertain_income_rupees": _rupees(summary.uncertain_income_paise),
            "uncertain_outgoings_rupees": _rupees(summary.uncertain_outgoings_paise),
            "conditional_closing_rupees_if_uncertain_money_arrives": _rupees(
                summary.conditional_closing_paise
            ),
        },
        "timeline": [
            {
                "date": event.date.isoformat(),
                "label": event.label,
                "change_rupees": _rupees(event.change_paise),
                "balance_rupees": _rupees(event.balance_paise),
            }
            for event in snapshot.timeline
        ],
    }


def format_existing_facts(shaped: dict) -> str:
    """Render a tool_snapshot() dict as a system-prompt-ready block of saved facts.

    A returning conversation used to just tell the model "existing facts remain
    their context" and hope it called get_financial_snapshot on its own — verified
    live, it did not, and told the person it "can't see earlier chats" even though
    the data existed. This is the pure formatting half of the actual fix (the
    other half fetches the snapshot and lives in app.voice.pipeline, since only
    that side needs a live session); kept here, with no pipecat import, so it can
    be tested without paying that module's import cost.
    """
    facts = shaped["opening_cash"] + shaped["income"] + shaped["commitments"] + shaped["expenses"]
    if not facts:
        return ""
    lines = []
    for fact in facts:
        if fact.get("recurring_day_of_month"):
            due = f", recurring on day {fact['recurring_day_of_month']} of every month"
        elif fact.get("due_date"):
            due = f", due {fact['due_date']}"
        else:
            due = ""
        cap = (
            f", usable up to {fact['usable_amount_rupees']} rupees"
            if fact.get("usable_amount_rupees") is not None
            else ""
        )
        restricted = ", restricted (not usable for this plan)" if fact.get("restricted") else ""
        note = f", note: {fact['timing_note']}" if fact.get("timing_note") else ""
        lines.append(f"- {fact['label']}: {fact['amount_rupees']} rupees ({fact['certainty']}{due}{cap}{restricted}{note})")
    return (
        "\n\nAlready saved from earlier conversations — this is your memory, already true, not\n"
        "something to re-ask or re-confirm from scratch:\n" + "\n".join(lines)
    )
