"""Persistent facts and deterministic, explainable 30-day cash projection."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import asyncpg
from loguru import logger
from pydantic import BaseModel, Field, field_validator

from app.models import MoneyFact, PlanEvent, PlanSummary, Workspace


class FinancialFactInput(BaseModel):
    """A fact the model has heard clearly; amounts are always integer rupees here."""

    operation_id: UUID
    category: str
    label: str = Field(min_length=1, max_length=120)
    amount_rupees: int = Field(ge=0, le=100_000_000)
    due_date: date | None = None
    certainty: str = "confirmed"
    fact_id: UUID | None = None

    @field_validator("amount_rupees", mode="before")
    @classmethod
    def normalize_amount(cls, value: object) -> int:
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            cleaned = re.sub(r"[^0-9]", "", value)
            if cleaned:
                return int(cleaned)
        raise ValueError("amount must be a whole number of rupees")

    @field_validator("category")
    @classmethod
    def valid_category(cls, value: str) -> str:
        if value not in {"opening_cash", "income", "commitment", "expense"}:
            raise ValueError("unsupported category")
        return value

    @field_validator("certainty")
    @classmethod
    def valid_certainty(cls, value: str) -> str:
        value = {"certain": "confirmed", "likely": "estimated", "variable": "uncertain"}.get(value, value)
        if value not in {"confirmed", "estimated", "uncertain", "unknown"}:
            raise ValueError("unsupported certainty")
        return value


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

    async def record(self, user_id: str, item: FinancialFactInput) -> Workspace:
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
                    changed = await connection.execute(
                        """UPDATE riverline_finance_facts SET category=$3, label=$4, amount_paise=$5,
                           due_date=$6, certainty=$7, updated_at=now() WHERE id=$1 AND workspace_id=$2 AND active=true""",
                        item.fact_id,
                        workspace_id,
                        item.category,
                        item.label,
                        item.amount_rupees * 100,
                        item.due_date,
                        item.certainty,
                    )
                    if changed == "UPDATE 0":
                        raise ValueError("fact to correct was not found")
                else:
                    await connection.execute(
                        """INSERT INTO riverline_finance_facts
                           (id, workspace_id, category, label, amount_paise, due_date, certainty)
                           VALUES ($1,$2,$3,$4,$5,$6,$7)""",
                        uuid4(),
                        workspace_id,
                        item.category,
                        item.label,
                        item.amount_rupees * 100,
                        item.due_date,
                        item.certainty,
                    )
                await connection.execute(
                    "UPDATE riverline_finance_workspaces SET revision=revision+1, updated_at=now() WHERE id=$1",
                    workspace_id,
                )
        logger.info("finance_fact_recorded category={} owner_present=true", item.category)
        return await self.workspace(user_id)

    async def workspace(self, user_id: str) -> Workspace:
        start = datetime.now(ZoneInfo("Asia/Kolkata")).date()
        end = start + timedelta(days=30)
        async with self._pool().acquire() as connection:
            workspace_id = await self._workspace_id(connection, user_id)
            workspace = await connection.fetchrow(
                "SELECT revision FROM riverline_finance_workspaces WHERE id=$1", workspace_id
            )
            rows = await connection.fetch(
                """SELECT id, category, label, amount_paise, due_date, certainty
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
            }
            for row in rows
        ]
        return build_workspace(facts, int(workspace["revision"]), start, end)

    async def start_conversation(self, conversation_id: str, user_id: str, mode: str) -> None:
        await self._pool().execute(
            """INSERT INTO riverline_conversations (id, user_id, mode)
               VALUES ($1, $2, $3) ON CONFLICT (id) DO NOTHING""",
            UUID(conversation_id), user_id, mode,
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
            UUID(conversation_id), event_type, role, content, elapsed_ms,
            json.dumps(metadata or {}),
        )

    async def finish_conversation(self, conversation_id: str, status: str, failure_code: str | None = None) -> None:
        await self._pool().execute(
            """UPDATE riverline_conversations SET status=$2, ended_at=now(), failure_code=$3
               WHERE id=$1""",
            UUID(conversation_id), status, failure_code,
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
            UUID(conversation_id), user_id,
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


def build_workspace(facts: list[dict], revision: int, start: date, end: date) -> Workspace:
    grouped = {"income": [], "commitment": [], "expense": [], "opening_cash": []}
    for fact in facts:
        grouped[fact["category"]].append(
            MoneyFact(**{key: fact[key] for key in MoneyFact.model_fields})
        )
    cash = sum(f.amount_paise or 0 for f in grouped["opening_cash"])
    opening = cash if grouped["opening_cash"] else None
    dated: list[tuple[date, int, str]] = []
    unplanned = 0
    for category in ("income", "commitment", "expense"):
        for fact in grouped[category]:
            if not fact.due_date:
                unplanned += 1
                continue
            if not start <= fact.due_date < end or fact.certainty == "uncertain":
                continue
            sign = 1 if category == "income" else -1
            dated.append((fact.due_date, sign * (fact.amount_paise or 0), fact.label))
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
    fact_count = sum(len(values) for values in grouped.values())
    return Workspace(
        revision=revision,
        window_start=start,
        window_end_exclusive=end,
        opening_cash_paise=opening,
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
        ),
        timeline=timeline,
    )
