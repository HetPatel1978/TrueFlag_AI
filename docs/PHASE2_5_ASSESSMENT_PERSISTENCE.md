# Phase 2.5 - Immutable assessments and atomic audit

## Implemented scope

- Internal `AssessmentService` in `backend/app/services/assessments.py`; **no new HTTP endpoints**, ingestion hook, deployed worker or automatic consequential action.
- Reuses the SHA-verified RF loader, scorer, frozen policy engine, exact TreeSHAP service and independent explanation verifier. No model/teammate modifications or training.
- `assess(actor_id, case_id, expected_version, run_id, idempotency_key, policy)` returns `(assessment_dict, created)`; keyword arguments only. Actor UUID must come from the trusted server principal, never an unauthenticated request field.
- `get(actor_id, case_id, assessment_id)` and bounded `list(actor_id, case_id, limit=20, offset=0)` enforce current case scope. List limit 1-50; offset 0-100000; newest assessment version first.
- Assigned active analysts may assess/read their cases; active supervisors/admins have workspace scope. This is an **internal service permission**; future HTTP submission-role approval remains separate.

## Execution and consistency

1. Validate strict UUID/envelope types, positive expected version, allowlisted policy and bounded ASCII key. Boolean versions are rejected.
2. In a short transaction: lock the active actor `FOR SHARE`, the visible case `FOR UPDATE`, then alert `FOR SHARE`. Validate all 27 stored predictors, synthetic classification, transport contract and recomputed ingestion fingerprint. Capture input fingerprint and case state.
3. Check an authorized existing receipt before computing. Matching retry returns the original record without new score, explanation, audit or model work. A retry never bypasses current authorization or input/source integrity.
4. Release the transaction. Load approved artifacts; score and explain the snapshot; verify score, class, method, root base, grouping and reconstruction using Phase 2.4 logic. The explanation callback checks DB case access before/after explanation. Evaluate the selected frozen policy independently.
5. Revalidate the result envelope, provenance, policy, finite scores and both contribution sums. No arbitrary result-upload/submission interface exists.
6. Begin the write transaction; reacquire actor/case/alert locks. Reject changed assignment, case version/status/disposition, alert/source/contract/input, closed case or revoked role/access. Insert score, recommendation, explanation, audit and assessment together; commit once.
7. Case-row serialization allocates `max(version)+1`; unique constraints arbitrate run/key conflicts across cases/processes. A collision on the two receipt constraints permits one fresh transaction to identify the winner; unrelated DB errors remain unavailable failures.

Completed records only: failed inference/verification/write creates **no partial assessment**. Durable pending/running/failed jobs, leases, retries and failure history require a later subphase. A valid historical retry may return its original assessment after a case version/status change if the actor still has access and the input/source is unchanged; a new run must use the current version and cannot assess a closed case.

## Stored fields and integrity

| Location | Persisted content |
|---|---|
| Existing `model_scores` | Alert ID, approved model version/SHA, record-bound input fingerprint, processed score |
| Existing `decisions` | Score ID, exact policy version/mode, explicit recommendation route and reason; no human disposition |
| New `assessment_explanations` | Verified base/score, 41 encoded and 27 grouped contributions, missing flags, rankings, method and tolerances; no predictor values |
| New `assessments` | Case/alert/actor/run IDs; assessment and case versions; completed status; child IDs; key/request/input/content hashes; timestamp and provenance |
| Existing `audit_events` | `assessment.completed`, actual actor, case/run/assessment/version/content digest; atomically linked |
| Provenance | Case state, source-ID hash, synthetic contract/input identity, policy trace/override, runtime pins, approved artifact identities, producer schema and explicit human-decision requirement |

- No duplicate feature snapshot is stored. Immutable alert reference + ingestion fingerprint + separately named `trueflag.explanation-input.rational.v1` fingerprint bind the input; the latter includes case record identity. Missing income and numeric zero remain different. A future input revision requires its own retained source history; this subphase adds no alert-edit API.
- `content_sha256` covers identities, child data, timestamps and provenance; audit details independently bind that digest. Retrieval recomputes it and fails closed on mismatch. This is an integrity checksum, **not a cryptographic signature or protection against a DBA rewriting all records/digests**.
- PostgreSQL triggers reject UPDATE/DELETE of assessments/explanations and linked scores/decisions/audit events. Statement triggers reject TRUNCATE of all five protected tables. Unlinked legacy score/decision/audit rows retain their prior behavior.
- No case status, disposition, assignment, SAR label or filing state is changed. `review_reduction_candidate` stays a recommendation; legacy `retain`/`dismiss` values remain accepted for compatibility but are not written by this service.

## Schema and operational limits

- Migration `0004_assessments`, parent `0003_case_security`; adds two tables and widens the decision route/check constraint. See [schema](DATABASE_SCHEMA.md).
- Foreign keys require every completed assessment's score, decision, explanation and audit. Run ID and actor-scoped hashed key are unique; child links are unique; `(case_id, version)` is unique.
- PostgreSQL is acceptance/production target; SQLite triggers support disposable tests only. A downgrade refuses retained assessment history instead of deleting it.
- DB owner/superuser can disable triggers or drop schema; separate migration/runtime roles, external audit retention and signed provenance remain deployment work. No enterprise immutability certification is claimed.
- Case writes/reads serialize briefly on a case row. ML work holds no long DB transaction. Each run currently initializes its own scientific services; caching, performance acceptance, worker isolation, cancellation and hard timeouts remain pending.
- Errors are fixed service reason codes; no feature values, source IDs, raw keys, credentials, model paths or DB/model exception text are logged/returned. Explanations remain sensitive, permission-scoped model attributions, not causal claims or evidence of crime.

## Reproduction

```powershell
docker compose up -d db
.\.venv\Scripts\python.exe -B scripts/run_assessment_verification.py --build --full-backend
.\.venv\Scripts\python.exe -B scripts/run_ml_verification.py --check tests
.\.venv\Scripts\python.exe -B scripts/run_ml_verification.py --check scoring
.\.venv\Scripts\python.exe -B scripts/run_ml_verification.py --check policy
.\.venv\Scripts\python.exe -B scripts/run_ml_verification.py --check shap
```

- New Linux verification image combines the existing service and ML pins. It is **test-only**: no application/private assets/secrets are copied into the image, deployed or pushed.
- Runtime is non-root, read-only with capabilities dropped, no-new-privileges, bounded CPU/memory/PIDs and temporary storage; selected code/assets mount read-only. Its Compose network reaches local PostgreSQL; it is not the network-disabled standalone ML test container.
- Database credentials pass through stdin, not Docker argv/env or a mounted `.env`; only disposable generated PostgreSQL schemas hold test data and are removed afterward. Windows native SHAP stays blocked; no host policy change is made.
- Persistence unit tests use explicitly synthetic internal producers/configuration; actual Linux/PostgreSQL tests execute the approved RF and SHAP for both missing/zero income, authorized creation/retrieval, idempotent retry and reassessment. Synthetic producers are not claimed as real-model verification.

## Verification results

Final counts are recorded in [implementation status](IMPLEMENTATION_STATUS.md). Full RF replay: 4000/4000, maximum score error 0.0. Policy replay: 12000/12000 routes and traces, zero mismatches. SHAP replay: 4000/4000 verified, no unavailable/mismatches, exact reference encoded/grouped/base parity; maximum reconstruction residual `3.1086244689504383e-15` against `1e-6`, score/group tolerance `1e-12`, relative tolerance 0. All 87 missing and 22 zero-income reference records preserved.

## Next task - requires new authorization

Design/implement durable assessment jobs with bounded scientific execution, leases/retry/failure isolation and immutable completed-result linkage. HTTP submission/retrieval contracts and production deployment remain separate approvals; no later phase is started here.
