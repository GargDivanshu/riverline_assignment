# Foundation verification

Scope: authentication, empty workspace scaffold and the first live voice slice, checked locally on Windows/Ubuntu on 2026-09-10/11. This does not establish completed assignment acceptance cases.

| Check | Result | Coverage |
| --- | --- | --- |
| Next.js production build | Passed | Compilation and generated routes |
| TypeScript and ESLint | Passed | Web source |
| Node tests | 2 passed | Authentication input validation |
| Python pytest | 8 passed | Internal authentication plus voice-session idempotency, ownership, capacity, cleanup and provider-failure handling |
| Ruff | Passed | Python source |
| Playwright using Chrome | 3 passed | Protected page/API rejection; signup, workspace/backend, dialogs, signout, wrong password, login; mobile overflow and reduced-motion layout |
| Desktop/mobile screenshots | Reviewed | Login and workspace; mobile brand selector and secondary-text contrast corrected |
| Docker Compose build and startup | Passed | Postgres, Python and Next.js all became healthy; `/api/health` returned `ok` |
| Provider smoke checks | Passed | Daily room API, ElevenLabs live STT and TTS, OpenRouter authentication and GPT-5.6 Terra inference |
| Voice backend lifecycle | Passed | Private Daily room creation, `starting` status, authenticated status lookup and explicit end cleanup |

Browser tests used real Next.js authentication and Python with PGlite's local PostgreSQL protocol adapter. This does not replace native Postgres or Docker integration testing. Synthetic accounts persist in ignored local data.

Chromium downloads timed out, so prior browser tests used installed Chrome. Python tests emit upstream Starlette/httpx and AnyIO deprecation warnings. PGlite schema inspection emits a rate-limit column type warning on subsequent starts; migrations and authentication journeys completed.

Unverified or absent: live Google OAuth, email delivery/recovery, browser-to-bot conversation quality, interruption/latency, financial persistence/arithmetic, multi-user financial isolation, load behavior and cloud deployment. The scenario matrix contains proposed acceptance cases, not passing tests.

No real financial data was used. Provider keys from the ignored local `.env` were used only for the named voice smoke checks and were never printed or committed. Root README contains startup and check commands.
