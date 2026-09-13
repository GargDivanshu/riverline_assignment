# Riverline

A real-time English-only voice assistant that has a natural conversation
about a person's money and produces a deterministic, explainable 30-day cash
plan — built for the Riverline AI Engineer hiring assignment
([engineering-assignment.md](engineering-assignment.md)).

## Quick start

Requires Docker Desktop (or another Docker engine) with Linux containers.

```bash
cp .env.example .env
# then edit .env and fill in your own API keys — see "Environment variables" below
docker compose up --build
```

Open **http://localhost:3000**, sign up with an email/password (12+
characters), and start a call.

That's the whole setup — one file to edit, one command to run. No separate
terminals for the database, the Python agent, or the web app; Compose starts
and orders all three.

## Environment variables

Copy [.env.example](.env.example) to `.env` and fill it in — every variable
is commented there too. Nothing in `.env` is committed (see `.gitignore`).

| Variable | Required | Purpose | How to get it |
|---|---|---|---|
| `APP_ORIGIN`, `BETTER_AUTH_URL` | Yes | Browser origin / auth base URL | Leave as `http://localhost:3000` for local use |
| `DATABASE_URL` | Yes | Postgres connection string | Provided; Compose overrides the host to `db` internally |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Yes | Local Postgres credentials | Local-only defaults provided; change if you like, they're not real secrets |
| `BETTER_AUTH_SECRET` | Yes | Signs auth session tokens | Generate with `npm run setup` (writes into `.env`, never printed), or any random 32+ char string (e.g. `openssl rand -hex 32`) |
| `INTERNAL_API_SECRET` | Yes | Shared secret between the web app and the Python agent | Same as above, minimum 32 characters |
| `AGENT_API_URL` | Yes | Where the web app reaches the Python agent | Provided; Compose overrides it to `http://agent:8000` internally |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | No | Enables Google sign-in (both must be set together) | [Google Cloud Console](https://console.cloud.google.com/) OAuth client; register `http://localhost:3000/api/auth/callback/google` as a redirect URI |
| `DAILY_API_KEY` | **Yes, for voice** | Creates the private, short-lived Daily room and tokens for each call | [Daily dashboard](https://dashboard.daily.co/) API key |
| `VOICE_ENGINE` | Yes | `realtime` (OpenAI speech-to-speech) or `cascade` (STT → LLM → TTS). Both share every tool, prompt, and finance rule — this is the only switch | Leave as `realtime` unless you want to compare the cascade path |
| `OPENAI_API_KEY`, `REALTIME_MODEL`, `REALTIME_VOICE` | **Yes when `VOICE_ENGINE=realtime`** | The realtime speech-to-speech model and voice | [OpenAI dashboard](https://platform.openai.com/api-keys) |
| `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `STT_MODEL`, `TTS_MODEL` | **Yes when `VOICE_ENGINE=cascade`** | Streaming speech recognition and speech synthesis | [ElevenLabs dashboard](https://elevenlabs.io/app/settings/api-keys) |
| `OPENROUTER_API_KEY`, `VOICE_MODEL` | **Yes when `VOICE_ENGINE=cascade`** | The conversational model for the cascade path | [OpenRouter dashboard](https://openrouter.ai/keys) |
| `VOICE_MAX_SESSIONS`, `VOICE_MAX_SECONDS` | No | Local concurrency cap and max call length | Defaults provided (2 sessions, 15 minutes) |
| `SARVAM_API_KEY` | No | Reserved for a possible alternative STT/TTS provider, not wired into either engine today | Not needed |

Only `DAILY_API_KEY` plus either the OpenAI key (realtime) or the
ElevenLabs+OpenRouter keys (cascade) cost anything or need a real account —
everything else is either a local placeholder or optional.

## What this is

The person talks; the model asks about their income, payments, and
expenses; every clear fact gets persisted through a small set of backend
tools; a deterministic engine turns those facts into a 30-day cash
projection; the UI shows live cards driven by that same projection. The
model never does arithmetic itself and never invents a number, date, or
outcome it wasn't actually given.

```
Browser (Next.js, tRPC) ⇄ Daily (WebRTC audio) ⇄ Pipecat pipeline
                                                        │
                                          record_financial_fact /
                                          get_financial_snapshot
                                                        │
                                        services/agent/app/finance.py
                                     (validation, grounding, patch/merge,
                                        deterministic 30-day projection)
                                                        │
                                                   Postgres
```

- **`apps/web`** — Next.js app, Better Auth, tRPC, the workspace UI (cards)
  and the voice call UI (`live-conversation.tsx`, `voice-orb.tsx`).
- **`services/agent`** — FastAPI + Pipecat. `voice/pipeline.py` is the
  cascade engine (ElevenLabs STT → OpenRouter LLM → ElevenLabs TTS);
  `voice/realtime_pipeline.py` is the OpenAI Realtime speech-to-speech
  engine. They share the same tools, system prompt, and finance layer —
  `VOICE_ENGINE` in `.env` is the only thing that decides which one runs.
  `finance.py` is the deterministic core: fact validation, correction/patch
  semantics, the 30-day projection, and every guardrail below.

## What the assistant actually guarantees

These aren't just prompt instructions — each one is a real bug found on a
live call, root-caused against the actual transcript and database state,
and fixed with a deterministic check plus a permanent regression test (not
just a prompt tweak, because a prompt-only version of more than one of these
was tried first and didn't hold under a real conversation):

- **A spoken amount can't be silently corrupted.** Before a new single
  amount is saved, it's checked against what was actually said (a
  deterministic Indian-numbering reader — "eighteen thousand" → 18000, "one
  lakh twenty five thousand" → 125000 — not a guess).
- **A date can't be invented.** A due date or recurring day only saves if
  something in the conversation actually supports a date at all; an
  aggregate money question with no date mentioned can't quietly acquire one.
- **Correcting one detail never means resupplying the whole fact.** A
  correction merges onto the existing fact — add a recurring day to a
  ranged expense and the range stays exactly as it was.
- **Resolving one obligation can't resolve others.** Marking something paid
  requires that the specific thing was actually named; it's also rejected
  if the wording could equally mean a different still-active obligation.
- **An aggregate and one of its components can't double-count.** If an
  income range is already saved and a later, same-source payment could
  plausibly be part of it, the system either recognizes that automatically
  or asks one direct clarifying question — it never silently adds both.
- **The assistant can't claim a save succeeded, failed, or is "still
  processing" without a tool result that actually says so.** Silence or
  latency is never narrated as a technical explanation.
- **Every tool call is fully traceable.** Each one is logged before and
  after, with its real arguments and the workspace revision before/after —
  never just a bare "it worked."

## Testing

```bash
uv run --project services/agent pytest services/agent/tests
```

90 tests, all passing, in `services/agent/tests/`:

| File | Covers |
|---|---|
| `test_finance.py` | The 30-day projection itself — chronological running balance, confirmed-vs-uncertain money, restricted/protected cash, both assignment demo scenarios (a variable-income kirana-style shortfall and a salaried pre-salary shortfall hidden by a later positive balance) |
| `test_finance_input.py` | Fact validation — ranges, usable caps, restrictions, recurring dates, resolved corrections |
| `test_finance_patch.py` | True patch semantics — a correction preserves everything it doesn't mention |
| `test_finance_grounding.py` | The amount/date/resolution-targeting guards, and the number-word extractor directly |
| `test_income_overlap.py` | The aggregate-vs-component income guard — additive, component, ambiguous, and distant-conversation cases |
| `test_voice_tool_contract.py` | The tool layer end to end (via an in-memory store built on the real merge/validation functions) — success, rejection, and reconciliation all produce the exact contract the model receives |
| `test_voice.py`, `test_api.py` | Session lifecycle, capacity limits, and provider-error classification |

There's also `apps/web/tests/` and `tests/e2e/` — pre-existing auth-flow
tests from early scaffolding, unrelated to the voice/finance work above.

No LLM-based semantic evaluation harness was built. Whether the model's own
*reasoning* about ambiguity or truthfulness holds in a live call is
something a controlled voice rehearsal has to verify — that's a stated
limitation, not glossed over (see below).

## Optional depth track: A (conversational intelligence)

Chosen and built through repeated live-call → transcript/DB root-cause →
fix → regression-test cycles rather than upfront design — every fix above
under "what the assistant actually guarantees" came from a real transcript,
each one saved and the exact failure quoted before being fixed.

## What works

- A full conversation — onboarding or returning — that asks one thing at a
  time, remembers what's already been said, and explains a 30-day plan
  including confirmed-vs-uncertain money and the first shortfall date.
- Corrections and "already paid" updates that target the right fact and
  leave everything else untouched.
- Recurring monthly obligations ("the 25th of every month") without ever
  asking which month or year.
- Cards that stay in sync with the same numbers the assistant is speaking
  from, because both read the same committed backend state.

## What does not work / known limitations

- OpenAI Realtime rate-limit failures under a burst of near-simultaneous
  tool calls aren't solved, only indirectly reduced. No call batching or
  serialization was built — that would have meant a bigger architectural
  change than any single pass here was scoped for.
- No graceful spoken goodbye when a call dies from exhausted provider
  retries — the realtime engine has no way to force one more spoken turn
  independent of the model's own generation.
- Duplicate-fact prevention beyond an 8-second creation window is
  prompt-level, not structurally enforced.
- Resolution-ambiguity and income-overlap detection are keyword-based
  heuristics, verified against the concrete cases that actually occurred
  live — not exhaustively fuzzed against arbitrary phrasing.
- "Confirm the user understands the plan" is handled by asking what they
  want next rather than an explicit comprehension check.

## What I would build next

- A small semantic/LLM-graded eval harness (Track B) over recorded
  transcripts, so a conversational regression can be caught without a live
  call every time.
- Extend the grounding/overlap checks' phrase lists from more real calls
  rather than guessing additional cases in advance.
- A batched or rate-aware tool-call path for the realtime engine, to reduce
  the provider-limit failures under a burst of facts in one turn.

## Where AI helped

Nearly everything in this repository was built with AI assistance,
consistent with the assignment's own framing — the code, the pipeline
plumbing, the test suite, and this README. Its actual value here was in the
debugging loop: pulling and reading real conversation transcripts and
database state after each test call, root-causing a specific failure
against that evidence, and turning it into a deterministic fix plus a
regression test that encodes the original failing transcript.

## Where AI produced incorrect or poor work

- An early attempt at "never double-count income" was prompt-only and
  looked reasonable, but didn't hold once the aggregate and the specific
  payment were mentioned many turns apart in a real call — it needed a
  deterministic backend check instead, not more prompt text.
- Turn-detection and OpenAI Realtime integration went through more than one
  wrong assumption before landing (frame direction, aggregator start
  behavior) — each one confirmed by reading the library source directly
  rather than guessing, after the first guess was wrong.
- Several early "it's fixed" claims turned out to be true only in isolated
  testing and not in a full live call; the working discipline that emerged
  was to verify every fix against a live container and a real transcript,
  not just a passing unit test, before calling it done.

## Decision journal

[decision_journal.md](decision_journal.md) — written independently by me, in accordance with the assignment's journal rules.

## Demo video

[Watch the demo](https://drive.google.com/file/d/15jjaLHt04jDqdTDm_0eWwEkQTZ1sd5px/view?usp=drive_link)

Not committed to this repository — `.Tmp/` (where working recordings were
kept during development) is git-ignored, and the reference product video is
excluded from git by filename in `.gitignore`.

## Verification results

The command above (`uv run pytest services/agent/tests`) is the full
automated verification: 90/90 passing at the time of this submission. Every
fix listed under "what the assistant actually guarantees" was additionally
verified live — rebuilt into the running `agent` container and re-run
against the actual Postgres instance — not just covered by a unit test, per
the working discipline noted above.
