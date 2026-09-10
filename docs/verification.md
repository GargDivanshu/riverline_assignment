# Foundation verification

Scope: authentication and empty workspace scaffold, checked locally on Windows on 2026-09-10/11. This does not establish completed assignment acceptance cases.

| Check | Result | Coverage |
| --- | --- | --- |
| Next.js production build | Passed | Compilation and generated routes |
| TypeScript and ESLint | Passed | Web source |
| Node tests | 2 passed | Authentication input validation |
| Python pytest | 4 passed | Internal authentication, required user context, empty state/date window, unavailable voice endpoint |
| Ruff | Passed | Python source |
| Playwright using Chrome | 3 passed | Protected page/API rejection; signup, workspace/backend, dialogs, signout, wrong password, login; mobile overflow and reduced-motion layout |
| Desktop/mobile screenshots | Reviewed | Login and workspace; mobile brand selector and secondary-text contrast corrected |
| Docker Compose configuration | Passed | Configuration only |

Browser tests used real Next.js authentication and Python with PGlite's local PostgreSQL protocol adapter. This does not replace native Postgres or Docker integration testing. Synthetic accounts persist in ignored local data.

Docker startup is unverified: Docker Desktop's Linux engine cannot start without WSL on this machine. Chromium downloads timed out, so tests used installed Chrome. Python tests emit upstream Starlette/httpx and AnyIO deprecation warnings. PGlite schema inspection emits a rate-limit column type warning on subsequent starts; migrations and authentication journeys completed.

Unverified or absent: live Google OAuth, email delivery/recovery, voice, interruption/latency, financial persistence/arithmetic, multi-user financial isolation, load behavior, cloud deployment and clean Docker startup. The scenario matrix contains proposed acceptance cases, not passing tests.

No real financial data or provider keys were used. Root README contains startup and check commands.
