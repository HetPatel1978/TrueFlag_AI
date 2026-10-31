# Implementation status — 2026-10-31

Seven functional phases are mapped below to the existing **five-week schedule**; they are not seven additional weeks. Phase 1/2 names follow the current request; labels for 3–7 organize the existing roadmap into planning workstreams, without implying separate historical approval.

| Phase | Verified completed functionality | In progress / pending | Acceptance / blockers |
|---|---|---|---|
| 1 — Foundation & Security | FastAPI/React/PostgreSQL/Compose, auth, synthetic ingestion, 27-field validation, atomic idempotency, scoped case APIs, supervisor/admin assignment, version conflicts, change audit, body/login limits, safe correlation/logs | Local-demo backend acceptance complete; no further Phase 1 implementation active | PostgreSQL/SQLite security and regression suites; frontend role tests; migration/drift and live HTTP checks. No Phase 1 functional blocker; production security is not certified |
| 2 — AML Risk Intelligence | Private approved RF/contract/policies/SHAP references retained; all 25 staged identities inspected without loading the model; integration design documented | Loader, live scoring, policy recommendation, explanation adapter, assessment/job migration, endpoints and regression harness all unimplemented | PHASE2_INTEGRATION_PLAN defines acceptance: 4000 scores, 12000 routes, failure/authorization/persistence tests. Public redistribution rights unresolved; existing SHAP loader is UI/cohort-bound |
| 3 — Regulatory/Evidence Retrieval | Only historical saved prototypes/reference evidence; no current retrieval service | Approved corpus, source rights, institution/jurisdiction/as-of scope, permission-aware retrieval and relevance evaluation | Reproducible source/citation and access checks; corpus/source-use decisions pending |
| 4 — AI Investigation | Provider-neutral protocol from initialization only | Provider adapter, evidence-grounded drafts, citation validation, abstention and bounded tool workflow | Approved provider/data boundary and adversarial evaluation required; no LLM integration or agent execution enabled |
| 5 — Analyst Workbench & Human Decisions | Frontend account verification; backend case-read/assignment foundation | In-memory application sessions, case/assignment UI, notes, review/approval state machine, evidence view and reports | Browser/IDOR/concurrency/approval acceptance; no automated closure/filing and no current case workbench UI |
| 6 — Monitoring & Controlled Evaluation | Health/readiness, safe request/error correlation, existing immutable experiment evidence and historical baseline replay | Queue/latency/quality/drift metrics, reviewed feedback curation, evaluated promotion procedure | No automatic retraining; new generalization claims need appropriate independent/customer/time-aware data |
| 7 — Deployment & Governance | Local non-root app containers, loopback ports, migrations and CI configuration | Enterprise identity, TLS, least-privilege runtime DB roles, tenancy, retention, backup/restore/rollback and deployment acceptance | Source rights/hosting/data governance decisions pending; no banking certification or production authorization claimed |

## Acceptance evidence

- Initial claim verification: branch `codex/project-initialization`, clean working tree at `b112b85`; pre-change suite 84 passed, 5 PostgreSQL-only skips.
- Phase 1 PostgreSQL suite on Windows: **153 passed**; includes all prior ingestion regressions, case access and real assignment/login races and trigger rollback.
- SQLite suite: **145 passed, 8 PostgreSQL-only skips**. Tests use fresh migrated files; persistent SQLite is not a deployment target.
- Rebuilt Linux container against PostgreSQL: **151 passed, 2 private-fixture skips**; no private assets were mounted into the container.
- Frontend: **6 tests passed**, lint and production build passed; tests verify supervisor identity parsing, not browser case-workbench acceptance.
- Local private contract checks validate the exact retained field/hash contract and all 10000 synthetic rows without inference or persistence. Container/CI checks skip private fixtures when absent.
- Live schema/drift checks and **29 HTTP checks** passed. See [Phase 1 verification](PHASE1_VERIFICATION.md) for executed commands and limits; counts are not inferred from configured CI.
- Known non-blocking warning: existing Starlette TestClient/httpx deprecation. No external dependency migration is required for these features.

## Exact next implementation task

**Phase 2, only after a new request:** implement the isolated SHA-verified RF artifact loader and its trust/dependency/contract tests, preserving serialized `trueflag` module names. Do not add a scoring endpoint, retrain, replace the model, or enable automatic dismissal as part of that first task.

## Deliberate limits

- Supervisor scope is the entire current workspace, not an invented team hierarchy. Multi-tenancy/team scoping is pending enterprise data modeling.
- Current list/detail and assignment features do not implement evidence retrieval, review dispositions, filing approvals or model assessments.
- Phase 1 acceptance is for a secure synthetic local demonstration. Deployment controls and external source/provider approval remain explicit future gates.
- This task ends after documentation, checks and a local development-branch commit. No GitHub push or later-phase implementation is authorized.
