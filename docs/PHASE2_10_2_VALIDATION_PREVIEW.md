# Phase 2.10.2 - Column mapping and validation preview

## Scope and verified sources

- Starts from `5f64709`, branch `codex/project-initialization`. Pre-existing README, logo/theme, publication-logo allowlist and Compose tmpfs edits remain separate and uncommitted.
- Reuses `backend/app/schemas/alerts.py` unchanged: `AlertIngestionInput` metadata (`source_id`, `data_classification`, `feature_contract_version`) plus all 27 `AlertFeatures` fields in their original order. No research-only columns or targets enter predictors.
- Reuses `CSVStagingService.validation_source`: current active admin, owner scope, private regular file, expiry and full SHA/size verification inside one transaction. `open_for_validation` retains its stream-only interface.
- No canonical alerts/cases/jobs, imports, model work, frontend or export. A valid preview is not import approval, malware clearance, provenance certification or proof of criminal conduct.

## Protected HTTP contracts

All routes below are under `/api/v1/batch-uploads/{upload_id}` and require the existing bearer admin permission and upload ownership. Foreign/missing uploads and cross-upload validation IDs return the same 404.

| Method / suffix | Request | Response |
|---|---|---|
| GET `/columns` | No file/path parameters | Owned headers, required 30 targets, exact matches, upload ID/SHA and units convention; never row values |
| POST `/validations` | JSON mapping request below, existing 64-KiB body cap | 201 new mapping/preview; 200 identical effective mapping/file/version replay; `Location` points to summary |
| GET `/validations/{validation_id}` | Bound upload + validation IDs | Versioned mapping, verified identities, counts, creation/expiry times; no cells/source IDs |
| GET `/validations/{validation_id}/errors` | `offset=0..10000`, `limit=1..100` (default 50), `severity=all|error|warning` | Total matching diagnostic rows, pagination and bounded field/code lists |

```json
{"mapping_version":"trueflag.csv-mapping.v1","units":"baseline_source_units","mapping":null}
```

- Null/omitted `mapping` means exact, case-sensitive column names for all 30 targets. Explicit `mapping` is **canonical target -> staged header** and must contain every target once, reference existing exact names and use each source column once. Partial maps, unknown targets, missing sources, ambiguous reuse, duplicate JSON keys and unsupported versions/units are rejected; no alias guessing, case folding, trimming, default values or imputation.
- Example explicit entry: `"income":"Annual Income"`, as one entry of a complete 30-target mapping. Header names retain staging's bounded ASCII syntax. Additional unmapped columns are never imported; nonempty unmapped cells yield a value-free warning.
- Summary: `validation_id`, `upload_id`, sequential upload-scoped `version`, mapping/validator/CSV/feature-contract versions, feature-contract SHA, upload SHA, mapping SHA, mapping, units, `total_rows`, `valid_rows`, `invalid_rows`, `warning_rows`, `created_at`, `expires_at`.
- Diagnostic shape: `{"row_number":3,"errors":[{"field":"income","code":"number_format"}],"warnings":[]}`. Row numbers are **logical CSV record numbers including header = 1**, not physical newline offsets. Counts cover the entire file; `warning_rows` may overlap valid or invalid rows. Pagination total counts rows with matching diagnostics, not individual field failures.

| Status | Meaning |
|---|---|
| 401 / 403 / 404 | Authentication / current admin permission / concealed resource mismatch |
| 410 | Upload expired; preview is no longer accessible, even if retained receipts remain |
| 413 / 415 / 422 | Resource/body limit / unsupported request media / invalid mapping, syntax or request |
| 429 | Per-process validation slots or per-upload version quota exhausted; bounded Retry-After |
| 503 | Storage integrity/access, database or cooperative validation deadline failure; no partial preview published |

## Exact conversion and domain decisions

| Input | Implemented behavior |
|---|---|
| Numeric cells | Strict JSON number grammar, max 512 characters; no whitespace, grouping, currency symbols, booleans, NaN/infinity or missing tokens. Reject nonfinite results and nonzero float underflow. Ordinary JSON float representation is retained |
| Income | Only an exactly empty cell becomes `None`; `0`, `0.0` and `-0.0` remain observed numeric zeros |
| Other missing fields | Missing required columns reject mapping; empty numeric cells fail row validation. No feature is invented |
| KYC | Existing whole-valued finite 0..6 validator; `3.0` valid, `3.1` invalid |
| State | Existing nonblank string of length 1..128; unknown categories and case remain unchanged. No invented state whitelist |
| Other numeric predictors | Original finite int/float rules; no new nonnegative/integer/binary-only constraints derived from field names |
| Metadata | Original source-ID regex/length, exact `synthetic` classification and exact feature-contract literal |
| Units | Required `baseline_source_units` declaration; alternative declared scales/currencies rejected. No conversion. Source currency/score scale is not exhaustively documented and cannot be verified from numeric cells alone; this is an explicit operator assertion, not inferred physical-unit verification |
| Duplicate source IDs | Later occurrences in this file are invalid (`duplicate_source_id`); first occurrence is checked normally. No existing-alert conflict or database reservation is claimed; import must handle those |
| Formula/markup cells | Never executed or echoed. Formula-like mapped text yields `spreadsheet_formula` warning; invalid numeric formula text still fails. Future spreadsheet export requires separate escaping |

Error codes: `number_format`, `contract_value`, `column_count`, `duplicate_source_id`. Warning codes: `spreadsheet_formula`, `unmapped_columns`. Error bodies never contain Pydantic input/context, user cell values, raw exceptions or filesystem paths.

## Persistence, concurrency and limits

- Migration `0009_csv_validation` adds `csv_validations` and `csv_validation_issues` (**18 domain tables**). Mapping identity hashes bind complete mapping, units, upload digest, CSV/feature contract identities, mapping version and validator version (`trueflag.csv-validation.v1`). Effective identical maps replay regardless of JSON key ordering or exact versus explicit selection.
- Parent records store mapping/version/provenance and counts, child records only logical row numbers and canonical field/code lists. No cells or duplicate sensitive snapshots are stored. Mapping/header labels are owner-visible metadata, never copied to audit/log payloads.
- Existing actor lock serializes authorization, version allocation and replay; database uniqueness on upload/mapping hash and upload/version prevents duplicates. Mapping/result records are append-only through the service/API; no database-wide immutable/tamper-proof guarantee is claimed. Future import must reverify bytes, identity, permissions and preview currency, not blindly trust a historical row count.
- A single PostgreSQL transaction commits mapping, all diagnostics and completion audit, or rolls them all back. Replay and reads have separate value-free audits. Permission changes serialize with the held actor row lock; revocation committed before processing/retrieval denies access. No claim of interrupting a transaction already authorized before a concurrent revocation.
- Streaming CSV reader, at most 100 pending diagnostic rows per database insert and at most one SHA digest per source ID in memory. Default staging caps remain 1 MiB / 2000 rows / 64 columns / 16 KiB per cell; absolute configured ceilings remain 8 MiB / 10000 rows / 128 columns.
- `CSV_MAX_VALIDATION_VERSIONS=5` per upload (1..20); matching replay bypasses this quota. `CSV_MAX_CONCURRENT_VALIDATIONS=2` per API process (1..8), shared by preview and protected reads. `CSV_VALIDATION_TIMEOUT_SECONDS=10` (1..30) is a cooperative per-record budget, alongside existing 2-second SQL lock / 5-second statement limits; it is not a hard thread kill. Cross-replica admission/rate quotas and production load acceptance remain pending.
- Original file is read-only and unchanged. Existing TTL/private-volume/DACL/no-follow/orphan controls remain. Expiry denies previews; metadata/diagnostic receipts remain for audit, subject to future institutional metadata-retention policy. Malware scanning and application-level encryption-at-rest remain unimplemented; an accepted CSV is **unscanned**, not declared safe.

## Verification and stop boundary

- `backend/tests/test_csv_validation.py`: synthetic mapping, metadata/predictor compatibility, null/zero, unknown category, units, duplicate-key/source mapping, full-file counts, logical/multiline row numbering, pagination, formula warnings, owner/role/revocation/expiry, tamper/malformed/size/deadline/quota handling, partial-write rollback and PostgreSQL concurrency/audit rollback.
- Run existing `scripts/run_assessment_verification.py --full-backend` for Linux/PostgreSQL and `scripts/run_ml_verification.py --check tests|scoring|policy|shap` for actual pinned scientific checks. Native Windows SHAP limitation is unchanged. Actual acceptance counts appear in [implementation status](IMPLEMENTATION_STATUS.md).
- Next, only after a new request: **2.10.3 Durable Chunked Idempotent Alert/Case Import**. Import approval, conflict handling, checkpoint/recovery and canonical ingestion are not implemented here.
