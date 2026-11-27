# Phase 1 verification — 2026-10-31

Scope: local synthetic demonstration on `codex/project-initialization`, starting from `b112b85`. No remote push or Phase 2 implementation. Results below were executed locally, not inferred from CI configuration.

## Acceptance results

| Check | Actual result | Scope / limits |
|---|---|---|
| Initial backend baseline | 84 passed, 5 skipped | SQLite; prior ingestion tests retained |
| Final backend, Windows/PostgreSQL | 153 passed, 0 failed | Disposable per-test schemas; includes current private contract fixtures |
| Final backend, SQLite | 145 passed, 8 skipped, 0 failed | Skips require PostgreSQL; fresh migrated unit fixtures |
| Final backend, Linux/PostgreSQL | 151 passed, 2 skipped, 0 failed | Rebuilt container; skips are private fixtures absent from image |
| Frontend | 6 passed, 0 failed | API boundary including supervisor identity; no case workbench UI claim |
| Ruff / format | Passed | Backend and scripts |
| ESLint / Prettier / TypeScript / Vite | Passed | Frontend lint, formatting and production build |
| PostgreSQL migration / drift | Passed | Revision `0003_case_security`, nine domain tables, rollback probe removed; Alembic detected no new operations |
| Live case API | 17 checks passed | Loopback through nginx; temporary users, case, alert, receipt and audit events removed |
| Live auth / ingestion | 12 checks passed | Existing smoke suite; temporary users and ingestion records removed |
| Dependency consistency | Passed | `pip check` found no broken requirements |
| Backend advisory audit | No known vulnerabilities found | `pip-audit` against existing pinned backend lock in disposable container, `--disable-pip --no-deps`; advisory availability is not a penetration test |
| Frontend advisory audit | 0 vulnerabilities | `npm audit --audit-level=high` |
| Publication boundary | Passed | Tracked/candidate source checked; private assets and secrets remain ignored |
| Compose | Passed | Configuration, rebuild, startup; database/API healthy, frontend serves loopback requests |

## Executed entry points

- `.venv\Scripts\python.exe -B -m pytest backend/tests -q -p no:cacheprovider --tb=short --maxfail=1`.
- PostgreSQL host run: same pytest suite with `TRUEFLAG_TEST_POSTGRES_URL` assigned in-process from local settings; no connection string printed.
- Linux run: rebuilt backend image, read-only tests mount, PostgreSQL test URL from container settings; same pytest options. Tests use generated isolated schemas, not existing application records.
- `.venv\Scripts\python.exe -B -m ruff check backend scripts` and `ruff format --check backend scripts`.
- Frontend `npm run format:check`, `npm run lint`, `npm test`, `npm run build`, `npm audit --audit-level=high`.
- `docker compose config --quiet`, `docker compose up -d --build backend frontend`, `docker compose exec -T backend alembic check`.
- `scripts/verify_postgres.py`, `scripts/smoke_cases.py`, `scripts/smoke_http.py`, `scripts/check_publication.py`.
- Backend `pip-audit` installed only into a temporary directory of a disposable container; no dependency manifest or application environment changed.

## Security properties exercised

- Unauthenticated requests, analyst assignment denial, cross-analyst/unassigned IDOR, hidden/nonexistent 404, forged role claims and current role/account revocation.
- Permission-scoped list/count/detail; bounded validated query options; list metadata projection and strict feature allowlist on details, including injected forbidden stored fields.
- Manager-only assignment/reassignment/unassignment, eligible active analysts, strict expected version, closed/stale conflicts, no-op semantics and reassignment revocation.
- Concurrent PostgreSQL assignment returns one success and one conflict. Real audit-trigger failure, simulated update/audit/commit failures and subsequent retries verify atomic rollback.
- Persistent cross-worker login limits, concurrent enforcement, window reset, ignored arbitrary forwarded headers, bounded declared/streamed bodies, safe error/log fields and server-generated correlation IDs.
- Existing 27-feature ingestion validation, idempotency, duplicate races and transaction rollback remain covered. No score, route, closure or dismissal is added.

## Limits and remaining gates

- One existing Starlette TestClient/httpx deprecation warning occurs per backend run; tests pass. Dependency audit warns that the pinned lock lacks distribution hashes; adding verified hashes remains supply-chain hardening.
- Login-limit records are intentionally retained as security state; smoke scripts remove only their generated domain records. Proxy/NAT bucket scope and inactive-key retention require operational configuration.
- Local-demo backend Phase 1 acceptance is complete. Production TLS/identity, runtime DB least privilege, team/tenant scoping, protected audit retention, backups and browser case-workbench acceptance remain future gates.
- Phase 2 document is a design: the model was hashed, not loaded, during this task. All 25 staged reference identities match; no new reference replay or SHAP computation is claimed.
