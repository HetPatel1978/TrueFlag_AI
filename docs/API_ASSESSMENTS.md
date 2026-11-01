# Phase 2.7 - Secure assessment APIs

## Scope and permissions

- Explicit asynchronous requests against existing synthetic alerts; API processes do not load or invoke the RF/SHAP pipeline.
- Bearer JWT and current active DB role required on every endpoint. Analysts: currently assigned cases only. Supervisors/admins: existing single-workspace oversight, including unassigned cases. No team/tenant hierarchy is invented.
- Hidden/missing jobs, cases and case/assessment mismatches return the same `404` body. Role/assignment changes are rechecked during submission, computation, publication and retrieval; an old receipt is not an access token.
- Phase 2.9 React workbench consumes these protected APIs. No LLM/RAG, automatic enqueue, retraining, dismissal, closure or SAR action is implemented.

## Endpoints

| Endpoint | Success | Contract |
|---|---|---|
| `POST /api/v1/cases/{case_id}/assessments` | `202 Accepted` | Required `Idempotency-Key` and strict body below; returns job status, `Location` and `Retry-After: 2` |
| `GET /api/v1/assessment-jobs/{job_id}` | `200` | Current case-scoped job metadata/status, attempts, selected policy, optional assessment ID, allowlisted failure code/fallback; polling hint for Pending/Running |
| `GET /api/v1/cases/{case_id}/assessments` | `200` | `{items,total,limit,offset}`; summaries only, newest assessment version first |
| `GET /api/v1/cases/{case_id}/assessments/{assessment_id}` | `200` | Stored score, recommendation, policy trace, grouped verified SHAP and provenance |

All responses are `Cache-Control: no-store`; existing safe request correlation applies. CORS exposes `Location`, `Retry-After` and `X-Request-ID`. None of these routes accepts uploaded models or client-generated inference results.

| Request field | Required validation |
|---|---|
| expected_version | Strict JSON integer, 1-2147483647; current case version for a new run; booleans/floats rejected |
| run_id | UUID; stable for retries, new UUID for reassessment |
| policy | Exactly `Efficiency`, `Balanced` or `Coverage` |
| Idempotency-Key header | 8-128 ASCII characters; first alphanumeric, remaining alphanumeric/underscore/dot/colon/hyphen |

Extra body fields are forbidden, including features, model scores, actor/role, model identity and queue limits. Case/alert predictors always come from the validated persisted alert.

```json
{
  "expected_version": 2,
  "run_id": "11111111-1111-4111-8111-111111111111",
  "policy": "Coverage"
}
```

- Matching key/run/content returns the original job with `202`, including when it is already completed or Failed. It does not retry a terminal job; reassessment requires a new run/key and current case version.
- Conflicting run/key/policy/input content or stale/closed case for a new run returns `409`; no new job is created. Matching historical retries still require current access and unchanged source identity.
- Accepted means durably queued, not successfully scored. Worker downtime leaves jobs Pending; worker failures/recovery retain the existing bounded-attempt semantics.
- The immutable queued snapshot binds case/source state and input fingerprints. Original 27 predictor values remain in the ingested alert; there is no alert-edit API or duplicate feature payload in a job. Any queued-source change fails closed rather than silently scoring different input.

## Responses and provenance

| Response | Included / intentionally omitted |
|---|---|
| Job | Job/case/run IDs, lowercase state, attempts, selected policy, result ID, sanitized failure code, manual-review fallback and human-decision requirement. No lease/worker/token/receipt data |
| History summary | Assessment/case/alert/run IDs, versions, processing time, score, model version/SHA, selected policy/version/route and input/content fingerprints. No explanation payload or raw predictors |
| Detail | Summary plus transport/feature/hash contract, policy artifact SHA/threshold/priority/override/reason, 27 contributions with direction/missing flag, ranking/top features/base/residual, exact SHAP method, verification tolerances/runtime/artifact identities |

- History: `limit` 1-50 (default 20), `offset` 0-10000 (default 0); unknown query fields rejected. No arbitrary sort expression or client-selected projection.
- Detail exposes grouped 27-feature contributions; encoded 41-feature vectors, raw feature values, source IDs, internal idempotency digests, raw audit payloads and worker credentials are omitted.
- Stored content integrity is checked before response projection; malformed/corrupt internal records return sanitized `503`, not a partial explanation. Content SHA identifies the full internal immutable record; the redacted API payload alone cannot reconstruct that digest. It is not a signature against a privileged DB owner.
- Positive output is the frozen model's SAR-positive score, not calibrated criminal probability. SHAP is model attribution, not causality or evidence of crime. Model recommendations remain distinct from human case dispositions.

## Admission, throttling and errors

| Control | Implemented behavior |
|---|---|
| Per-user request budget | Persistent fixed window across API replicas and all four routes; defaults 120 requests/60 seconds. Debit after current-role authentication in its own transaction; hidden/missing resources, conflicts and service failures cannot roll back the budget |
| Exhausted budget | `429` plus positive `Retry-After`; matching retries also consume request budget. No client IP/role header can change the actor |
| Active queue capacity | Defaults 1000 Pending/Running jobs. All enqueue writers serialize capacity checks with the same queue-table-scoped PostgreSQL transaction advisory lock; matching receipts/completed results bypass new-capacity checks |
| Saturation / contention | `503` with retry hint; no accepted job or partial creation audit. Conflicting content remains `409`, not disguised as capacity failure |
| Worker failure | Status remains queryable; failure codes are allowlisted, terminal fallback is `manual_review`, `human_decision_required=true`; no fabricated score/explanation or human-case mutation |

Configuration: `ASSESSMENT_API_RATE_LIMIT`, `ASSESSMENT_API_WINDOW_SECONDS`, `ASSESSMENT_QUEUE_CAPACITY`; defaults and bounds are in `app/core/config.py` and `.env.example`. Keep capacity configuration consistent across enqueue producers/replicas. Queue locking assumes the existing PostgreSQL READ COMMITTED isolation. Readiness still checks database migration, not worker availability.

## Audit and implementation evidence

- New/replayed API requests write `assessment.job.requested` in the enqueue transaction; original creation still writes `assessment.job.enqueued`.
- Successful protected reads write `assessment.job.status_read`, `assessment.history_read` or `assessment.detail_read`. Response construction/validation and audit commit precede disclosure. Audit failure returns `503` and rolls back the operation; a separately committed request debit remains consumed.
- Request/read audits contain actor/resource IDs and bounded pagination metadata, not feature values or explanation contents. Job and new sensitive-read audit events reject UPDATE/DELETE through database triggers.
- Migration `0006_assessment_api`: one per-actor throttle table plus expanded read-audit guard; **14 domain tables**. No model/feature/scoring schema or immutable assessment record is rewritten.
- Files: `backend/app/api/assessments.py`, `schemas/assessments.py`, `services/assessment_api.py`; existing queue/persistence/authorization services reused. Scientific source, original model and teammate files remain unchanged.
- Acceptance includes real Linux/PostgreSQL/FastAPI/isolated-worker flows, including a real TCP/Uvicorn roundtrip, for all three policies with unseen synthetic inputs and both missing/zero income; in-flight assignment revocation prevents result publication. HTTP/concurrency/capacity/rate/audit tests use explicitly synthetic producers; they are not substitutes for the real-model tests.
- Reproduce: `python -B scripts/run_assessment_verification.py --full-backend`; full reference replays use `scripts/run_ml_verification.py --check policy` and `--check shap`. Actual final counts are in [implementation status](IMPLEMENTATION_STATUS.md).

## Remaining scope

The workbench and bounded internal operational metrics are implemented. Notification, cancellation API, bulk assessment, production SLO/HA, automatic archival, enterprise identity/SQL roles and regulatory production acceptance remain pending. Native Windows SHAP remains blocked; scientific execution uses Linux. A new request is required before later subphases.

## Operational monitoring

Admin-only `GET /api/v1/internal/metrics?minutes=15` exposes bounded aggregate API/job/worker/stage metrics. It does not return case contents or replace these case-scoped result endpoints. See [operational contract and benchmark](PHASE2_8_OPERATIONS.md).

## React consumer

See [Phase 2.9](PHASE2_9_FRONTEND.md): explicit 202 workflow, session-scoped run/key retries, bounded cancellable polling and immutable history/verified result display. No client feature values or model-generated scores are submitted.
