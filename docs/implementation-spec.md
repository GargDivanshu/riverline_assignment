# Implementation spec: 30-day voice finance planner

Status: target design. The authentication/workspace foundation is implemented; see [architecture](architecture.md) for actual status and account-based authentication superseding the original anonymous-session proposal. Voice and financial behavior remain unimplemented and unbenchmarked. Grounded in `engineering-assignment.md`. This is a technical specification, not journal content. Research checked on 2026-09-10; see [integration research](integration-research.md).

Current scope: local Docker Compose delivery and Track A conversational intelligence. See [conversation architecture](conversation-architecture.md) for the current provider comparison and intent-first interaction proposal. Hosted databases are out of scope.

## 1. Product outcome and scope

Help an individual answer: **What can I pay over the next 30 days, on which dates, what remains uncovered, and what changes if uncertain money arrives?**

The main product value is a dated plan that remains consistent as the person corrects or adds information. A monthly surplus alone is insufficient: an EMI can fall due before salary arrives.

### First complete journey

An individual with salary plus variable earnings explains available cash, upcoming income, essential expenses, and debts. The agent discovers a correction and an uncertain receivable, identifies an early cash shortage, and produces a dated plan with visible calculations. The user can protect spending categories and decline proposed adjustments. The agent explains unresolved gaps and checks understanding.

Support salaried people, freelancers, gig workers and household planning by a sole proprietor through the same underlying cash-flow model. Do not require a job-category selection or a fixed questionnaire.

### Included in the first build

- English-only live voice through Pipecat and Daily; start, interrupt, end and review.
- Known cash, dated inflows/outflows, amount ranges, uncertain receipt, corrections and missing information.
- Bank/NBFC debt, credit-card bills, BNPL instalments, and money owed to friends/family.
- A conservative projection, clearly conditional alternatives, and payment-date shortfalls.
- Live cards, a final plan, user-approved expense adjustments and visible calculation inputs.
- Persistent session state, meaningful tests/evaluations, and one-command Docker startup.

### Future product opportunities, outside this submission's first build

Credit-report import and AA connections, long-term debt payoff, enterprise treasury, joint ownership/guarantees, multiple currencies, investment aggregation, and lender integrations.

New-loan discovery, recommendations, eligibility predictions and approval promises are outside the assignment. A request for an education or expansion loan can reveal the user's motivation, but this application must keep its assistance within current 30-day cash planning. A goal two months away may be acknowledged as outside the horizon; do not claim the plan finances it.

## 2. User control and useful questions

Ask for information when it changes a calculation, timing risk, uncertainty, or a choice the user needs to make. Avoid profiling by city, occupation or lifestyle to invent spending or income. Ask about occupation only when it clarifies something material, such as whether delivery earnings are net of fuel expenses.

The planner provides candidate information gaps, not a fixed dialogue script. The LLM chooses a relevant question and its wording from the actual context, normally one question at a time.

| Situation | Useful next question | Reason |
| --- | --- | --- |
| Salary is known but due date is missing | “When will that salary reach your account?” | Determines whether it can cover an upcoming payment. |
| A client owes money | “When did they agree to pay, and how certain are you it will arrive by then?” | Separates a receivable from spendable cash. |
| Variable delivery earnings | “Is that what reaches you after work expenses, or before them?” | Avoids treating gross receipts as available money. |
| “Thirty thousand—actually twenty-five” | “Is ₹25,000 your revised estimate for this period?” when the correction's scope is unclear | Prevents replacing the wrong fact. Explicit, unambiguous corrections need only acknowledgement. |
| Food is ₹20,000–₹25,000 | “Should we keep that full range protected in the plan?” | Preserves uncertainty and the user's priorities. |
| Parent repayment has no stated deadline | “Have you agreed on a repayment date?” | Avoids assuming informal debt is freely deferrable. |
| User refuses spending changes | “I’ll keep those amounts. With them unchanged, this payment remains uncovered.” | Explains consequences without moral judgement. |
| User wants another loan | “I can help map your current payments and cash gap, but this planner doesn't recommend new loans.” | Respects the assignment boundary while retaining the current task. |

Spending flexibility is **protected / open to discussion / user-approved adjustment / unknown**. Essential versus optional is a separate classification and is user-correctable. “Optional” is not permission to remove an expense. Family support, food, subscriptions and leisure are not judged. Do not infer agreement from silence.

Enough information means the major stated obligations and resources have usable amounts/timing or explicit unresolved labels, and the user has had an opportunity to identify missing categories. Do not force exactness when the user does not know. Produce a provisional plan with limitations when necessary; reserve “confirmed” for the user's confirmation of the current plan version.

## 3. Financial model

Use INR and Asia/Kolkata for the first build. Freeze `as_of` and `window_start` per session. Define the 30-day window as `[start, start + 30 days)`, including today and the following 29 local calendar dates. Ask before changing the horizon on a resumed session. These are explicit product assumptions, not universal financial rules.

### Income and incoming cash

Treat source, amount knowledge, timing knowledge, and receipt reliability as independent dimensions.

| Dimension | Representation |
| --- | --- |
| Kind | Salary, gig/platform earnings, freelance invoice, business draw, rent received, pension/benefit, support, refund/reimbursement, return of money lent, other. |
| Amount | Exact, estimate, bounded range, or unknown; integer paise when a value exists. |
| Receipt | Received, expected with user-confirmed amount/date, uncertain, cancelled. Future receipts are never labelled guaranteed. |
| Date | Exact date, earliest/latest interval, or unknown. A contractual due date can differ from expected arrival. |
| Recurrence | One-off, weekly, monthly, or explicit dated occurrences. Expand only into the active horizon. |
| Provenance | Source turn, user wording for the fact, source type, confirmation/conflict status, revision. |
| Cash availability | Net amount available for this plan; taxes, work costs and protected reserves are separate confirmed amounts where relevant. |

Examples: salary can have a known amount but a delayed date; a freelance invoice can be legally owed but have uncertain collection; influencer income can have both a variable amount and an uncertain payout date. Unknowns remain unknown. Do not assign made-up probabilities or average an amount range without agreement.

Opening cash is a snapshot of accessible funds at `as_of`. Income already reflected in that balance is not added again. Transfers between included accounts do not create new income. A refund or return of money lent can increase cash without being classified as earnings. A partial invoice receipt reduces the unpaid amount and is counted in cash only once.

### Debts and payment obligations

Separate an account's outstanding balance from payments due within the horizon. Capture account kind, creditor label, borrower context, known outstanding balance, dated required instalments, overdue amounts, paid/unpaid status, and verified terms if supplied. Do not require full account numbers or PAN for manual planning.

- Credit-card statement total, minimum due and unbilled balance are different fields. Never add the minimum to the statement total. Selecting the minimum as a scenario does not mean the balance is cleared or interest-free.
- BNPL is represented as dated obligations, regardless of marketing label. Avoid double-counting it as both a purchase expense and the repayment of that purchase.
- Family/friend debts have their own dates and user priorities; “informal” does not imply “unimportant.”
- Overdue amount may be included in a quoted current total. Clarify before adding both.
- Future instalments outside the horizon do not become current expenses. A remaining loan balance is not automatically due this month.
- Do not calculate a closure quote, penalty, interest charge or savings without the necessary verified terms. Long-term amortisation/optimal payoff is deferred.

### Expenses and planned allocations

Store amount/range, date or period, recurrence, category, protected/flexible preference and paid/unpaid status. Ask whether a figure is the full month's total or the amount still to spend. Separate scheduled investment contributions from spendable balances; do not liquidate assets or cancel investments by default.

For a small business owner, distinguish gross sales, business expenses/reserves and money actually available to the household. Do not aggregate a company's turnover into a founder's personal income. Full business accounting and multi-entity liability analysis are outside v1.

### Minimal persisted structure

- `sessions`: authenticated owner user ID, lifecycle status, horizon, current financial state JSON, monotonically increasing revision, timestamps and expiry.
- `financial_changes`: session, revision, operation id, source turn reference, validated change and timestamp; supports diagnosis and idempotency without requiring an event-sourcing framework.
- `plans`: session/revision, deterministic calculation output, assumptions, unresolved items and understanding status.

Use typed Pydantic models inside the state JSON. Each fact/entity has a stable ID. A change is a validated operation on an identified field, not an unstructured replacement of the whole conversation. Do not store raw audio by default. Retain only the source excerpts needed for corrections; full evaluation recordings use synthetic scenarios and explicit recording consent.

## 4. Calculation and planning policy

The Python calculation engine owns financial arithmetic. The LLM extracts proposed facts, asks questions and explains results. React renders server results; it does not maintain a second finance calculator.

For each scenario and date:

`projected balance = opening accessible cash + cumulative included inflows - cumulative planned outflows`

Output both the closing balance and the lowest dated balance, first shortage date, cumulative funding gap, and unresolved timing risks. A projected negative value diagnoses an uncovered obligation; it is not permission to spend unavailable funds. Distinguish the all-obligations projection from the feasible allocation schedule and show unpaid obligations separately.

1. Use received accessible funds and explicitly confirmed expected receipts for the base projection. Label future receipts as expected. Show an alternative excluding materially uncertain receipts; do not make a plan depend on an overdue invoice without saying so.
2. For bounded uncertain inflows, include them only in clearly conditional scenarios. For a stated arrival interval, the cautious timing uses its latest date. An unknown date cannot cover a specific deadline.
3. Preserve expense ranges. Show lower/upper outcomes from coherent assumptions; the cautious expense case uses the upper bound. These are scenarios, not confidence intervals. Do not imply every combination is equally likely.
4. Undated expenses remain visible reservations. Ask for timing if it changes feasibility. Never silently spread them evenly or report “all dates covered” while material timing is unknown. Any agreed weekly allocation is labelled as an assumption.
5. Same-day credits and debits require order awareness: do not assume salary clears before an auto-debit. Flag the ordering risk or use debit-first as an explicitly stated cautious case.
6. First establish user-protected living costs and commitments. Order debt obligations by due date, while identifying overdue items and user-stated consequences. Resolve same-date competition with the user when money is insufficient. Do not silently optimise only for interest rate or automatically deprioritise informal debts.
7. Show changes to flexible spending only as proposals. Apply them to the main plan after user agreement. Contacting a lender or a person owed money can be a proposed action; a changed date or offer becomes a fact only after the user reports an actual agreement.
8. Do not recommend another loan, fabricate lender terms, simulate guaranteed credit-score improvements, or claim a payment was executed. Suggested, user-reported completed, and verified completed are different states; v1 has no payment execution or verification integration.

Amounts use integer paise, with validated bounds compatible with JSON/JavaScript safe integers. Unknown is `null` with an explicit knowledge state, never zero. Rate-based arithmetic, if added, requires decimal arithmetic and a specified rounding rule. Reject negative expense amounts unless represented as an explicit refund/correction. Keep exact values for calculation and label rounded display values.

### Illustrative calculation fixture, not the demo's numbers

Opening cash ₹5,000 on September 10; salary ₹50,000 on September 30; EMI ₹12,000 on September 15; essential payment ₹20,000 on September 22. No other flows in this deliberately simplified fixture.

Closing balance is ₹23,000, but the balance first drops below zero on September 15 (−₹7,000) and reaches −₹27,000 before salary. An uncertain ₹15,000 client payment on September 14 belongs in a separate scenario; even if it arrives, the September 22 balance is −₹12,000. The system must surface both timing problems rather than describing the positive closing balance as sufficient.

## 5. System design

Proposed stack: Next.js/React/TypeScript with a thin tRPC application layer; Python FastAPI + Pipecat + deterministic finance functions; Postgres; Daily for the live session. This accommodates the user's tRPC preference while keeping financial logic next to the Python agent.

```text
Browser -- tRPC --> Next.js -- typed HTTP --> FastAPI session/finance service
   |                                               |          |
   |                                               |       Postgres
   +---- Daily WebRTC audio + RTVI messages ---- Pipecat task
                                                   |
                                         streaming STT / LLM / TTS
```

Pipecat documents the streaming STT → LLM → TTS pipeline and Daily/RTVI integration. Use that inspectable pipeline first; select the exact providers/models after checking available keys, streaming support, Indian English recognition and measured latency. Do not infer a production model choice from the assignment's mention of coding assistants. [Pipecat pipeline](https://docs.pipecat.ai/pipecat/learn/pipeline), [Daily runner](https://docs.pipecat.ai/api-reference/server/utilities/runner/guide).

### tRPC and the Python boundary

tRPC gives useful TypeScript inference; it does not inherently make an API more secure than REST. Authentication, session ownership, runtime validation, rate limits and secret handling still require implementation. [tRPC authorization](https://trpc.io/docs/server/authorization), [validators](https://trpc.io/docs/server/validators).

Use tRPC for `session.start`, `session.state`, `session.correct`, `session.end`, `session.delete`, and `plan.review`. FastAPI exposes corresponding internal endpoints plus health checks. Generate the TypeScript HTTP client/contracts from FastAPI's OpenAPI schema, and validate untrusted payloads at runtime. CI checks generated contract drift. tRPC's type inference does not automatically cross into Python. [FastAPI SDK generation](https://fastapi.tiangolo.com/advanced/generate-clients/).

The extra Node-to-Python hop is an accepted cost of this proposed tRPC design, not a second business-logic layer. A simpler alternative is React plus a generated FastAPI client without tRPC; choose it if maintaining the extra boundary proves disproportionate. Do not implement both paths.

### Authoritative state and live updates

1. A finalised user turn proposes a batch of fact changes with stable entity IDs, source-turn ID, operation ID and expected state revision.
2. Backend validates values and resolves the correction target. Ambiguous/conflicting facts produce a clarification item; they do not silently replace confirmed facts. Explicit corrections supersede the old value.
3. Commit changes and recalculated plan under one session lock and database transaction, incrementing the revision once. Repeating an operation ID cannot double-add income or debt. Version conflicts cause refresh and re-evaluation.
4. Only after commit, emit a small `{type: 'state.changed', revision}` notification over RTVI. Browser invalidates its query and fetches the entire authoritative display snapshot through tRPC. Pipecat supports custom messages; financial state need not be embedded in oversized transport messages. [Custom messaging](https://docs.pipecat.ai/client/guides/custom-messaging).
5. Client applies only newer revisions and replaces affected cards together. Reconnect always fetches the latest snapshot. A low-frequency active-session refresh recovers a lost notification; no financial correctness depends on notification delivery.
6. The agent receives the same committed calculation result. A new correction invalidates an older plan explanation and understanding confirmation. Stop queued stale speech where possible, then explicitly correct any outdated figure already spoken. Check revision before enqueuing a numeric plan summary.

LLM tools are limited to reading current state, proposing validated changes, requesting a calculation/conditional preview, and recording the user's understanding response. The server binds session ownership; the model cannot select an arbitrary session or mark a lender action verified. Batch facts from a single utterance to reduce inconsistent intermediate states.

For the final numeric summary, render key balances/dates from calculation output through a small deterministic narration formatter. The agent can explain surrounding context naturally. This reduces number drift without imposing a questionnaire.

### Lifecycle and failure behavior

The initial Python service runs one application worker and manages bounded background Pipecat tasks, with one active voice task per session. No Redis or distributed queue initially. Apply a concurrency cap and timeout, and reject excess starts clearly.

Persist session state before issuing connection details. Create a private Daily room and short-lived room-scoped participant token server-side; secrets never reach the browser. Daily explicitly supports room binding and expiry. [Daily meeting-token API](https://docs.daily.co/reference/rest-api/meeting-tokens/create-meeting-token).

Start is idempotent. On start failure clean up partial resources. End stops the bot, closes/leaves the session and retains the last valid plan for review. A crash leaves a recoverable saved state and an interrupted-call status; startup reconciles stale active sessions. Browser disconnect has a short bounded reconnect grace period, then releases the task. Cleanup must run on cancellation and provider errors.

Handle microphone denial, room/token failure, STT/LLM/TTS errors, tool timeout, database failure, interruption during a correction, and stale events. Keep the last valid cards visible with a clear connection/error state. Never fill missing results with invented financial data.

### Persistence and deployment

Docker Compose starts `web`, `agent`, and `db`, applies migrations automatically, and exposes the web app at proposed `http://localhost:3000`. The database and internal agent API stay on the Compose network. Health checks distinguish process liveness from dependency readiness. No cloud deployment is needed for submission.

Local Postgres in Compose is the database target. RDS, Supabase, Convex and cloud hosting are outside this submission scope.

Configuration contract to finalise during the voice spike: `DAILY_API_KEY`, selected STT/LLM/TTS credentials and model identifiers, `DATABASE_URL`, session signing secret, internal service credential, public app origin and internal backend URL. `.env.example` must contain all actual required values with placeholders; README distinguishes required keys, optional settings and local defaults. Startup must identify missing configuration without printing secrets.

The scaffold already uses Better Auth email/password accounts and server-side sessions. Bind every financial session and tool operation to the authenticated user, enforce same-origin protections and limits, and keep provider keys server-side. Google is optional and does not block the assignment. Explain provider processing and the absence of default audio recording before a live session.

## 6. Interface

One conversational workspace with a clear start/end control, microphone and connection states, and progressively disclosed cards:

- Available cash and incoming money, separating expected and uncertain receipts.
- Upcoming commitments, including formal and informal debt.
- Protected spending and user-approved adjustment previews.
- A 30-day timeline with first shortfall, lowest balance and conditional receipts.
- Missing/conflicting information with a direct correction route.
- Final plan with the dated actions, assumptions, uncovered obligations and expandable arithmetic.

Amounts visibly carry “estimated,” “range,” “not yet received,” or “needs confirmation” labels when relevant. Hide irrelevant cards rather than rendering an empty dashboard. Use deterministic card components from typed data; no arbitrary model-generated HTML. A card correction uses the same validated change pathway as speech.

## 7. Verification and build sequence

See [scenario matrix](scenario-matrix.md). The matrix is a proposed test plan, not evidence of passing tests.

1. **Voice feasibility:** Docker-started browser and Pipecat/Daily call with one question/answer, interruption and end cleanup. Measure first-response latency and check English output before building extensive UI.
2. **Financial engine:** pure calculations, date/range handling, debt versus instalment distinctions, clear incomplete states, and tests with manually checked fixtures.
3. **One complete journey:** tool mutations → transaction → updated cards → revised speech → final plan → understanding check. Include the ₹30,000 → ₹25,000 correction and an uncertain receivable.
4. **Failure and boundary checks:** stale revisions, duplicated operations, provider failures, multiple sessions, lost notifications, refusal to adjust spending, and requests for a new loan.
5. **Submission rehearsal:** clean Compose startup, documented configuration, full demo, limitations and reproducible test results. The candidate writes the journal independently throughout.

Collect unit/integration results separately from live conversation evidence. Use deterministic assertions for arithmetic and state consistency; use a stated human rubric for relevance, non-judgemental tone and explanation quality. An LLM judge, if used, is supplementary and can be wrong. Avoid reporting a tiny synthetic sample as a general success rate.

Measure voice response latency from detected end-of-user-turn to first audible response, and card latency from committed revision to rendered revision. Proposed initial targets are p95 voice response below 3 seconds and card update below 1 second on the documented test setup; these are targets, not measured claims. Report sample size, providers/models, hardware/network and failures.

Track A is selected. Demonstrate relevant follow-ups, corrections, interruptions, retained context and understanding through real conversations. Core calculation and integration tests remain required; do not build a separate Track B evaluation platform.

## 8. Open choices before application scaffolding

- Actual deadline and time available.
- Voice-provider credentials/budget and the candidate's familiarity with Python/TypeScript.
- Confirm remaining stack after the voice spike; tRPC is proposed, not a security guarantee.
- Outdated hosting question, outside current scope: whether Vercel was intended by “virtual”; hosting is not a prerequisite for local development.

Local Docker delivery and Track A are explicit user requirements. Other unimplemented architecture details remain proposals unless stated otherwise. Revisit the spec as implementation evidence arrives.
