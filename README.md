# TrueFlag AI

Intelligent AML investigation platform: a five-week, production-oriented demonstration using **synthetic data only**. This is not a certified banking deployment. Existing source/research and private handoff directories remain unchanged.

## Implemented foundation

- FastAPI liveness (`GET /health`) and migration-aware readiness (`GET /ready`).
- Explicit account provisioning, Argon2 password hashes, expiring JWTs, current database-backed roles, protected identity and administrator audit endpoints.
- PostgreSQL domain schema and Alembic migration for users, alerts, cases, evidence, model scores, decisions and audit events.
- Admin-only `POST /api/v1/alerts`: strict 27-predictor synthetic inputs, durable idempotency, atomic alert/case/audit creation and concurrency-safe duplicate handling. See [API contract](docs/API_ALERT_INGESTION.md).
- Scoped `GET /api/v1/cases` and `GET /api/v1/cases/{case_id}`, filtered/bounded pagination and sorting, supervisor/admin `PUT /api/v1/cases/{case_id}/assignment`, version conflicts and atomic assignment audit. See [case API](docs/API_CASES.md).
- Persistent login throttle, streamed-body limits and safe server-generated request correlation; current roles and per-case access are enforced in the database query.
- React/TypeScript account-verification screen, real health check, tests, linting and build.
- Docker Compose, CI, local private-baseline staging and publication boundary checks.
- Isolated Phase 2.1 RF loader: approved artifact/source hashes, pinned runtime, fitted-pipeline checks and strict shared 27-feature validation. See [loader verification](docs/PHASE2_1_MODEL_LOADER.md).
- Pure Phase 2.2 single/batch RF scorer: all 4000 saved evaluation scores reproduced with maximum absolute error 0.0. See [scoring interfaces and verification](docs/PHASE2_2_RF_SCORING.md).
- Pure Phase 2.3 Efficiency/Balanced/Coverage recommendations: frozen policy verification, strict score/priority checks, manual-review fallback and exact 12000-route/audit parity. See [policy engine](docs/PHASE2_3_POLICY_ENGINE.md).
- Phase 2.4 authorization-gated exact SHAP service: independent verification, 41→27 aggregation/ranking and all 4000 saved explanations matched. See [explainability and Linux verification](docs/PHASE2_4_SHAP_EXPLAINABILITY.md).

- Phase 2.5 internal assessment persistence: approved RF/policy/SHAP orchestration, immutable versioned history, atomic completion audit, idempotent retries, stale-state protection and current case authorization. See [assessment persistence](docs/PHASE2_5_ASSESSMENT_PERSISTENCE.md) and [schema](docs/DATABASE_SCHEMA.md).

**Pending:** batch/CSV ingestion, inference/policy/explanation HTTP endpoints, durable jobs/worker deployment/timeouts, review transitions/approvals, live regulatory retrieval, LLM investigations and model promotion. Assessment services integrate the ML libraries with PostgreSQL internally; ingestion does not trigger inference. They cannot dismiss or close cases. The UI verifies an account; case/session/assignment screens remain pending.

## Local setup (PowerShell)

Requirements: Python **3.11**, Node **24** (22.12+ supported), Git, Docker Desktop with Linux containers. Use `npm.cmd` if PowerShell blocks `npm.ps1`. Do not weaken execution policy.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e backend
.\.venv\Scripts\python.exe scripts/init_env.py
docker compose up -d db
.\.venv\Scripts\alembic.exe -c backend/alembic.ini upgrade head
.\.venv\Scripts\python.exe -m app.security.bootstrap --username admin --role admin
.\.venv\Scripts\uvicorn.exe app.main:create_app --factory --host 127.0.0.1 --port 8010 --no-access-log
```

In a second terminal:

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

Open http://127.0.0.1:5173. Bootstrap prompts for a password; no default user exists. `.env` is generated locally, ignored, and never printed. Initialization refuses overwrites. Rotate secrets by an explicit later procedure, not by deleting application data.

For macOS/Linux, replace `.venv\Scripts\python.exe` with `.venv/bin/python`, use `.venv/bin/alembic` / `.venv/bin/uvicorn`, and use `npm`. Linux container behavior is separately verified; host-specific validation is recorded in [SETUP_STATUS](docs/SETUP_STATUS.md).

## Entire stack in Docker

```powershell
docker compose config --quiet
docker compose up --build -d
docker compose exec backend python -m app.security.bootstrap --username admin --role admin
```

Open http://127.0.0.1:8088; the API is http://127.0.0.1:8010. Migration is a separate one-shot service before API startup. PostgreSQL is persisted in a named volume; all published ports bind loopback. Host ports are configurable in `.env`; defaults avoid the already occupied port 8000. Do not use `docker compose down -v` against state you want to preserve. No private model/data enters Docker build contexts. Internet access is required for first installation/build.

## Checks

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
.\.venv\Scripts\python.exe -m ruff check backend scripts
.\.venv\Scripts\python.exe -m ruff format --check backend scripts
.\.venv\Scripts\alembic.exe -c backend/alembic.ini check
.\.venv\Scripts\python.exe scripts/verify_postgres.py
.\.venv\Scripts\python.exe scripts/smoke_http.py --base-url http://127.0.0.1:8088
.\.venv\Scripts\python.exe scripts/smoke_cases.py --base-url http://127.0.0.1:8088
.\.venv\Scripts\python.exe scripts/check_publication.py
cd frontend
npm.cmd test
npm.cmd run lint
npm.cmd run format:check
npm.cmd run build
```

Backend unit tests migrate disposable SQLite files; they are not PostgreSQL equivalence claims. `verify_postgres.py` verifies actual PostgreSQL connectivity/revision, migration consistency is checked separately, and CI provisions PostgreSQL. CI also reruns the suite with `TRUEFLAG_TEST_POSTGRES_URL`, using per-test disposable schemas for real concurrent ingestion and trigger-rollback checks. Optional private-fixture checks skip when baseline files are absent. Protected endpoint tests verify 401/403, invalid/expired JWTs, role changes, account deactivation, and audit behavior.

## Reuse the private baseline locally

With `../github` and `../private_handoff` present:

```powershell
.\.venv\Scripts\python.exe scripts/stage_baseline.py
python -m venv .venv-ml
.\.venv-ml\Scripts\python.exe -m pip install -r backend/ml-requirements.txt
.\.venv-ml\Scripts\python.exe -B scripts/verify_model_loader.py
.\.venv-ml\Scripts\python.exe -B scripts/verify_rf_scoring.py
.\.venv-ml\Scripts\python.exe -B scripts/verify_risk_policy.py
.\.venv-ml\Scripts\python.exe -B -m unittest discover -s backend/ml_tests -v
```

Native SHAP is blocked by Windows Application Control on the current host. For Phase 2.4, use the [verification-only Linux runtime](docs/PHASE2_4_SHAP_EXPLAINABILITY.md):

```powershell
.\.venv\Scripts\python.exe -B scripts/stage_explanation_reference.py
.\.venv\Scripts\python.exe -B scripts/run_ml_verification.py --build --check tests
.\.venv\Scripts\python.exe -B scripts/run_ml_verification.py --check shap
.\.venv\Scripts\python.exe -B scripts/run_assessment_verification.py --build --full-backend
```

The stager verifies both matching delivery manifests and every main private asset before copying a selected subset and reference source to ignored `assets/local/baseline/`. It refuses existing destinations and does not load a model, rescore, train, or change original files. Teammate source has no supplied redistribution license and stays untracked. The API package is `app`; serialized research `trueflag` modules are reserved for a separate ML runtime. Never force-add private assets.

## Working plan

- [Product scope](docs/PRODUCT_SCOPE.md) · [Five-week roadmap](docs/ROADMAP_5_WEEKS.md)
- [AS-IS](docs/ARCHITECTURE_AS_IS.md) · [TO-BE](docs/ARCHITECTURE_TO_BE.md)
- [Technology](docs/TECH_STACK.md) · [Reuse](docs/REUSE_MANIFEST.md)
- [Security](docs/SECURITY_PLAN.md) · [Decisions](docs/DECISIONS.md)
- [Actual setup evidence and blockers](docs/SETUP_STATUS.md)
- [Week 1 ingestion verification](docs/WEEK1_INGESTION_VERIFICATION.md)
- [Seven-phase implementation status](docs/IMPLEMENTATION_STATUS.md) · [Phase 2 integration design](docs/PHASE2_INTEGRATION_PLAN.md)

Before network exposure: approved proxy/perimeter limits, organization/tenant authorization, least-privilege database roles, TLS, security review, and operational acceptance remain required. Foundation login limits and case authorization are implemented; they do not constitute enterprise deployment acceptance. SAR labels are synthetic source dispositions, not evidence of criminality. Human decisions must remain distinct from labels and model routing.
