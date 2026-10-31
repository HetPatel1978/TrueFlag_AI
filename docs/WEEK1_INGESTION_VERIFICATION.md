# Week 1 ingestion verification — 2026-10-31

This is subsequent development evidence, separate from historical initialization checks in SETUP_STATUS.md.

## Implemented

- Admin-only `POST /api/v1/alerts`, strict synthetic envelope and unchanged 27-predictor field set.
- Required idempotency key, durable hashed-key receipt, independent source-ID deduplication, and 409 content conflicts.
- One transaction for alert, linked unassigned open case, actor-attributed creation audit and receipt; no success response before commit.
- Additive migration `0002_alert_ingestion`; shared expected revision for readiness and database verification.
- Input-safe validation errors and neutral database failures. No inference imports, predictions, routes or automatic dismissal.
- API documentation, roadmap, security status and CI PostgreSQL integration checks updated.

## Actual checks

| Check | Result / scope |
|---|---|
| SQLite suite | 84 passed; 5 PostgreSQL-only checks skipped |
| Windows PostgreSQL suite | 89 passed, including optional private contract/data checks |
| Linux container PostgreSQL suite | 87 passed; 2 private-reference checks skipped because no private assets enter containers |
| Real concurrent requests | Four passing scenarios: same key, different keys/same source, conflicting key/different sources, conflicting source/changed input |
| Rollback | Failures at every write stage and pre-commit; real PostgreSQL trigger failure after prior writes; no partial records and successful retry afterward |
| Contract fidelity | Exact retained predictor order/exclusions/hash; all 10,000 synthetic rows validate without scoring/persistence; missing income distinct from zero; large integers preserved |
| Live HTTP | 12 passing checks through frontend proxy, including admin creation/replay/conflict, analyst rejection and anonymous rejection; generated accounts and ingestion records removed |
| PostgreSQL migration | Revision 0002, eight domain tables; rollback probe passes; Alembic reports no schema drift |
| Container setup | Compose configuration validates; API/frontend images build; migration completes and API becomes healthy |
| Lint/format/publication | Ruff, formatting, whitespace and private/secret boundary checks pass before commit |

Known non-blocking warning: the pre-existing Starlette TestClient/httpx transport deprecation remains; no dependency migration is part of ingestion.

## Scope and limitations

- Single-alert ingestion only; no batch upload, case-read API, assignment workflow, ML worker integration or automatic decisions.
- Idempotency is persistent across application restarts and enforced by database constraints across concurrent workers. A transport failure around commit still requires retrying with the same key to resolve commit ambiguity.
- Synthetic classification is a caller assertion; this does not certify source data or grant actual customer-data access.
- Data-dependent contract checks are optional and local. CI runs both SQLite and PostgreSQL without private assets.
- Tests use generated PostgreSQL schemas and remove them on teardown; no existing application schema is dropped. Live smoke cleanup targets only its generated identities/source.
- Original teammate source/private packages and baseline assets remain unchanged; no new model replay, training or explanation generation occurred.

Next Week 1 work: authenticated case reads with assignment-aware authorization, followed by frontend session/ingestion integration and operational abuse controls. Commit is limited to `codex/project-initialization`; no push is part of this task.
