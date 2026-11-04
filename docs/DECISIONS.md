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

## ADR-021 — Phase 2.4 verified, authorization-gated SHAP

- Preserve exact TreeSHAP 0.51.0/path-dependent/raw settings, complete fitted preprocessing and SAR-positive probability space. Group 41 encoded values into 27 predictors without residual repair; ranking is descriptive, without causal/criminal inference.
- Require a trusted host authorization callback before feature access and again before disclosure. No default permit-all, client role/path/model control or HTTP endpoint; future server integration must bind current case scope.
- Independently validate the strict input snapshot, model/contract/method identity, fitted-root base, mapping, score, aggregation and reconstruction. Return verified payloads only; failures expose no partial contributions, raw feature values or exception messages.
- Preserve original lexical provenance separately from new rational input hashes. Pin the three historical explanation references, compare all 4000 numeric allocations, and retain old UI/policy context without installing it as current policy or browser state.
- Use a verification-only non-root, read-only, offline Linux container because host Application Control blocks the pinned llvmlite DLL. Do not weaken the host policy or substitute dependencies. Baseline RF fits remain zero; the independent algorithm unit test fits only a synthetic two-feature toy tree.

## ADR-022 - Phase 2.5 assessment persistence (2026-11-01)

- Add two tables: immutable `assessments` and `assessment_explanations`; reuse existing score, decision and audit tables. Preserve legacy routes while storing explicit recommendations for new assessments.
- Use trusted internal orchestration instead of arbitrary result submission. Permit current assigned analysts and workspace managers; no HTTP inference endpoint or automatic ingestion hook is added.
- Compute outside write transactions. Recheck actor, case/alert state and input/source identity under PostgreSQL locks before one atomic score/decision/explanation/audit/assessment commit.
- Actor-scoped hashed keys and global unique run IDs identify retries; conflicts reject, matching authorized retries reuse the original result. Serialize append-only version allocation per case.
- Retain feature references/fingerprints, not duplicate values. Persist model/contract/source/runtime/policy/method provenance, explicit override trace and checked content digest.
- Enforce immutability with database triggers, including linked children and TRUNCATE protection. Refuse history-destroying downgrade. Owner bypass, independent retention and runtime role separation remain deployment limits.
- Failure leaves no completed assessment or partial writes; durable failed attempts, jobs, bounded workers and HTTP integration require a later request. No changes to human case state, model, teammate sources or private references.

## ADR-023 - Durable assessment jobs (2026-11-01)

- Use PostgreSQL as the durable queue; no separate broker/outbox is needed for this single-database internal handoff.
- Separate worker service credentials from human identities. Execution rechecks the current requesting principal and case state; no worker HTTP interface is added.
- SKIP LOCKED claim, DB-clock renewable leases, rotating fencing tokens, three attempts and durable 5/10-second retry backoff. At-least-once computation, unique immutable assessment publication.
- Isolate each scientific run in a Linux subprocess with independent wall-clock watchdog, parent-death cleanup and bounded resource/JSON IPC. Keep existing RF/policy/SHAP behavior unchanged.
- Extract the unchanged Phase 2.5 write body into a caller-owned transaction so job success, assessment/explanation and both audit events commit together. No partial success or automatic human-case action.
- Optional Compose worker, explicit operator provisioning and no default/automatic enqueue. HTTP contracts, admission quotas, retention, metrics and production privilege separation remain later scope.

## ADR-024 - Secure asynchronous assessment APIs (2026-11-01)

- Expose explicit POST request, job status, bounded history and verified detail APIs. Request body contains only current case version, stable run UUID and frozen policy; model input remains the bound persisted alert.
- Keep existing assigned-analyst/workspace-manager scope. Reauthorize every lookup and bind case/result IDs; no broad job enumeration or arbitrary model submission endpoint.
- Always acknowledge matching/new durable requests with 202 and canonical Location, including historical job replay. Separate shared API abuse budget from enqueue transaction so failures do not undo throttling.
- Use one PostgreSQL advisory admission lock and active-job count instead of introducing a broker. Matching receipts bypass capacity; all authenticated API calls consume per-user request budget.
- Project stored immutable results through explicit schemas: summaries for history, grouped 27-feature SHAP for detail, model/input/policy/method verification provenance. Raw predictors/encoded vectors/worker secrets/receipt internals are omitted.
- Audit new/replayed requests atomically with enqueue; validate output and commit protected sensitive-read audits before disclosure. Existing RF, SHAP, policy and worker decision semantics remain unchanged.
- No frontend, automatic enqueue, LLM/RAG or consequential human-case action. Operational monitoring/load/retention and enterprise deployment gates remain separate scope.

## ADR-025 - Bounded operations monitoring (2026-11-01)

- Reuse PostgreSQL and existing API/worker processes: one operational rollup table, no mandatory telemetry/broker/dashboard service.
- Fixed-label streaming histograms and cumulative idempotent minute snapshots. Exact benchmark quantiles are distinct from conservative operational histogram upper bounds.
- Separate best-effort numeric telemetry from authoritative queue/audit state and domain commits. Dedicated export connections/timeouts and bounded buffering prevent monitoring from becoming a decision/persistence prerequisite.
- Observe existing RF/SHAP service envelopes without changing scientific behavior or immutable assessment content; numeric timing metadata travels separately over existing JSON IPC.
- Restrict metrics to current active admins; sanitize all metric/log fields. Per-request/attempt/exporter correlation contains no business or customer identity.
- Record one capped local synthetic run with real TCP/Linux/PG and injected failures; do not infer production capacity/SLO. Next phase requires new authorization.

## ADR-026 - Thin authorized risk workbench (2026-11-01)

- Reuse React, existing auth and asynchronous assessment contracts; hash navigation and no additional production runtime dependencies.
- Add only scoped safe overview/list metadata and literal server-side filters needed by the screens; preserve existing detail/assignment contracts and avoid predictor-bearing browser calls.
- Keep sessions and uncertain submission receipts in memory. Stable run/key retries, cancellable bounded polling and fresh server authorization; no client-supplied scores or decision authority.
- Display verified grouped attribution with signed text and model/provenance history. Recommendations stay separate from human dispositions; no automatic case action or new approval workflow.
- Validate real Chromium plus pinned Linux/PostgreSQL/ML flow and exercised accessibility states; do not equate UI completion with enterprise deployment certification.

## Decisions still required

- Institution/jurisdiction and corpus source-use permissions.
- External LLM provider and allowed data boundary.
- Approval matrix and permitted review/filing transitions beyond the implemented case-read/assignment role matrix.
- Hosting/TLS/identity strategy and performance envelope.
- Publication rights for teammate code and eventual repository license.

## Upstream engineering references

See TECH_STACK for framework documentation. Guidance informs implementation choices; it does not certify AML compliance or establish actual-data access rights.

## Phase 2.10.5 ? reuse existing batch APIs; add only bounded result export

- Use existing React session/API/SHAP/history foundations and current admin-only bulk permission. Resume from owned import IDs/links; do not add a dataset browser or new roles. Keep import approval and ML Start Assessment separate.
- Preserve uncertain request content/key in memory; server idempotency remains authoritative. Poll sequentially with five-minute/60-read bound and cleanup; no extra push service.
- Export one explicit bounded range with fixed fields, current all-member permissions, existing verified projections and committed digest audit. Buffer within row/byte caps to avoid partially disclosed files when later permission/integrity/audit checks fail. Formula quoting/prefix defense on every field; no predictors/source IDs.
- No migration, scientific logic, extra worker or dependency upgrade. No unscanned-file safety claim; downloaded-file retention remains operational policy. Stop before 2.10.6/Phase 3.

## Phase 2.10.6 ? accept the existing architecture within measured local limits

- Execute the complete existing pipeline with real Linux/PostgreSQL workers; preserve all model/policy/SHAP/schema/runtime behavior. Add acceptance tools/tests and evidence only. Separate scientific reference parity, operational load and security/fault scenarios.
- Keep default ingress/import/export/rate limits. Measure 100 and 1000 synthetic rows with two actual workers and deliberate 20-job backpressure; reject 5000 at the 2000-row default. No quota inflation or invented production capacity/SLO.
- Fix a discovered test timing assumption with PostgreSQL-clock availability and bounded terminal-state polling, retaining exact count assertions. Production scheduler unchanged. Test actual RF/SHAP stage-boundary process loss before publication and real API/dispatcher/browser resume.
- Local Phase 2.10 acceptance **PASS**, subject to [matrix, measurements and residual gates](PHASE2_10_6_ACCEPTANCE.md). Keep cold per-record initialization unchanged; optimization needs separate evaluated scope. Malware scanning unavailable; no certification, later-phase implementation or push.

## Phase 3.1 proposals - review pending, not implementation approval

| Proposal | Recommendation | Reason / approval boundary |
|---|---|---|
| D3-01 | Independently generated new synthetic evidence; no invented historical backfill | Reuse documented 27-field dictionary and contract; approve event mapping/reconciliation and case linkage |
| D3-02 | One jurisdiction/entity type and explicit as-of context | Select reviewed official corpus; law, guidance, internal and RF routing policies remain distinct |
| D3-03 | PostgreSQL typed evidence, deterministic analytics and lexical retrieval first | Existing infrastructure; graph/vector/agent additions require measured benefit |
| D3-04 | Provider-neutral bounded coordinator and separate investigation execution budget | Keep pinned ML queue/runtime isolated; approve model/egress/retention/spend before any call |
| D3-05 | Independent deterministic verifier plus authorized human semantic review | Citations are not truth/legal applicability; no autonomous case or SAR actions |
| D3-06 | Append-only version provenance with revocable access and governed retention | Immutability does not require perpetual PII storage; statutory/hold periods require approval |
| D3-07 | Curated safe text initially; broader intake separately gated | No scanner exists; source authenticity/rights/parse quality remain explicit |

[Full design, tradeoffs, implementation gates and open decisions](PHASE3_1_INVESTIGATION_ARCHITECTURE.md). Phase 3.2 is not started. These proposal IDs are design references, not accepted runtime controls.

## Phase 3.2 accepted local synthetic implementation scope

- The Phase 3.2 request authorizes the minimum additive PostgreSQL evidence implementation following the frozen [schema/matrix/generator/rollback contract](PHASE3_2_EVIDENCE_FOUNDATION.md). This supersedes the earlier statement that Phase 3.2 had not started; other Phase 3.1 proposals remain proposals.
- Preserve the original 27-feature contract. Use 27 explicit versioned synthetic declarations and zero invented transaction equations. Keep the `nbrCollections3y` one-year/three-year dictionary conflict, baseline currency and codebooks unresolved. Missing mandatory support yields evidence-only fixtures, never fabricated inputs/orphan cases.
- Own/admin-only admission and mutation; explicit case/source access plus existing current-case scope for reads. One generated source binds through existing ingestion to one new case. No legacy backfill/shared entity-derived access/new public roles.
- Whole source snapshot releases retain immutable typed record versions and predecessors. Exact duplicates collapse; conflicting payloads require a new release. Revocation changes access/membership and atomic revisions/audit, never erases history.
- Use PostgreSQL locks, uniqueness, deferred completeness and existing audit/ingestion/worker interfaces. Keep evidence internal, resource bounded, synthetic and deterministic; no new infrastructure, public API, provider, RAG, graph or automatic case action.

## Phase 3.3 read-layer decisions

- Reuse PostgreSQL/auth/immutable assessments/audits; no additional schema or infrastructure. Six narrow case-authorized read routes, not public unrestricted tools.
- Freeze current authorized linked membership and one selected release/source in a signed, short-lived context. Never merge corrected snapshots or silently choose a newer assessment. Explicit model selection and changed-input warnings preserve model/source authority boundaries.
- Decimal calculations use explicit `[start,end)` windows/currency, gross observation or verified reversal-pair rules and reproducible parameters. No FX, ML predictor derivation or new AML risk score.
- Status, comparable KYC expectations, sampling metadata and curated documents are absent. Report unavailable/insufficient evidence rather than inventing facts. No corpus/provider/source rights approval inferred. [Implementation contract](PHASE3_3_RETRIEVAL_ANALYTICS.md).
