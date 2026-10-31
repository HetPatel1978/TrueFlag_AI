# TrueFlag AI

Intelligent AML investigation platform: a five-week, production-oriented demonstration using **synthetic data only**. This is not a certified banking deployment. Existing source/research and private handoff directories remain unchanged.

## Implemented foundation

- FastAPI liveness (`GET /health`) and migration-aware readiness (`GET /ready`).
- Explicit account provisioning, Argon2 password hashes, expiring JWTs, current database-backed roles, protected identity and administrator audit endpoints.
- PostgreSQL domain schema and Alembic migration for users, alerts, cases, evidence, model scores, decisions and audit events.
- React/TypeScript account-verification screen, real health check, tests, linting and build.
- Docker Compose, CI, local private-baseline staging and publication boundary checks.

**Not implemented:** incoming alert APIs, RF inference service, SHAP service, case transitions/approvals, live regulatory retrieval, LLM investigations, or model promotion. Their schemas/interfaces and roadmap are not completed features. The UI verifies an account; it does not yet maintain an application session.

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
.\.venv\Scripts\uvicorn.exe app.main:create_app --factory --host 127.0.0.1 --port 8010
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
.\.venv\Scripts\python.exe scripts/check_publication.py
cd frontend
npm.cmd test
npm.cmd run lint
npm.cmd run format:check
npm.cmd run build
```

Backend unit tests migrate disposable SQLite files; they are not PostgreSQL equivalence claims. `verify_postgres.py` verifies actual PostgreSQL connectivity/revision, migration consistency is checked separately, and CI provisions PostgreSQL. Protected endpoint tests verify 401/403, invalid/expired JWTs, role changes, account deactivation, and audit behavior.

## Reuse the private baseline locally

With `../github` and `../private_handoff` present:

```powershell
.\.venv\Scripts\python.exe scripts/stage_baseline.py
python -m venv .venv-ml
.\.venv-ml\Scripts\python.exe -m pip install -r backend/ml-requirements.txt
```

The stager verifies both matching delivery manifests and every main private asset before copying a selected subset and reference source to ignored `assets/local/baseline/`. It refuses existing destinations and does not load a model, rescore, train, or change original files. Teammate source has no supplied redistribution license and stays untracked. The API package is `app`; serialized research `trueflag` modules are reserved for a separate ML runtime. Never force-add private assets.

## Working plan

- [Product scope](docs/PRODUCT_SCOPE.md) · [Five-week roadmap](docs/ROADMAP_5_WEEKS.md)
- [AS-IS](docs/ARCHITECTURE_AS_IS.md) · [TO-BE](docs/ARCHITECTURE_TO_BE.md)
- [Technology](docs/TECH_STACK.md) · [Reuse](docs/REUSE_MANIFEST.md)
- [Security](docs/SECURITY_PLAN.md) · [Decisions](docs/DECISIONS.md)
- [Actual setup evidence and blockers](docs/SETUP_STATUS.md)

Before network exposure: rate limiting, organization/case authorization, least-privilege database roles, TLS, security review, and operational acceptance remain required. SAR labels are synthetic source dispositions, not evidence of criminality. Human decisions must remain distinct from labels and model routing.
