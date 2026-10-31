# Initialization verification — 2026-10-30

This records checks actually executed during initialization. It does not mark the five-week roadmap complete. Commands assume repository root; credential values and personal runtime state are excluded.

| Check | Result | Evidence / scope |
|---|---|---|
| Remote identity | PASS | Explicit `HetPatel1978/TrueFlag_AI` remote; cloned fresh-reset main; separate initialization branch; original checkout untouched |
| Python service environment | PASS | Isolated Python 3.11.14; editable backend installed; package consistency check passed |
| ML environment | PASS | Separate Python 3.11.14 with exact recorded scientific pins; package consistency check passed |
| Frontend dependencies | PASS | Node 24.14.0 / npm 11.9.0; lockfile installed; patched lint/test/glob dependencies |
| Backend security/foundation tests | PASS | 16 tests on Windows; same 16 tests passed in Linux container with read-only test mount |
| Backend lint/format | PASS | Ruff checks and formatting |
| Frontend tests | PASS | Five API-boundary tests; no browser-layout acceptance implied |
| Frontend lint/format/build | PASS | ESLint, Prettier, TypeScript and Vite production build |
| npm vulnerability audit | PASS | Zero known advisories after tooling update and tested minimatch 11 override; time-bound registry result |
| PostgreSQL | PASS | Real PostgreSQL 17 container; seven domain tables; exact migration revision; rollback probe leaves no records |
| Migration drift | PASS | Alembic reports no new upgrade operations |
| Compose | PASS | Configuration validates; Linux frontend/backend/migration images build; migration completes before API readiness |
| HTTP delivery | PASS | API and frontend-proxied health/readiness return 200; unauthenticated identity returns 401; frontend HTML and CSP delivered |
| HTTP authentication/RBAC | PASS | Seven checks through the frontend proxy; generated temporary admin/analyst accounts removed afterward |
| Private asset integrity | PASS | Both matching source/private package manifests and all 107 main private assets verified |
| Baseline staging | PASS | Seven required private artifacts plus 18 source/dependency references staged locally and ignored; originals unchanged |
| RF replay | PASS | All 4,000 scores match exactly (maximum absolute difference 0); all 12,000 routes match; zero fits, threshold changes or SHAP generations |
| Publication boundary | PASS | Secret/private-format checks and Git ignore boundaries checked before commit; private assets, .env and environments remain untracked |
| Browser interaction/usefulness | NOT RUN | No claim of recipient browser acceptance or analyst usefulness |
| GitHub Actions | CONFIGURED | Workflow provided; remote execution status must be checked after push, not inferred from local tests |

## Running local services

- Workbench: http://127.0.0.1:8088
- API liveness: http://127.0.0.1:8010/health
- API/database readiness: http://127.0.0.1:8010/ready
- PostgreSQL: loopback port 5432; persistent project-specific named volume.
- No permanent account was invented. Provision the first account explicitly using the bootstrap command in README.

## Issues resolved during setup

- Sandbox network/ancestor-directory restrictions required host-access execution for dependency installation, Git operations and frontend bundling; no global execution policy was weakened.
- Docker Desktop was installed but its engine was stopped; started the existing engine and isolated project containers.
- Existing port 8000 was occupied; chose configurable project ports 8010 and 8088 without stopping that service.
- Initial test dependencies had critical advisories; upgraded compatible tooling and validated the patched glob matcher override. No force audit fix was used.
- Backend editable installation was refreshed after source creation; service and scientific environments remain separate.

## Remaining limitations / exact next commands

| Item | Next action |
|---|---|
| First permanent account | `docker compose exec backend python -m app.security.bootstrap --username admin --role admin` (interactive password prompt) |
| Source redistribution rights | Obtain explicit teammate/source-owner permission or license before moving copied reference code into tracked source |
| Live scoring/explanations | Week 2 adapter and service work; local verification script proves baseline replay, not a deployed inference service |
| Alert/case APIs | First Week 1 vertical slice: strict synthetic ingestion, idempotency, case creation and transaction-linked audit |
| RAG/provider | Approve corpus, scope, provider and data boundary before Week 3 integration; no fabricated provider or placeholder endpoint |
| Login abuse / DB privilege separation / TLS | Required before network exposure; explicitly tracked in SECURITY_PLAN |
| TestClient deprecation | Installed Starlette warns about httpx transport deprecation; tests pass; plan a compatible httpx2 migration rather than hiding the warning |
| Historical full research reproduction | Requires separately staged recovery material; not performed or represented by RF replay |

## Re-run baseline verification

```powershell
.\.venv-ml\Scripts\python.exe -B scripts/verify_baseline.py
.\.venv\Scripts\python.exe scripts/verify_postgres.py
.\.venv\Scripts\python.exe scripts/smoke_http.py --base-url http://127.0.0.1:8088
```

Smoke verification is loopback-only and removes only its generated accounts/events. No original owner database/browser state is imported. Replay remains conditional on previously exposed synthetic cases, not independent evaluation or proof of safe real-world dismissal.
