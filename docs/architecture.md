# Foundation architecture

This describes the scaffold as implemented. The broader [implementation spec](implementation-spec.md) remains the target for subsequent milestones.

## Responsibilities

| Part | Responsibility | Current status |
| --- | --- | --- |
| Next.js + React | Login and responsive financial workspace | Implemented |
| shadcn/ui | Accessible controls, account menu, dialogs and detail sheets | Implemented |
| Libraries.dev ThinkingOrb + Motion | Restrained conversation illustration and entrance motion; reduced-motion support | Implemented |
| Better Auth + Postgres | Email/password account creation, sign-in, session expiry and sign-out | Implemented; Google conditional on OAuth configuration |
| tRPC | Authenticated browser API with TypeScript inference | Implemented for workspace query |
| FastAPI + Pydantic | Internal typed service with authenticated user context | Implemented; returns an empty workspace |
| Daily | Live WebRTC audio transport, private rooms and participant tokens | Next milestone; not connected |
| Pipecat | Backend streaming pipeline, turn handling, conversation context and provider/tool orchestration | Dependency extra and module boundary only; not connected |
| Financial engine and persisted financial sessions | Validated facts, dated arithmetic, revisions and plans | Next milestone |

## The two paths

**Account and application path:** Browser → Next.js/Better Auth → Postgres. Protected pages and tRPC procedures check the server-side session. The authenticated tRPC workspace query calls Python through a generated OpenAPI client, forwarding an internal credential and the server-derived user ID. A browser cannot pick its own user ID or receive the internal credential. The Python endpoint checks the credential before accepting the user context.

**Future audio path:** Browser → Daily → Pipecat → streaming STT → LLM → financial tools → TTS → Daily → browser. Daily transports audio; Pipecat connects processing stages. The LLM handles language and selects tools; our deterministic functions own money calculations. Neither Daily nor Pipecat supplies the financial policy. [Daily documentation](https://docs.daily.co/docs/daily-js/introduction), [Pipecat introduction](https://docs.pipecat.ai/pipecat/get-started/introduction).

Example: an income correction is proposed by the model, checked against the right fact, saved with a new revision, and recomputed. A small RTVI notification tells the UI to fetch that revision. The agent explains the same computed result. Audio will not travel through tRPC, and API type safety does not substitute for authorization.

## Authentication scope

The latest user request supersedes the spec's anonymous-capability-only proposal. Accounts are now required for the workspace. Better Auth manages password hashing and database-backed sessions. Rate limiting is enabled and stored in the database. Google sign-in is only rendered if both credentials exist. Automatic linking of accounts by matching email is disabled.

The local foundation does not send verification or password-reset emails. Email ownership is unverified, and this must be addressed before a public production launch. Local accounts are sufficient for developing the assignment. Google OAuth is implemented as configuration and a real redirect path, but has not been tested against a configured Google project. [Better Auth email/password](https://better-auth.com/docs/authentication/email-password), [Google setup](https://better-auth.com/docs/authentication/google).

## Data and runtime

Only accounts and authentication sessions are persistent today. The empty financial response is intentional: there are no fabricated balances, payment records, stored conversations or working finance mutations. The workspace's provisional date window is computed at request time; it will be frozen per financial session when those sessions are implemented.

Docker Compose defines web, agent and Postgres, applies the auth schema before web startup, and binds the web port to localhost. The optional PGlite script is a development/test fallback for machines without a working Docker engine. It is not used by Compose and is not equivalent to testing against native Postgres under load.

No queues, Redis, microservice split for individual tools, or cloud deployment are needed for this scaffold. Add coordination only when we introduce concurrent long-lived agent sessions or durable jobs that justify it.

## Next slice

1. Select STT/LLM/TTS providers using available keys and measured behavior.
2. Authenticate session start, create a private Daily room and short-lived tokens, and start a managed Pipecat task.
3. Prove English conversation, interruption, disconnect cleanup and end-to-end latency.
4. Add user-owned financial sessions and the pure calculation engine, then wire one correction into cards and speech.

The current voice button explains the unavailable feature without opening the microphone. The backend start endpoint returns 501. This is a scaffold, not a completed Riverline assignment.
