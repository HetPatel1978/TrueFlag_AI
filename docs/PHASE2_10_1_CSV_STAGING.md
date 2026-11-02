# Phase 2.10.1 - Contract and secure CSV staging

## API contract

All routes require the current active admin via `require_batch_uploader`. Uploads and reads are owner-scoped even between administrators. The existing case/supervisor scope does not grant access to another uploader's file. No raw-file download route exists.

| Route | Result |
|---|---|
| `GET /api/v1/batch-uploads/contract` | Versioned target format, exact generated metadata/predictor definitions and missing-value rules |
| `GET /api/v1/batch-uploads/template` | UTF-8 header-only CSV; fixed attachment name `trueflag-alerts-v1.csv` |
| `POST /api/v1/batch-uploads` | Raw CSV body; new receipt `201`, matching retry `200`, canonical `Location` |
| `GET /api/v1/batch-uploads/{upload_id}` | Minimal owned metadata; concealed/missing `404`; expired receipt reports `expired` |

Upload headers:

- Required `Content-Type: text/csv` (optional `charset=utf-8`, including quoted UTF-8).
- Required `Idempotency-Key`: 16-128 ASCII alphanumeric / underscore / period / colon / hyphen characters.
- No multipart, compression, filename/path query parameters, `Content-Disposition` or `X-Upload-Filename`. Storage names are exclusively generated UUID keys.
- Response/error bodies never echo file contents, headers, original filenames, actor identifiers, tokens, storage paths or stack traces. Error envelope remains `{"detail":"fixed sanitized message"}`.

Example transport (token supplied privately by the existing authentication flow, never put into source or logs):

```http
POST /api/v1/batch-uploads
Authorization: Bearer <current-admin-token>
Idempotency-Key: synthetic-upload-intent-0001
Content-Type: text/csv; charset=utf-8

source_id,data_classification,feature_contract_version,kycRiskScore,income,...
```

The abbreviated header above is illustrative; download the actual complete template. A successful response contains only `upload_id`, `status`, `size_bytes`, logical `row_count`, `column_count`, server-computed `sha256`, `created_at`, `expires_at`, `csv_contract_version`, `feature_contract_version`, `template_url` and `contract_url`. References describe the target contract, not validated file-row content. All responses are no-store.

| Error | Meaning |
|---|---|
| 401 / 403 | Missing/inactive/invalid credentials / current role lacks staging permission or was revoked during upload |
| 404 | Upload hidden or missing |
| 408 | Streaming interrupted or exceeded 60 seconds |
| 409 | Same actor/key with different bytes or contract intent, including malformed replacement content |
| 410 | Matching historical upload expired; a new intent needs a new key |
| 413 | Byte, row, column or cell limit exceeded |
| 415 | Non-CSV media type, unsupported declared charset or compression |
| 422 | Invalid UTF-8, CSV syntax/header, no data records, invalid key or filename/path parameters |
| 429 | Ten active uploads per actor, or four concurrent streams per API process; retry hints 60 / 5 seconds |
| 503 | Database/private storage unavailable; retry the same key |

## Exact canonical target

- CSV version: `trueflag.alert-csv.v1`; predictor contract: `datarobot_provisional_v1` and existing SHA `97ec1a8c39bb368621609ea66d1a652179dee8a1c910bc7c14c1b3ff81f72747`.
- The 30 template columns are generated from three `AlertIngestionInput` metadata fields plus all 27 ordered `AlertFeatures.model_fields` (`backend/app/schemas/csv_uploads.py`). Metadata is never passed as an RF predictor.
- Required metadata per row, to be validated in 2.10.2: `source_id`, `data_classification` (exactly `synthetic`), `feature_contract_version` (exactly the existing version). Source ID remains a required 1-128-character ASCII identity starting alphanumeric and continuing alphanumeric/underscore/period/colon/hyphen. No generated source IDs, source-ID overwrites or file-digest-as-alert-ID rules are added.
- `state` is a required nonblank recorded string, max 128 characters; preserve original case and unknown categories for the fitted encoder. Other predictors are required finite JSON-compatible numbers; `income` alone is required-but-nullable. `kycRiskScore` must be whole-valued 0 through 6. The real contract does not enforce invented transaction counts, integer-only PEP flags or nonnegative ranges beyond its existing validators.
- Controlled missing value: an empty **income** cell will map to JSON null in 2.10.2; `0` remains numeric zero. Empty other predictors, `NA`, `N/A`, `null`, `NaN`, infinity, booleans, currency symbols or implicit category normalization are not approved coercions. No predictor parser/mapping is implemented in this subphase.

## Staging restrictions and limits

| Setting | Default / hard configurable range |
|---|---|
| `CSV_MAX_BYTES` | 1048576 (1 MiB) / 1024-8388608 |
| `CSV_MAX_ROWS` | 2000 / 1-10000 logical records after header |
| `CSV_MAX_COLUMNS` | 64 / 30-128 maximum; staging may accept fewer columns for later mapping |
| `CSV_MAX_FIELD_BYTES` | 16384 UTF-8 bytes / 128-65536 |
| `CSV_RETENTION_SECONDS` | 86400 / 300-604800 |
| `CSV_MAX_ACTIVE_UPLOADS` | 10 per actor / 1-100 |
| `CSV_MAX_CONCURRENT_UPLOADS` | 4 per API process / 1-16 |
| `CSV_CLEANUP_INTERVAL_SECONDS` | 300 / 30-3600 |
| `CSV_STAGING_ROOT` | Host `runtime/csv-staging`; API image `/app/runtime/csv-staging` on private Compose volume |

- UTF-8 only; an initial BOM is permitted and included in the stored-byte digest. Comma delimiter, double-quote escaping, CRLF/LF and quoted multiline cells are supported. Python's strict CSV reader is used without changing process-global parser limits.
- Nonempty unique headers: ASCII letter first, then letters/digits/spaces/underscore/period/hyphen, max 80 characters. No leading/trailing whitespace, duplicates ignoring case, multiline/empty/formula-like headers. Names/values are not normalized.
- NUL/unsupported control characters and malformed quoted CSV are rejected. Each logical record counts toward the row bound, including blank records; header-only or blank-line-only content is rejected. Variable record widths and invalid predictor values may still stage: the full mapping/row-value preview belongs to 2.10.2.
- Formula-like cells and markup are inert data, never executed, evaluated, deserialized or reflected into HTML. Future spreadsheet export must escape formula-capable cells; that export does not exist now.
- API receives chunks into a private spool with a byte counter and SHA-256, not an unbounded in-memory body. Only this exact POST path skips the existing generic 64-KiB JSON buffering. Header byte claims do not bypass the counter; interrupted/rejected streams remove partial files.
- Existing Nginx default body cap is 1 MiB. Operators increasing the API cap must separately review proxy limits; no frontend/proxy change is made here. Multi-replica global temporary-storage/ingress quotas are not claimed.

## Persistence, access and recovery

- Migration `0008_csv_staging` adds **one table** (`csv_uploads`), bringing domain tables to **16**. Metadata stores actor, intent-key hash, status, sizes/counts, trusted SHA, generated private reference, target versions, timestamps and creation-audit link. Neither raw features, CSV headers nor original filenames are copied into PostgreSQL metadata.
- `batch.upload.staged` audit commits with the receipt; it contains only upload identity, bounded sizes/counts and contract version. Metadata reads and expiry have separate safe audit events. No alerts, cases, model scores or ML jobs are created by staging.
- Short actor row locks recheck current admin status, serialize same-actor publication and quota checks, and fence revocation. Database uniqueness on `(actor_id,key_sha256)` remains authoritative. Different actors/keys can intentionally stage identical bytes.
- New content is structurally checked, fsynced and atomically renamed inside the receipt transaction. Definite pre-commit failure rolls back audit/metadata and removes new bytes. A lost COMMIT acknowledgement retains bytes because the receipt might be durable; same-key retry recovers the committed result without duplication.
- Filesystem/database operations are **not a distributed atomic transaction**. Bounded reconciliation handles process-crash and uncertain-commit orphans after one hour, only for generated UUID filenames with no database reference. Active/new partial files and unrelated operator files are untouched. Directory scanning resumes across bounded passes to avoid starvation.
- Expiry is enforced immediately on protected reads/internal consumption. Lazy read cleanup and a backend retention thread remove expired bytes; metadata receipts/audit remain for idempotency/provenance. Each pass handles at most 100 expired receipts and 100 directory entries. DB or filesystem failures can delay physical removal but cannot authorize expired content. Production cleanup alerts/independent audit retention remain deployment work.
- Linux root mode 0700, file mode 0600; native Windows uses a protected DACL allowing the service user and SYSTEM without requesting SACL/security privileges. Reject configured public/static/build/source locations, traversal references, symlinks and nonregular files. Storage keys are never accepted from clients or returned by HTTP.
- Private Compose volume is owned by API UID 10001 and survives container replacement; the worker/frontend do not mount it. Staging paths are ignored by Git, and backend build context excludes `runtime`. No upload bytes belong in images, test reports or publication candidates.
- Service-only `CSVStagingService.open_for_validation(actor_id, upload_id)` rechecks owner/current role/expiry, opens a no-follow regular file and recomputes size/SHA before yielding a bounded read-only binary stream. The future mapper reads headers/rows there; it gets no caller-supplied filesystem path. Keep the context short; no model work while its authorization transaction is open.
- No malware scanner or application-level encryption-at-rest is implemented. CSV-only parsing, no execution, private quarantine, privilege checks, caps and TTL are compensating controls. Enterprise storage/AV/backup/key-management and least-privilege SQL roles remain explicit gaps.

## Verification

```powershell
.\.venv\Scripts\python.exe -B scripts/run_assessment_verification.py --full-backend
.\.venv\Scripts\python.exe -B scripts/run_ml_verification.py --check tests
.\.venv\Scripts\python.exe -B scripts/run_ml_verification.py --check policy
.\.venv\Scripts\python.exe -B scripts/run_ml_verification.py --check shap
.\.venv\Scripts\python.exe -B -m alembic -c backend/alembic.ini upgrade head
.\.venv\Scripts\python.exe -B -m alembic -c backend/alembic.ini check
.\.venv\Scripts\python.exe -B scripts/verify_postgres.py
.\.venv\Scripts\python.exe -B scripts/check_publication.py
```

New synthetic tests: `backend/tests/test_csv_staging.py`. Cover exact generated template, private receipt/digest/permissions, owner/admin scope, revocation, size/encoding/header/media restrictions, inert formula cells, duplicate/conflicting/concurrent requests, publication and audit failures, uncertain successful/failed commits, disconnect cleanup, bounded expiry/orphan recovery, no public raw route, storage tampering and no canonical writes. Actual final counts and regression parity are in [implementation status](IMPLEMENTATION_STATUS.md).

## Stop boundary

This document records the 2.10.1 boundary. Phase 2.10.2 is now implemented separately: see [mapping and validation preview](PHASE2_10_2_VALIDATION_PREVIEW.md). Next is 2.10.3 approved durable import, not implemented. No batch frontend, import, assessment dispatch or export is included.
