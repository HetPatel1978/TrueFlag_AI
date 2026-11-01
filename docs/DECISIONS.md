# Architecture decisions

| ID | Decision | Status / rationale |
|---|---|---|
| ADR-001 | New sibling repository cloned from the explicit TrueFlag_AI remote; work on `codex/project-initialization` | Executed; preserve teammate folder, private package and existing main/archive branches |
| ADR-002 | Target intelligent alert/investigation overlay; first deliver secure foundation | Five-week scope; streaming/graph/behavioral models are expansion |
| ADR-003 | Modular FastAPI service plus isolated RF worker | Avoid premature microservices and incompatible scientific/service dependencies |
| ADR-004 | API package `app`; retain serialized `trueflag` names privately | Resolve regular-package collision without renaming serialized classes |
| ADR-005 | PostgreSQL source of truth, explicit Alembic migrations | Preserve cases/evidence/scores/decisions/audit separately; no auto create_all in application startup |
| ADR-006 | Locally provisioned Argon2/JWT accounts for demonstration | No public registration/default admin; role from database; foundation abuse controls added in ADR-016; production identity remains deployment work |
| ADR-007 | Exact RF/preprocessing/policies stay immutable | No training/tuning or silent feature changes; replay is identity validation, not independent performance |
| ADR-008 | Teammate source remains ignored/local until redistribution rights clarified | No supplied license; copy only selected artifacts and references; never publish private data/models |
| ADR-009 | One provider-neutral investigation interface | Week 3 implementation; no mock endpoint, autonomous actions or mandatory multi-agent framework |
| ADR-010 | No automatic model learning from review actions | Reviewed outcomes, dataset curation and offline promotion require separate acceptance |
| ADR-011 | Containers publish loopback only | Local demonstration; no external deployment or certification claim |
| ADR-012 | Patched frontend tooling and minimatch 11 override | Initial dependency audit exposed vulnerable test/glob tooling; updated compatible lint/test versions and verified matcher override with lint, tests and build; remove override once upstream ranges are patched |
| ADR-013 | Host ports 8010 / 8088, configurable through .env | Port 8000 was already occupied; preserve the existing listener rather than stopping another project |

## ADR-014 — Single-alert ingestion (2026-10-31)

- Current server-verified admin role required; analysts cannot submit, and request actor/role fields are forbidden.
- Required idempotency key is hashed in a durable receipt; global source identity independently prevents duplicate cases under a changed key. Changed key/source content conflicts with 409.
- Alert, unassigned open case, creation audit and receipt commit atomically. Database constraints arbitrate concurrent writers; no process-local lock or score/dismissal side effect.
- Preserve the exact 27 predictor names and numeric/missingness semantics. The new transport version maps JSON null to missing income without imputation; no ML dependency or model is loaded.
- Reject invalid requests rather than persist untrusted raw payloads into a newly invented quarantine. Batch ingestion, assignment-aware reads and operational telemetry remain separate tasks.

## ADR-015 — Phase 1 case scope and assignment

- Single workspace: analysts see only assigned cases; supervisors/admins oversee all cases. Neither supervisor nor analyst gains existing admin-only ingestion/global-audit permissions.
- Apply active role and assignment predicates in SQL for detail, list and counts. Hidden/nonexistent cases share 404. Lists project metadata only; details allowlist the 27 predictors after authorization.
- Supervisors/admins may assign/reassign/unassign active analysts. Strict expected version required; stale/closed cases conflict. Even no-op assignment executes a version predicate. Mutation and actor-attributed change audit commit together.
- PostgreSQL shared locks protect manager/assignee eligibility during the transaction; compare-and-set updates arbitrate case races. No source label, case disposition, score or routing changes occur.

## ADR-016 — Foundation abuse controls and observability

- Persist fixed-window login limits per HMAC-protected transport client, shared across workers/restarts; count valid and failed attempts alike. Do not trust arbitrary forwarded headers or persist raw client addresses.
- Bound both declared and actual streamed body sizes (default 64 KiB), before parsing/DB work. Generate request IDs server-side; logs contain route name/method/status/error class, not body, query, credentials, customer values or exception text.
- This is local-demo protection, not distributed bot mitigation. Approved proxy identity forwarding, production identity, TLS, database least privilege and retention remain deployment gates.

## ADR-017 — Phase 2 acceptance boundary

- Preserve the exact RF artifact, preprocessing, contract and frozen policy values. Current API has no ML imports or assessment endpoint.
- Document trusted worker loading, input snapshots, recommendations, explanation verification and 4000-score/12000-route regression before implementation. Original UI-bound SHAP loaders require an explicit live-case adapter.
- A future below-threshold recommendation must not dismiss/close/hide a case automatically. Do not continue Phase 2 code until separately requested.

## ADR-018 — Phase 2.1 trusted RF loading

- Keep the loader in `backend/trueflag_ml`, invoked only in the separately pinned scientific environment. Reuse `app.schemas.alerts.AlertFeatures` with pinned Pydantic dependencies; import no API/settings/database modules.
- Pin five approved identities in reviewed application code: model, contract, package initialization and the two required research modules. Never accept caller-supplied hashes/filenames or trust an editable artifact-side manifest as an authority.
- Hash bounded immutable byte snapshots before executing source/deserializing the model. Load the exact verified bytes, including compatibility modules; keep `sys.path` unchanged and reject existing `trueflag` namespace collisions.
- Validate CPython 3.11/64-bit, exact required distribution versions, fitted guard/preprocessor/RF, class order, native missing-income behavior and the actual `state`+`kycRiskScore` encoder. Keep original code private; no source shim, training or inference API.
- Phase 2.1 acceptance uses the actual retained model. CI boundary tests may skip private-runtime tests; local scientific acceptance is required evidence and is recorded separately.

## ADR-019 — Phase 2.2 read-only scoring and regression

- Construct `RFScoringService` only through the approved loader; preserve original fitted preprocessing and RF parameters. Resolve positive class from verified `classes_`; label 1 represents the research SAR target. No classifier threshold or calibration is added.
- Bound requests to 1–1000 unique-ID records, reuse strict ingestion feature validation and return per-record processed/failed results. Reject ambiguous envelopes/duplicate IDs before prediction. Never fabricate a failure score or log customer inputs/exception text.
- Pin the saved predictions and cleaned evaluation-source hashes independently of artifact manifests. Align all 4000 records by ID, check source/reference label metadata, and reject duplicated/missing/mismatched IDs. Numeric acceptance is absolute 1e-12, relative 0; measured maximum error is 0.0.
- Keep only pure Python scoring in Phase 2.2. HTTP endpoints, workers, persistence, deterministic policy recommendations and SHAP remain separately authorized work. No retraining, automatic dismissal or case mutation.

## ADR-020 — Phase 2.3 frozen policy recommendations

- Verify the original policy artifact SHA and model binding before using thresholds; identify the policy set by original model version plus artifact SHA because upstream supplies no independent policy version field.
- Keep deterministic evaluation separate from RF inference. Accept trusted internal score results and KYC attributes; reject booleans/nonfinite/out-of-range scores, unsupported priorities, mismatched model identity and failed processing. Fail to manual review without successful-retention/dismissal credit.
- Preserve exact inclusive thresholds, Coverage's successful-High-only protection, original reason codes and override flags. Represent saved `Dismiss` as `review_reduction_candidate`; all outputs require human decision and never change case visibility/disposition.
- Align all 12000 traces by record ID and mode, compare routes plus audit fields and totals, and preserve reference files. Actual parity is zero route/audit mismatches and zero retained/dismissed total differences; RF code remains unchanged.

## Decisions still required

- Institution/jurisdiction and corpus source-use permissions.
- External LLM provider and allowed data boundary.
- Approval matrix and permitted review/filing transitions beyond the implemented case-read/assignment role matrix.
- Hosting/TLS/identity strategy and performance envelope.
- Publication rights for teammate code and eventual repository license.

## Upstream engineering references

See TECH_STACK for framework documentation. Guidance informs implementation choices; it does not certify AML compliance or establish actual-data access rights.
