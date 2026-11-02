# Five-week development roadmap

Initialization provides a foundation, not five completed weeks. Checkboxes below remain open until acceptance evidence exists. Security is progressive from Week 1. No calendar dates or individual assignments are inferred.

Current acceptance: [IMPLEMENTATION_STATUS](IMPLEMENTATION_STATUS.md), [assessment APIs](API_ASSESSMENTS.md), and [Phase 2.8 operations](PHASE2_8_OPERATIONS.md). Internal monitoring and bounded synthetic load/recovery are verified; the Phase 2.9 risk workbench is integrated; production deployment acceptance remains pending.

## Week 1 — Foundation and integration

- **Objective:** one secure service, persisted domain and usable local environment.
- **Tasks:**
  - [ ] Accept setup evidence, license boundary and product scope.
  - [x] Add validated/idempotent synthetic alert ingestion and case creation in one transaction (API, strict 27-field contract, durable receipts, creation audit; see API_ALERT_INGESTION.md).
  - [x] Add authenticated case reads with assignment-aware access rules, supervisor oversight, protected assignment/reassignment and atomic version/audit updates (Phase 1).
  - [x] Phase 2.9: in-memory authenticated application sessions, role-aware navigation, logout cleanup and bounded authorization refresh.
  - [x] Add safe failure logging, server-generated request correlation, bounded request bodies and database-backed cross-worker login throttling (Phase 1).
- **Dependencies:** Python 3.11, Docker/PostgreSQL, accounts, agreed input envelope; no model needed for foundation tests.
- **Deliverables:** backend/frontend foundation, migrations, authentication/RBAC, CI and first ingestion vertical slice.
- **Acceptance:** valid alert persists; invalid/extra fields fail; same retry is idempotent; unauthorized access fails; restart preserves state; health differs from database readiness.
- **Risks / mitigation:** credential leakage → generated ignored secrets and scanner; namespace collision → separate API/ML runtime; unavailable infrastructure → exact blocker, never fake readiness.

## Week 2 — AML risk intelligence

- **Objective:** integrate the unchanged RF reference and policy semantics.
- **Tasks:**
  - [x] Phase 2.1: load the real fitted RF in compatible isolated runtime, pin model/contract/source identities independently of the artifact manifest, enforce the exact shared 27-field contract and verify native missing income.
  - [x] Phase 2.2: pure single/batch RF scorer with positive-class mapping, sanitized failure results and ID-aligned 4000-score regression (maximum error 0.0; absolute tolerance 1e-12 / relative 0).
  - [x] Implement strict 27-predictor validation at ingestion and isolated scoring, preserving missing versus zero income and unsupported KYC rejection.
  - [x] Phase 2.3: implement versioned deterministic recommendations and all 12000 saved route/audit comparisons, including 456 changed-route Coverage overrides; no automatic dismissal or case mutation.
  - [x] Phase 2.5: immutable versioned assessments, approved model/input/policy identity, verified explanations, atomic audit, idempotency and scoped internal retrieval.
  - [x] Phase 2.6: durable four-state jobs, claim/fencing, lease recovery, bounded retry/backoff and atomic completed-result/job/audit publication.
  - [x] Phase 2.4: exact SHAP service, required host authorization, independent output checks and 4000-reference parity; native missing/zero income preserved, no RF retraining.
  - [x] Phase 2.6: hard subprocess watchdog, cancellation, parent-death cleanup and bounded failure isolation.
  - [x] Phase 2.6: bounded Linux background worker and internal idempotent job requests.
  - [x] Phase 2.7: protected assessment request/status/history/detail APIs, strict contracts, case scope, request/read audit, queue capacity and shared API budgets.
  - [x] Phase 2.8: internal operational metrics, safe structured correlation and measured bounded synthetic load/recovery acceptance.
  - [x] Phase 2.9: authorized alert dashboard, safe case results/SHAP/provenance/history, explicit assessment requests and bounded async status workflow.
  - [x] Phase 2.10.1: canonical CSV contract/template, admin-only private staging, owner-scoped metadata, idempotency, expiry and audit.
  - [ ] Phase 2.10.2: column mapping and full-file validation preview.
  - [ ] Phases 2.10.3-2.10.6: approved chunked import, bounded assessment dispatch, batch UI/export and full-workflow acceptance.
  - [ ] Production deployment acceptance after separate approval.
- **Dependencies:** rights approval for any redistributed source; staged model/contracts; exact scientific dependencies; Week 1 persistence.
- **Deliverables:** live inference worker, deterministic policies, explanation artifacts and replay evidence.
- **Acceptance:** all 4,000 saved scores match within 1e-12 absolute tolerance and all 12,000 routes match; no fitting/tuning; input labels never enter features; attribution reconstruction passes fixed tolerances; failures require manual review and receive no capture/dismissal credit.
- **Risks / mitigation:** environment drift → isolated pins; old/new thresholds mixed → model/policy IDs; slow SHAP → asynchronous explanation status independent of route.

## Week 3 — AI investigation

- **Objective:** a bounded evidence-grounded assistant, not an autonomous investigator.
- **Tasks:**
  - [ ] Approve provider, data boundary, corpus rights, institution scope and jurisdiction.
  - [ ] Ingest versioned official passages with exact source/page/as-of references.
  - [ ] Implement permission-aware keyword retrieval; add semantic retrieval only if evaluated useful.
  - [ ] Implement provider adapter, structured cited drafts, abstention and citation validation.
  - [ ] Test prompt injection, unsupported claims, empty evidence, provider outage and budget limits.
- **Dependencies:** approved corpus/provider access and evaluation references; Week 1 evidence permissions; Week 2 traces.
- **Deliverables:** regulatory retrieval service and one assistant workflow behind human review.
- **Acceptance:** every citation resolves to allowed stored evidence; absent evidence causes abstention; generated output cannot authorize closure/filing; record model/prompt/retrieval versions, latency and cost without sensitive logs.
- **Risks / mitigation:** stale/wrong-scope guidance → version filters; fabricated citations → deterministic validation; absent credentials → explicit unavailable status, no simulated answers.

## Week 4 — Analyst workbench and security

- **Objective:** complete case handling with auditable human control.
- **Tasks:**
  - [x] Implement backend assignment/reassignment, case authorization and optimistic concurrency (completed in Phase 1).
  - [x] Phase 2.9: case/session workbench and immutable assessment history with real browser/API/worker acceptance.
  - [ ] Evidence inspection, notes, human review history and assignment editor.
  - [ ] Implement approval-gated consequential transitions and report/export authorization.
  - [ ] Add actor-attributed audit events in the same transaction as state changes.
  - [ ] Restrict runtime database privileges; establish migrations versus application roles.
  - [ ] Add access-control, export, abuse and data-leakage regression tests; perform browser acceptance.
- **Dependencies:** accepted case states/roles/approval policy; previous service interfaces.
- **Deliverables:** analyst workspace, approval workflow, controlled reporting and security evidence.
- **Acceptance:** two reviewers cannot silently overwrite each other; stale/retried requests are safe; role changes take effect; state survives restart; denied access cannot reveal evidence; original private/browser state is never imported.
- **Risks / mitigation:** UI-only controls → server tests; decision/label conflation → separate entities and permissions; scope growth → prioritize one complete case workflow.

## Week 5 — Evaluation and deployment

- **Objective:** deliver a tested demonstration with reproducible operational evidence.
- **Tasks:**
  - [ ] Run end-to-end synthetic acceptance and restart/retry/outage exercises.
  - [ ] Measure latency/throughput/queue age and bounded resource use.
  - [ ] Compare saved baseline behavior; distinguish historical replay from new evaluation.
  - [ ] Validate TLS deployment, backup restoration, migrations, rollback and secret rotation.
  - [ ] Complete dependency/security checks, documentation and final demo.
- **Dependencies:** approved hosting/data boundary, accepted previous deliverables; representative labels required for any new generalization claim.
- **Deliverables:** deployment/runbook, evaluation report, release evidence and controlled demo.
- **Acceptance:** clean install/build/tests; protected deployed endpoints; successful recovery test; documented limitations; no certification/real-world performance claims unsupported by evidence.
- **Risks / mitigation:** late infrastructure issues → rehearsed Compose baseline; biased feedback → reviewed labels and no automatic retraining; external-data delays → synthetic demo with explicit limitations.

## Final demo checklist

- [ ] Fresh setup and real database readiness.
- [ ] Login; server rejects unauthorized action.
- [ ] Synthetic alert ingestion and safe retry.
- [ ] Exact model/policy version, validated score, frozen route and failure fallback.
- [ ] Verified model explanation and separate routing trace.
- [ ] Source-cited retrieval/draft; abstention on missing evidence.
- [ ] Human review/approval, audit trail and authorized report.
- [ ] Restart persistence, backup/restore and rollback evidence.
- [ ] No secrets/private assets in Git; rights and remaining blockers disclosed.
