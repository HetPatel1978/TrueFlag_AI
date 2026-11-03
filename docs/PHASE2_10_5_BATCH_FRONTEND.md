# Phase 2.10.5 — Batch frontend and safe export

## Scope and reuse

- Starts from `4cb5a6f` on `codex/project-initialization`. Existing branding/startup edits remain separate. No teammate, model, predictor, policy, SHAP, job-state-machine or database-schema changes.
- Admin-only React Batch Processing consumes the existing 2.10.1–2.10.4 APIs. Authorization is enforced by PostgreSQL-backed services on every request; navigation visibility is not an access control.
- Only new backend capability: bounded CSV result export, reusing existing authorization, verified result projection, audit and shared request budget. No new queue, broker, UI library, inference implementation or endpoint for uploaded models.

## Workflow

| Step | Actual behavior |
|---|---|
| Upload | Raw authorized CSV upload with progress, stable uncertain-retry key, 1-MiB browser guard and existing server limits. Filename is not sent as metadata. Generated template is downloadable |
| Map | Exact-name defaults and explicit selectors for the server-generated 30-column contract: three metadata fields plus unchanged 27 predictors. All targets require distinct source columns; explicit baseline-unit assertion |
| Validate | Existing full-file validator; counts and paginated field/code diagnostics (20/page), without raw cells. Empty income remains missing, numeric zero observed zero |
| Approve | Separate explicit valid-row confirmation bound to the exact upload/mapping/version/units preview; existing durable import APIs |
| Import | Persisted counts, excluded/conflicting rows, bounded row receipts (10/page), case links, terminal failures and resume receipt |
| Assess | Separate explicit policy and Start Assessment action. No import-triggered scoring. Existing bounded dispatcher and Linux RF/policy/SHAP worker |
| Results | Authoritative persisted counters, retrying versus terminal manual review, paginated actual results, reusable SHAP component and case/history drill-down |
| Export | Explicit bounded range, fixed result-field allowlist, fresh server permissions and committed export audit |

- Routes: `#/batch`, `#/batch/upload/{id}`, `#/batch/upload/{id}/validation/{id}`, `#/batch/import/{id}`, `#/batch/import/{id}/assessment/{id}`. Invalid UUID/route combinations are rejected before API access.
- Resume with the saved import link/ID; no upload-list API was invented. A reload requires sign-in. The durable server receipts survive browser closure; in-memory uncertain request keys do not. Existing server intent/source/batch deduplication remains authoritative.
- Pending upload/approval/start keys and exact request content remain in session memory across view changes. Retries reuse them; a different file starts new upload intent. No raw feature values, scores, tokens or results are written to local/session storage.
- Sequential polls every five seconds, at most 60 iterations/five minutes; respect bounded 429 backoff. Navigation/logout abort requests and timers. Expiry, revocation, conflict, capacity, network and malformed-input errors use fixed messages. Manual refresh resumes observation, not a new import or assessment.
- Existing ten-second current-identity/scope checks and hidden-tab protection apply. Denied responses clear protected state. Revocation detection has polling/network delay, not instantaneous push guarantees.

## Export API

`GET /api/v1/batch-assessments/{batch_id}/export?offset=0&limit=500`

- Current active admin, batch ownership and **all member-case visibility** required. Individual assessments reuse the existing locked integrity/provenance projection. Unknown query fields rejected. Same persistent assessment API rate budget applies.
- Offset 0..10000. Default configured row cap 500 (maximum configuration 1000); default byte cap 1 MiB (maximum configuration 4 MiB). `BATCH_EXPORT_MAX_ROWS`, `BATCH_EXPORT_MAX_BYTES`. Above-cap requests return sanitized 413; no silent truncation. Use smaller ranges, including when an operator lowers the cap.
- Fixed fields: `case_id`, `source_row_number`, `outcome`, `policy`, `sar_positive_score`, `recommendation`, `override_reason`, `assessment_id`, `job_id`, `retrying`, `reason_code`, `model_version`, `model_sha256`, `policy_version`, `policy_sha256`, `human_decision_required`.
- UTF-8 BOM, quoted cells and CRLF. Prefix a single quote to formula prefixes `= + - @`, including whitespace/BOM-obscured prefixes, and leading tab/CR/LF. CSV quoting alone is insufficient. Failed/unprocessed rows contain no fabricated score.
- No source IDs, predictor cells, uploaded headers, SHAP payloads, private paths, credentials or operator-selected columns. Fixed generated attachment filename; `Cache-Control: no-store`; `X-Export-Total` and `X-Export-Rows` describe the selected range. Downloaded files remain the operator's retention responsibility.
- One short transaction checks access, builds one bounded range and writes `batch.assessment.exported` with actor/batch, range, count, bytes, schema, timestamp and SHA-256. Return bytes only after audit commit. Authorization/audit/DB/byte-limit failures release no CSV. No export contents in logs/audit.
- No migration: `0011_batch_assessments`, 24 domain tables. Existing batch audit immutability guards cover the new event prefix. This is an application audit, not independent tamper-proof evidence against a privileged SQL owner.

## Verification and limits

- Frontend component/API tests include mapping, explicit approvals, same-key retries, manual-review rendering, server-only exports, error statuses, raw-upload progress/cancellation, bounded polling and cleanup.
- Real Chromium acceptance uses isolated migrated PostgreSQL schemas and pinned Linux import/RF/SHAP workers. Synthetic-only cells; no fabricated model results. Exercises lost import acknowledgement, durable retry, missing/zero income, partial validation/import, real result/explanation/history, export, mobile/keyboard accessibility, worker downtime/failure and permission revocation.
- Export tests use actual PostgreSQL and actual Linux RF/SHAP where applicable; formula safety, field restrictions, audit digest, row/byte bounds, authorization/revocation and audit rollback. Actual executed counts and scientific parity are recorded in [implementation status](IMPLEMENTATION_STATUS.md).
- Reproduce: `python -B scripts/run_frontend_e2e.py`; `npm test`, `npm run build`, `npm run lint`, `npm run format:check` in `frontend`; `python -B scripts/run_assessment_verification.py --full-backend`; `scripts/run_ml_verification.py --check tests|scoring|policy|shap` (one choice per invocation). Use existing private assets and local PostgreSQL; no fixtures or credentials are committed.
- Uploaded files remain **unscanned**. No AV, production IAM/tenancy, retention, global perimeter quotas or production capacity certification is claimed. Model scores are not evidence of money laundering; human decisions remain separate.
- Stop after this subphase. **2.10.6 complete-workflow security/load/recovery acceptance** requires a new request. No Phase 3, LLM/RAG, training, automatic dismissal/closure/SAR action or push.
