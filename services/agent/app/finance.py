"""Persistent facts and deterministic, explainable 30-day cash projection."""

from __future__ import annotations

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
