"""Move conversations, their events, and financial facts into archive tables.

This clears stale test data out of the live tables the voice agent actually reads
from (so a fresh conversation isn't confused by a dozen near-duplicate facts from
past manual test calls) while keeping every row for later review. It never touches
`riverline_finance_workspaces` (the per-user identity/revision row) or deletes any
user account — only conversations, conversation events, and financial facts move.

Usage (from the repo root, with the stack running):
    docker compose exec agent .venv/bin/python scripts/archive_conversations.py
    docker compose exec agent .venv/bin/python scripts/archive_conversations.py --user <user_id>

With no --user, archives every user's data. Pass --user to scope to one person
(find the id with: SELECT DISTINCT user_id FROM riverline_conversations;).
"""

import argparse
import asyncio
import sys
from pathlib import Path

import asyncpg

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from app.config import get_settings

# Deliberately plain column copies with no foreign keys or unique constraints of
# their own — not `LIKE ... INCLUDING ALL`. That would also copy each source
# table's `ON DELETE CASCADE` foreign key, pointed at the *live* parent table.
# Since this script deletes those live parent rows in the same transaction it
# archives them, an inherited cascade constraint would delete the archive copy
# right along with it — silently destroying the very data being archived.
ARCHIVE_SCHEMA = """
CREATE TABLE IF NOT EXISTS riverline_conversations_archive (
  id uuid NOT NULL,
  user_id text NOT NULL,
  mode text NOT NULL,
  status text NOT NULL,
  started_at timestamptz NOT NULL,
  ended_at timestamptz NULL,
  failure_code text NULL,
  archived_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS riverline_conversation_events_archive (
  id bigint NOT NULL,
  conversation_id uuid NOT NULL,
  event_type text NOT NULL,
  role text NULL,
  content text NULL,
  occurred_at timestamptz NOT NULL,
  elapsed_ms integer NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  archived_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS riverline_finance_facts_archive (
  id uuid NOT NULL,
  workspace_id uuid NOT NULL,
  category text NOT NULL,
  label text NOT NULL,
  amount_paise bigint NOT NULL,
  due_date date NULL,
  certainty text NOT NULL,
  active boolean NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  archived_at timestamptz NOT NULL DEFAULT now()
);
"""


async def archive(user_id: str | None) -> None:
    settings = get_settings()
    connection = await asyncpg.connect(settings.database_url)
    try:
        async with connection.transaction():
            await connection.execute(ARCHIVE_SCHEMA)

            events_moved = await connection.fetchval(
                """WITH moved AS (
                     DELETE FROM riverline_conversation_events e USING riverline_conversations c
                     WHERE e.conversation_id = c.id AND ($1::text IS NULL OR c.user_id = $1)
                     RETURNING e.*
                   ), inserted AS (
                     INSERT INTO riverline_conversation_events_archive
                       (id, conversation_id, event_type, role, content, occurred_at, elapsed_ms, metadata)
                     SELECT id, conversation_id, event_type, role, content, occurred_at, elapsed_ms, metadata
                     FROM moved RETURNING 1
                   )
                   SELECT count(*) FROM inserted""",
                user_id,
            )
            conversations_moved = await connection.fetchval(
                """WITH moved AS (
                     DELETE FROM riverline_conversations
                     WHERE $1::text IS NULL OR user_id = $1
                     RETURNING *
                   ), inserted AS (
                     INSERT INTO riverline_conversations_archive
                       (id, user_id, mode, status, started_at, ended_at, failure_code)
                     SELECT id, user_id, mode, status, started_at, ended_at, failure_code
                     FROM moved RETURNING 1
                   )
                   SELECT count(*) FROM inserted""",
                user_id,
            )
            facts_moved = await connection.fetchval(
                """WITH moved AS (
                     DELETE FROM riverline_finance_facts f USING riverline_finance_workspaces w
                     WHERE f.workspace_id = w.id AND ($1::text IS NULL OR w.user_id = $1)
                     RETURNING f.*
                   ), inserted AS (
                     INSERT INTO riverline_finance_facts_archive
                       (id, workspace_id, category, label, amount_paise, due_date, certainty,
                        active, created_at, updated_at)
                     SELECT id, workspace_id, category, label, amount_paise, due_date, certainty,
                            active, created_at, updated_at
                     FROM moved RETURNING 1
                   )
                   SELECT count(*) FROM inserted""",
                user_id,
            )
        scope = f"user {user_id}" if user_id else "all users"
        print(
            f"Archived for {scope}: {conversations_moved} conversations, "
            f"{events_moved} conversation events, {facts_moved} financial facts."
        )
    finally:
        await connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", default=None, help="Scope to one user_id. Omit to archive all users.")
    args = parser.parse_args()
    asyncio.run(archive(args.user))
