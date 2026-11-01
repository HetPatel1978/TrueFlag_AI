# Implementation status — 2026-10-31

Seven functional phases are mapped below to the existing **five-week schedule**; they are not seven additional weeks. Phase 1/2 names follow the current request; labels for 3–7 organize the existing roadmap into planning workstreams, without implying separate historical approval.

| Phase | Verified completed functionality | In progress / pending | Acceptance / blockers |
|---|---|---|---|
| 1 — Foundation & Security | FastAPI/React/PostgreSQL/Compose, auth, synthetic ingestion, 27-field validation, atomic idempotency, scoped case APIs, supervisor/admin assignment, version conflicts, change audit, body/login limits, safe correlation/logs | Local-demo backend acceptance complete; no further Phase 1 implementation active | PostgreSQL/SQLite security and regression suites; frontend role tests; migration/drift and live HTTP checks. No Phase 1 functional blocker; production security is not certified |
| 2 — AML Risk Intelligence | Phases 2.1–2.3 verified: secure loader, unchanged single/batch RF scorer, strict 27-feature contract, 4000 exact scores, versioned Efficiency/Balanced/Coverage recommendations and all 12000 saved routes/audit traces matched | SHAP adapter, assessment/job migration, deployed worker, HTTP endpoints and ingestion integration remain pending | 135 ML/policy tests pass with actual private artifacts; no automatic dismissal. SHAP and persistent workflow acceptance pending. Public redistribution rights unresolved; historical SHAP loader is UI/cohort-bound |
| 3 — Regulatory/Evidence Retrieval | Only historical saved prototypes/reference evidence; no current retrieval service | Approved corpus, source rights, institution/jurisdiction/as-of scope, permission-aware retrieval and relevance evaluation | Reproducible source/citation and access checks; corpus/source-use decisions pending |
| 4 — AI Investigation | Provider-neutral protocol from initialization only | Provider adapter, evidence-grounded drafts, citation validation, abstention and bounded tool workflow | Approved provider/data boundary and adversarial evaluation required; no LLM integration or agent execution enabled |
| 5 — Analyst Workbench & Human Decisions | Frontend account verification; backend case-read/assignment foundation | In-memory application sessions, case/assignment UI, notes, review/approval state machine, evidence view and reports | Browser/IDOR/concurrency/approval acceptance; no automated closure/filing and no current case workbench UI |
| 6 — Monitoring & Controlled Evaluation | Health/readiness, safe request/error correlation, existing immutable experiment evidence and historical baseline replay | Queue/latency/quality/drift metrics, reviewed feedback curation, evaluated promotion procedure | No automatic retraining; new generalization claims need appropriate independent/customer/time-aware data |
| 7 — Deployment & Governance | Local non-root app containers, loopback ports, migrations and CI configuration | Enterprise identity, TLS, least-privilege runtime DB roles, tenancy, retention, backup/restore/rollback and deployment acceptance | Source rights/hosting/data governance decisions pending; no banking certification or production authorization claimed |

## Acceptance evidence

- Phase 2.3 starts from clean `20a4ef2`: **135 ML/policy tests passed, 0 failed/skipped**; **12000 routes and audit traces matched**, zero mismatches/failures and zero retained/dismissed total differences in all three modes. Coverage has 456 changed-route High overrides. RF replay remains 4000/4000 exact, maximum error 0.0. See [policy acceptance](PHASE2_3_POLICY_ENGINE.md).
- Phase 2.3 backend rerun: **153 PostgreSQL passed**; **145 SQLite passed, 8 PostgreSQL-only skips**. Service-runtime boundaries: **101 passed, 34 scientific-runtime skips**; Linux without private assets: **82 passed, 53 private/runtime skips**. Historical subphase evidence below retains its original scope.
- Phase 2.2 starts from clean `bce4f78`: **81 ML tests passed, 0 failed/skipped**; **4000/4000 scores matched**, maximum absolute error **0.0**, zero mismatches/failures at absolute 1e-12 / relative 0. Rechecked batch sizes 1000/137; no policy or SHAP execution. See [scoring acceptance](PHASE2_2_RF_SCORING.md).
- Phase 2.2 backend rerun: **153 PostgreSQL passed**; **145 SQLite passed, 8 PostgreSQL-only skips**. Service-runtime ML checks: **50 passed, 31 private/scientific-runtime skips**. Historical Phase 1/2.1 counts below retain their original scope.
- Phase 2.1 starts from clean `635ec07`: **34 loader tests passed, zero skips/failures** in `.venv-ml`; standalone real loader verification passed with 27 predictors, 41 encoded features and 300 fitted trees, without fitting/scoring or reading a dataset. See [loader acceptance](PHASE2_1_MODEL_LOADER.md).
- Phase 2.1 backend regression rerun: **153 PostgreSQL passed**; **145 SQLite passed, 8 PostgreSQL-only skips**. In service runtime, loader boundary suite passes **19 tests, 15 real-runtime skips**; scientific acceptance above supplies the real-model evidence. CI is configured for boundary tests; no remote CI execution is claimed.
- Initial claim verification: branch `codex/project-initialization`, clean working tree at `b112b85`; pre-change suite 84 passed, 5 PostgreSQL-only skips.
- Phase 1 PostgreSQL suite on Windows: **153 passed**; includes all prior ingestion regressions, case access and real assignment/login races and trigger rollback.
- SQLite suite: **145 passed, 8 PostgreSQL-only skips**. Tests use fresh migrated files; persistent SQLite is not a deployment target.
- Rebuilt Linux container against PostgreSQL: **151 passed, 2 private-fixture skips**; no private assets were mounted into the container.
- Frontend: **6 tests passed**, lint and production build passed; tests verify supervisor identity parsing, not browser case-workbench acceptance.
- Local private contract checks validate the exact retained field/hash contract and all 10000 synthetic rows without inference or persistence. Container/CI checks skip private fixtures when absent.
- Live schema/drift checks and **29 HTTP checks** passed. See [Phase 1 verification](PHASE1_VERIFICATION.md) for executed commands and limits; counts are not inferred from configured CI.
- Known non-blocking warning: existing Starlette TestClient/httpx deprecation. No external dependency migration is required for these features.

## Exact next implementation task

**Proposed Phase 2.4, only after a new request:** implement an independently verified SHAP explanation adapter using approved model/input snapshots, preserving exact preprocessing and missing-income behavior. Verify score reconstruction, grouped attribution and provenance; keep HTTP/worker integration, persistent assessments and consequential human decisions behind separate acceptance gates.

## Deliberate limits

- Supervisor scope is the entire current workspace, not an invented team hierarchy. Multi-tenancy/team scoping is pending enterprise data modeling.
- Current list/detail and assignment features do not implement evidence retrieval, review dispositions, filing approvals or model assessments.
- Phase 1 acceptance is for a secure synthetic local demonstration. Deployment controls and external source/provider approval remain explicit future gates.
- This task ends after documentation, checks and a local development-branch commit. No GitHub push or later-phase implementation is authorized.
