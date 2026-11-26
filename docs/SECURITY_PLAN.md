# Security foundation and progressive controls

## Scoped Claude development test — 22 November 2026

- The owner withdrew the $20/$2.15 limits only for `development_no_spend_cap_v1`. This is default-off, synthetic-only, exact-input and new-approval-ID-bound; ordinary Claude/Luminal financial gates remain unchanged. Historical ledger rows are immutable; no reservation is required for the explicit development scope, while actual token usage/cost estimates remain recorded.
- One outstanding attempt under the existing provider-wide lock, one attempt per approval ID, no automatic paid retry, bounded tokens/body/deadline/subprocess and current case/source/clock/snapshot checks remain mandatory. No public endpoint accepts arbitrary development configuration.
- Flat wire v2 maps to the existing strict `AIProposal` and independent financial/reference verifier. Regulatory-grounded input is excluded from this scope; citation and governance services are unchanged. Bounded provider error detail is retained only in private development receipts with credential redaction, not public error responses.
- Probe-only candidate 0022 was restored/rehearsed and applied with history equality verified; the original demo and running local schema were not migrated. New exact request approval is pending, with no live dispatch or analyst activation. [Scope, tests and full review package](CLAUDE_DEVELOPMENT_UNBLOCK_2026_11_22.md).

## G5.3 candidate controls — 21 November 2026

- Immutable, actor/case/parent/manifest-bound regulatory context uses existing source/version/release/citation identities. Current permissions, grant revision, evidence revisions, 900-second expiry and clock epoch are checked at preparation, dispatch, completion and protected reads. Revoke/regrant cannot revive an old binding.
- Parent and evidence-only draft admission now share one PostgreSQL transaction through a protected endpoint; existing dependency fencing, bounded attempts, conservative reservations, auditing and independent source/numeric verification remain mandatory.
- Public Claude generation requires the separate default-off `anthropic_analyst_generation_enabled` operating gate. A configured key does not activate it. Simulation stays labeled; a failed live request is not silently relabeled as simulation.
- Allowlisted provider HTTP error diagnostics exclude raw content and credentials. One scoped live request returned HTTP 400; no live verification or complete acceptance is claimed. Official approvals remain absent. Candidate migration 0021 was not applied to the running app. [Evidence and remaining risks](G5_3_CLAUDE_REGULATORY_INTEGRATION_REPORT.md).

Scope: synthetic local demonstration. A passing foundation test is not a penetration test, regulatory approval or production acceptance.

| Control | Verified Phase 1 status | Evidence / remaining work |
|---|---|---|
| Password storage | Implemented | Argon2 hash; explicit CLI provisioning; no default accounts; hash and login tests |
| Authentication | Implemented | Short-lived JWT; signature, issuer, audience, required expiry; invalid-token tests |
| Server RBAC | Implemented for available endpoints | Analyst/supervisor/admin roles from current DB state; supervisor cannot ingest or read global admin audit; client role claims never grant authority |
| Case authorization | Implemented, single workspace | SQL-scoped list/count/detail; analysts only their assignments, supervisors/admins oversight; hidden/nonexistent case 404; reassignment removes previous access |
| Tenant/team authorization | Pending enterprise scope | No team/organization data model; supervisor scope is explicitly this workspace, not an invented team hierarchy |
| Strict request validation | Implemented for login and single-alert ingestion | Extra actor/role/predictor fields rejected; exact 27 fields, finite numbers, supported KYC and nullable income; validation errors omit submitted values |
| Secrets | Local implementation | Generated ignored .env; no displayed credential values; production secret manager/rotation pending |
| Audit | Foundation implementation | Auth/bootstrap, ingestion and atomic assignment-change events; actual actor, before/after assignee UUID/version; protected/tamper-resistant retention and review events pending |
| Transport | Local loopback only | TLS at trusted deployment ingress required before network exposure; no claim of local HTTPS |
| Database | Partial | Named-volume PostgreSQL, readiness and constraints; Compose initialization account is not a least-privilege runtime role |
| Sensitive content | Boundary implemented | No private assets in build contexts/Git; synthetic-only alert DB constraint; external AI data policy pending |
| RF artifact trust | Phase 2.1 implemented locally | Reviewed model/contract/source hashes, exact runtime checks, verified in-memory deserialization and namespace cleanup; no API import/upload, scoring or deployment. See PHASE2_1_MODEL_LOADER |
| RF scoring | Phase 2.2 pure Python implementation | Approved loader, bounded unique-ID batches, strict feature allowlist, verified class mapping, finite/range/shape checks, sanitized failures/warnings; no feature logs, API, policy or case mutation. See PHASE2_2_RF_SCORING |
| Policy recommendations | Phase 2.3 pure deterministic implementation | Verified policy SHA/model binding, exact thresholds, strict score/priority validation; invalid or failed inputs require manual review with no success credit. All outputs require human decision; no HTTP endpoint or workflow mutation. See PHASE2_3_POLICY_ENGINE |
| SHAP explanations | Phase 2.4 verified library | Required host ACL callback before work/after verification, no raw value logging/output, exact dependencies/model/input identity, independent checks and empty unavailable payloads on failure. Actual acceptance in hardened local Linux container; no API/worker authorization wiring or timeout deployment yet. See PHASE2_4_SHAP_EXPLAINABILITY |
| Assessment persistence | Phase 2.5 verified internal service | Current DB role/assignment checks before snapshot, explanation and commit/read; stale-state rejection, actor-scoped receipt keys, immutable linked rows, atomic completion audit and read-time content digest. No raw feature duplication, HTTP result submission, automatic disposition or deployed worker. See [assessment security](PHASE2_5_ASSESSMENT_PERSISTENCE.md) |
| Prompt injection/leakage | Planned Week 3 | Treat evidence as untrusted data, enforce tool permissions before retrieval, validate citations, bound tokens/time/cost; test adversarial passages |
| Human approval | Review workflow pending | Assignment changes preserve status/disposition; no automatic closure, dismissal or filing; review approvals remain a later phase |
| Abuse protection | Implemented foundation | Persistent atomic login window per HMAC client key, shared across workers/restarts; 429/Retry-After; declared and streamed request bodies bounded before parsing/DB work |
| Safe observability | Implemented foundation | Server-generated X-Request-ID, bounded event fields, no body/query/credentials/customer values/exception text; own logger configuration does not enable SQL parameter logging |
| Browser protection | Partial | Account verification including supervisor; no token localStorage; container CSP/no-store; full workbench/XSS and browser acceptance pending |

## Implemented permissions and concurrency

See API_CASES for the exact matrix. Case data and active role/assignment predicates are evaluated together in SQL. Lists project metadata; authorized details allowlist the 27 predictors. No raw stored JSON, passwords, SAR labels, idempotency keys or private paths are projected.

Assignment requires an active supervisor/admin, an eligible active analyst or explicit null, and a strict expected version. PostgreSQL shared locks retain actor/target eligibility until commit; an atomic version predicate protects actual changes and no-ops. Case/version/audit changes roll back together. Closed cases cannot be reassigned. Manager/analyst role changes and deactivation affect subsequent requests immediately.

## Foundation limits and defaults

- Browser refresh restores an HttpOnly/SameSite=Strict session after server-side JWT/account validation. The owner-selected default is 60 minutes from login (bounded configuration remains 1–60 minutes). Protected APIs remain bearer-only; no credential or case-data browser storage. Logout deletes the cookie; expiry is not renewed by refresh. Already-issued tokens retain their original expiry. See [browser session contract](API_AUTH.md).
- The explicitly configured local review account can use remembered login: a hash-only, credential-bound server grant with immutable revocation and renewable one-hour bearer tokens. This is disabled outside local development and for all other accounts. Restores and bearer use check current authorization/revocation; logout/password/role changes invalidate remembered access. Browser retention is finite (365-day cookie renewed on restore); no infinite bearer tokens or evidence-expiry changes. See the local-account section of [API_AUTH.md](API_AUTH.md).

- `MAX_REQUEST_BYTES=65536`: actual streamed bytes and Content-Length checked; overflow gets 413 with no parsing/database side effects. No file upload/large batch contract is implied.
- `LOGIN_ATTEMPT_LIMIT=10`, `LOGIN_WINDOW_SECONDS=60`: fixed window counts **all** sign-in attempts per transport client, including success. Unknown usernames and failures share the same policy; active sessions are not revoked by throttling.
- Client keys use domain-separated HMAC; no raw address is stored. Arbitrary X-Forwarded-For is not parsed by the application. Trusted reverse-proxy configuration is a deployment responsibility; a shared proxy/NAT can share a bucket. This is not account lockout or distributed bot mitigation.
- Request IDs are generated by the server, never taken from arbitrary caller input. Application logs contain only event, ID, route name, method, status and error class. Supplied Uvicorn/nginx access logs are disabled to avoid raw URL/query logging; external infrastructure logging also needs approved redaction.
- Expired throttle keys reset on reuse; a retention/cleanup policy for inactive keys remains operational work. No credentials, private data or existing application state are copied into test reports.
- PostgreSQL is the persistent deployment target. SQLite files are disposable unit fixtures; PostgreSQL concurrency/rollback tests are required acceptance evidence.

## Required gates

- Phase 1 local-demo gate verified: authentication negatives, IDOR/cross-analyst tests, strict query/body validation, role provisioning, login/body limits, safe logs, atomic assignment and real PostgreSQL races/rollback.
- Week 2: trusted artifacts only; never deserialize user-supplied pickle/joblib; unsupported inputs fail to review without successful-capture or dismissal credit.
- Week 3: approved provider/data boundary; source permissions, institution/jurisdiction/as-of filtering; fabricated citations and provider failures cause abstention.
- Later workbench/security gate: review approval permissions, authorized export, protected audit retention, runtime DB roles and browser tests. Case ownership/assignment concurrency are already implemented.
- Week 5: TLS, dependency review, backup/restore, rollback, rotation, bounded load and explicit deployment acceptance.

New data sources, public hosting, institutional use and actual customer data require separately agreed scope. No automatic filing, model promotion or retraining is authorized by a review action.

## Phase 2.5 integrity boundary

- Actor IDs originate from trusted server identity. Internal service permits assigned analysts and workspace supervisors/admins; future HTTP submission-role decisions are not implemented here.
- PostgreSQL shared actor/alert locks plus case row locks serialize authorization/input/state changes with the final transaction. Expensive RF/SHAP work runs between short transactions; completion rechecks state and input/source fingerprints.
- Assessment, explanation, score, recommendation and audit commit or roll back together. Duplicate retries reauthorize; changed content/run/key conflicts. Reassessment appends history and never changes human disposition.
- Database triggers reject UPDATE/DELETE of immutable history and linked children; TRUNCATE is blocked. Unlinked foundation audit events are not newly protected. Owners/superusers can bypass triggers; runtime-role separation and independent audit retention remain pending.
- SHA-256 content checks detect accidental corruption on retrieval; they are not signatures or protection against a privileged actor rewriting digests. No new data access/inference HTTP route is exposed.
- Actual RF/SHAP/DB acceptance runs in a non-root, read-only Linux verification container on the local Compose network. Credentials pass through stdin; no `.env` or private assets enter image layers. Native Windows DLL security remains unchanged.

## Phase 2.6 worker and queue controls

- Separate non-login 256-bit worker secrets, hashed in DB and checked on every queue operation. Current admins provision/revoke; current requesting-user case access remains independently required.
- Immutable queued envelopes bind source/input/model/policy identity. Completion rechecks actor/worker eligibility, assignment/state, lease generation and deadline under locks before atomic publication.
- Linux child uses JSON-only private IPC, approved model loading, restricted environment, output/address-space/CPU bounds, independent wall-clock kill watchdog, parent-death SIGKILL and reaping. No feature-value logs or inherited application secrets; child stderr is discarded.
- Expiration or DB outage cannot publish partial results. Three attempts with durable backoff; terminal failures record manual review and keep case/human disposition unchanged.
- Optional non-root worker profile has no ports, read-only source/artifact mounts, dropped capabilities and bounded resources. No dataset mounts or automatic enqueue. Host token ACL/readability and production SQL roles remain operational gates.
- Real Linux/PostgreSQL/process acceptance and limitations: [Phase 2.6](PHASE2_6_DURABLE_JOBS.md). Synthetic fixture clock correction does not change production JWT validation; future-issued JWTs remain rejected.

## Phase 2.7 assessment API controls

- All four routes use bearer authentication, current-role checks and fresh per-case SQL authorization. Job lookup is scoped before resource metadata is loaded; detail binds both URI case and assessment ID. Hidden and absent resources share 404.
- Strict ID/version/policy-only submission and allowlisted response schemas; no client scores/features/artifacts, raw predictor values, source IDs, worker credentials, lease tokens or internal receipt/audit payloads are exposed.
- Persistent per-actor API budgets count failed/hidden lookups and conflict/capacity failures independently of business rollback. Queue admission serializes new active-job counts; rate exhaustion returns 429, saturation/busy returns 503, with retry hints.
- Original job request/creation and new/replayed API request audit commit together. Sensitive read audit must commit before response disclosure; read audits are protected from UPDATE/DELETE. No feature values or explanation bodies enter logs/audit.
- Worker rechecks current actor/service identity and queued source/state before execution/publication. No request starts scoring in the API process or automatically changes case disposition.
- Real Linux/PostgreSQL API/worker acceptance, error semantics and limits: [assessment API](API_ASSESSMENTS.md). TLS, production SQL roles, tenancy, retention and independent audit storage remain deployment work.

## Phase 2.8 operational visibility

- Admin-only internal metrics with fresh active-role SQL check; anonymous, analyst, supervisor and revoked identities denied. No public metrics listener or customer-level monitoring endpoint.
- Fixed allowlists constrain metric names, route/method/status labels, logged fields and correlation IDs. No PII, request/query/body contents, raw paths, secrets, private features or case/job IDs in operational telemetry.
- Bounded histograms/current+previous-minute buffer, asynchronous dedicated DB export and short SQL/connect limits isolate monitoring failures from committed jobs/results. Retried cumulative exports are idempotent; best-effort telemetry loss is explicitly distinguished from job loss.
- Real synthetic TCP/API/worker load and fault injections verified crash recovery, stale fencing, own-transaction PG disconnect rollback, authorization revocation, backpressure and terminal manual review. No automatic case action or private-source/model modification.
- Evidence and limits: [Phase 2.8 operations](PHASE2_8_OPERATIONS.md). Production capacity, HA, TLS/perimeter, SQL privileges, external alerting and institutional data acceptance remain separate gates.

## Phase 2.9 browser boundary

- Memory-only bearer session and uncertain-request receipts; no local/session storage, cookies, URL credentials or third-party analytics. Logout aborts requests, destroys session state and unmounts private screens. Refresh requires authentication. Existing bearer expiration remains the server-side token lifecycle.
- Current identity and visible scope refresh every ten seconds; hidden tabs hide private views until revalidation. Every 401/403/404 clears protected results on response; revocation detection has bounded polling/network delay, not push semantics. Failed access checks hide content.
- UI requests a redacted scoped overview and immutable assessment DTOs; never the raw-predictor detail endpoint. No artifacts, customer feature values, worker secrets or client-generated scores cross this boundary. Literal search stays inside server authorization scope.
- Stable session-scoped run/key/content prevents duplicate uncertain retries across view changes. Sequential polling respects backoff and has read/time limits; navigation/sign-out cancels requests/timers. Human disposition is read-only and separate from recommendations.
- Actual Chromium/Linux/PostgreSQL acceptance covers role scope, IDOR, revocation, persisted jobs, real RF/SHAP results, failure/manual review and logout. Component tests cover conflicts, throttling, uncertain retries and timer cleanup. Accessibility checks cover exercised states, not certification. See [Phase 2.9](PHASE2_9_FRONTEND.md).

## Phase 2.10.1 CSV quarantine boundary

- Dedicated batch-upload permission currently grants only active admins. Metadata and internal byte reads are owner-scoped between admins; analysts/supervisors are not bulk importers. Publication and consumption recheck current DB authorization, including revocation after streaming.
- One bounded authenticated CSV-only stream, no multipart/compression/path/filename inputs. UTF-8/CSV/header restrictions, per-file/row/column/cell caps, 60-second stream timeout, four in-flight uploads per API process and ten active receipts per actor. Existing JSON body limits remain unchanged.
- Private generated filenames, Linux 0700/0600 or Windows protected user/SYSTEM DACL, no-follow regular-file checks and verified SHA before internal consumption. Raw files, headers/values and internal paths never appear in HTTP metadata, errors or audit payloads. Upload storage is not mounted by the frontend or model worker and is excluded from Git/build contexts.
- Actor-scoped intent receipts, DB uniqueness and short locking distinguish identical bytes from duplicate intent. Handled failures clean up; uncertain commits retain bytes for safe idempotent retry and bounded orphan reconciliation. TTL blocks access immediately; delayed physical cleanup is explicit.
- No AV scanner or application-level encryption-at-rest exists. CSV quarantine/no execution/no deserialization/access restrictions are compensating controls; enterprise AV, encryption/keys, gateway/global quotas and production-data approval remain planned.
- Evidence, error contracts and limits: [Phase 2.10.1](PHASE2_10_1_CSV_STAGING.md). No row-value validation, import, dispatch, CSV UI, export, model change or automatic case action is implemented.

## Phase 2.10.2 mapping/preview boundary

- Admin-only, upload-owner scope on headers, validation, summaries and errors. Every operation rechecks current SQL authorization and verified private file identity/expiry; foreign upload and cross-upload result IDs are concealed with 404. Actor locks serialize committed role revocation and validation transactions.
- Duplicate JSON keys, ambiguous source reuse, missing/unknown target fields, alternative units declarations and unsupported versions fail closed with fixed errors. Preserve the exact 27-field semantics, null/zero distinction and original unknown-state behavior. Baseline units are an explicit operator assertion; numeric cells cannot prove currency or scale.
- Streaming full-file validation, 100-row diagnostic insert batches, 64-KiB JSON cap, two per-process slots, ten-second cooperative budget and five versions per upload by default. SQL timeouts and database uniqueness bound contention/replay; global replica quotas remain pending.
- Header names are available only through the owned header/mapping endpoints and retain restricted ASCII syntax. No row values/source IDs are returned in previews, persisted in diagnostics or copied to audit/logs. Errors expose only canonical fields and fixed codes, with bounded pages. Formula/markup cells are inert; warning codes are not spreadsheet export sanitization.
- Mapping/results/audit commit atomically; partial parsing/storage/database/deadline failures roll back. Service/API history is versioned and append-only, not claimed tamper-proof against privileged SQL edits. Original staged bytes remain unchanged.
- Malware scanning remains unavailable; no file is declared safe. No canonical alerts/cases/jobs, batch ML dispatch, frontend, export or automatic case action. [Concrete preview/API/security limits](PHASE2_10_2_VALIDATION_PREVIEW.md).

## Phase 2.10.3 import approval and execution boundary

- Strict explicit boolean approval binds owned completed preview, exact SHA/mapping/validation/units and frozen counts. Reject duplicate JSON keys, stale identities, no-valid-row approvals and unauthorized ownership. Fresh admin SQL checks on every approval/read/chunk; row links additionally enforce existing case visibility. No new analyst/importer role or tenant scope is invented.
- A separate non-login csv_import_workers registry/token grants only controlled import execution. No assessment-worker token reuse, public worker HTTP interface or model assets. Linux import container uses non-root UID, read-only CSV/root mounts, dropped capabilities/no-new-privileges and bounded resources. Operator provisioning needs trusted database access plus a current admin identity.
- PG advisory admission, actor/global capacities, bounded chunk transactions, database-clock leases, random fencing, final time/lease checks and capped recovery/backoff. Source/role/worker revocation is rechecked and serialized with active chunks. Already committed chunks persist; incomplete chunks roll back, including their canonical rows, receipts and audits.
- Original input conversion/fingerprints and source uniqueness are reused. Conflicting sources have no returned foreign links or silent overwrites; matching cases retain status/disposition/assignment. No assessment job, prediction, automatic dismissal/closure or SAR action is created.
- DB guards freeze approved preview/source/approval identity, terminal imports, row receipts and import audit history. File integrity is verified each chunk; TTL is not extended. Retained owner-scoped receipts/counters/diagnostics survive source expiry. Privileged SQL owner access and institutional retention remain deployment limitations.
- No feature cells/source IDs in import logs, audit payloads or progress/row errors. CSV is still unscanned; no malware-safety claim. Real synthetic PG interruption and Linux process-crash/restart acceptance are documented in [durable import](PHASE2_10_3_DURABLE_IMPORT.md).

## Phase 2.10.4 explicit batch ML boundary

- Only current active admin/import owners can explicitly start/read a batch; no automatic CSV-to-ML hook. Freeze authorized successful-import cases, versions and alert identities; omit invalid/conflicting rows, skip closed/changed cases. Aggregate and page reads recheck owner plus every member-case scope.
- Requests/status/results share the existing authenticated assessment budget. New job attempts consume that same budget and existing global queue capacity; bounded groups/backpressure prevent unbounded job bursts. Immutable key aliases and import/policy/artifact identity prevent repeat reassessments; matching prior results and active jobs are reused.
- API-owned maintenance uses short DB transactions/locks, not a new worker credential or ML implementation. Existing enqueue core atomically commits jobs, batch links and audits. Process/DB interruptions roll back incomplete groups; committed links/run IDs resume without duplicate assessments.
- Existing Linux workers retain their verified model/SHAP, leases, retries and fencing. Originating batch jobs additionally recheck active bulk permission and frozen artifact identity during preparation and final publication; role demotion to supervisor revokes bulk execution, even while ordinary case scope remains. Assignment changes invalidate snapshots. Independent pre-existing jobs retain original authority.
- Progress joins authoritative persisted jobs; pending retries are distinct from terminal failures/manual review. Verified public AssessmentDetail projections expose no raw predictors, source IDs, paths or tokens. Fixed operational labels and sanitized correlation logs/audits retain privacy.
- No automatic dismissal/closure/SAR action, frontend, LLM/RAG, retraining or malware-safety claim. Uploads remain unscanned. Rebuild API and ML worker together; enterprise SQL roles/tenancy, retention, external scheduler/SLO and production capacity remain separate gates. [Batch assessment contracts](PHASE2_10_4_BATCH_ASSESSMENT.md).

## Phase 2.10.5 batch UI and export

- Current admin/owner/member-case checks remain server authoritative. New UI sends raw CSV only to staging and consumes value-free preview/verified result DTOs; no client-provided scores or raw predictor retrieval. Separate import and assessment confirmations; uncertain retries preserve exact in-memory keys/content.
- No browser-persisted credentials, receipts, features or result caches. Session/navigation abort cleanup, bounded polls, existing identity/visibility guard and denial handling clear protected views. Revocation has bounded polling/network delay.
- Export is range/byte bounded, fixed-field allowlisted and authenticated with the existing shared rate budget. All member permissions/integrity checked and immutable range/count/SHA audit committed before any CSV disclosure; audit failure returns no file. Generated filenames, no-store responses, quoted UTF-8 cells and formula-prefix neutralization. Raw predictors, source identifiers and private artifact paths excluded.
- Tests exercise real Linux/PostgreSQL/Chromium processing, role revocation, lost acknowledgement/idempotency, manual-review failures, formula injection and field restrictions. Uploads remain unscanned. Download retention, production IAM/SQL privileges/tenancy and independent audit storage remain deployment gates. [Detailed security/limits](PHASE2_10_5_BATCH_FRONTEND.md).

## Phase 2.10.6 acceptance evidence

- [Acceptance matrix](PHASE2_10_6_ACCEPTANCE.md) maps authorization/owner/case isolation, role/assignment revocation, tampered approvals, concurrent idempotency, malformed/large CSV, quotas, formula-safe export, privacy and audit rollback to executable tests.
- Actual Linux/PostgreSQL fault scenarios include process death before/after transaction commit, owned PG connection termination, stale lease fencing, real scientific stage-boundary SIGKILL and restart. A real listener/lifespan/dispatcher restart is exercised with browser reload/login/resume. No shared development database outage/reset is injected.
- Resource-bounded new synthetic workloads, aggregate-only benchmark output, read-only scientific assets, in-memory/pipe credentials, private tmpfs and isolated generated test schemas. Queue depth and connection/memory/CPU observations are local samples, not capacity guarantees.
- Malware scanning remains unavailable. Production IAM/SQL roles/tenancy, independent audit storage, TLS/perimeter/global quotas, download/data retention, backup/restore/HA and source-use authorization remain residual gates. Revocation has existing bounded browser polling delay. No production certification, automatic case action or later-phase implementation is claimed.

## Phase 3.1 investigator design - proposed controls only

- [Threat/control/evaluation matrix](PHASE3_1_SECURITY_EVALUATION.md) covers direct/indirect injection, poisoned/incorrectly scoped references, tool/SQL/URL abuse, PII, cross-case leakage, stale/revoked evidence, cost exhaustion and audit/review accountability. No new control or provider integration is implemented here.
- Proposed tools are read-only and server-bound to actor/case/source versions; current SQL authority rechecked before retrieval, provider egress, publication and disclosure. No LLM credential, arbitrary DB/network tool or consequential write capability. Document data cannot override system permissions.
- Separate deterministic numeric/citation checks from independent human semantic/applicability review. Model signals, observations, generated hypotheses, internal policy and regulatory text have distinct authority classes. Provider timeout/revocation never causes a lower RF score, dismissal or fabricated evidence.
- Jurisdiction/entity context, source-use approval, provider/privacy/region/retention contract, review capability and class-specific retention remain decisions. External disclosure cannot be undone by later revocation. Malware scanning and production IAM/TLS/SQL roles/tenancy/independent audit controls remain unavailable/pending; no certification claim.

## Phase 3.2 internal synthetic evidence controls

- Active admin **and source owner** required for register/admit/correct/bind/link/grant/revoke; current case authorization also required. Fresh SQL user/case locks serialize writes and revocation. Analysts can read an internal manifest only for assigned cases with an explicit active source grant; supervisors/admins reuse existing workspace case scope.
- Admission regenerates supported fictional bundles from fixed configuration and verifies canonical manifest/digests. No arbitrary real customer input, binary object, URI fetch, uploaded evidence or provider capability. Test-oracle labels remain in `backend/tests/evidence_oracles.py` only.
- Immutable releases/typed history, source-scoped FKs, complete-payload deferred checks and evidence audit guards prevent service-side overwrite/cross-source linkage. Grant/link/revision/audit and new Alert/Case binding transactions roll back together on audit/database failure. Replays do not restore revoked access or duplicate cases.
- Manifests apply current case/source/link permissions, verify stored payloads and commit the read audit before returning value-free provenance. They exclude feature declarations, names, amounts and raw predictor values. Errors contain fixed codes; no customer data logging. Revocation removes source/record projections; linked corrections remain distinct from contradiction observations.
- Limits: 100 sources/owner, 100 releases/source, 200 observations/bundle, 1,000 visible record versions/manifest; 2/5/15-second lock/statement/idle timeouts. Exceeding limits fails explicitly. No public evidence endpoint or unbounded evidence export.
- Primary acceptance: real PostgreSQL locks/FKs/immutability, duplicate races, revocation, owned connection termination and audit rollback; real pinned Linux worker for new null/zero-income scenarios. [Implementation and limitations](PHASE3_2_EVIDENCE_FOUNDATION.md).
- Synthetic-only scope does not establish real-feed truth, regulator approval or enterprise authorization. Deployment SQL roles, independent audit storage, tenancy/RLS and approved retention remain pending. Malware scanning unavailable; no automatic closure/SAR/LLM/RAG.

## Phase 3.3 evidence disclosure controls

- Server binds actor/case from authentication/route. Fresh SQL role, assignment and active source/version membership precede projection, counts, ordering or analysis. Short actor/case locks serialize grant/role/assignment changes with the audited read commit.
- Domain-separated snapshot/cursor signatures are not authentication grants. Bind current case state/version, role, evidence/access revisions, membership, explicit assessment, operation, filters, page size and expiry; invalidation never silently switches to new evidence.
- Relationships require both endpoints to be currently linked. Shared aliases/counterparties cannot widen access; withdrawn identities are redacted from transactions and excluded from related/concentration handles. Model retrieval reuses parent-scoped immutable assessment verification and removes raw predictor/internal mapping fields.
- Existing shared authenticated rate budget, four per-process read slots, 12 KiB strict JSON, 256 KiB output, fixed source/record/page/window/bucket limits and SQL timeouts. Duplicate keys, extra parameters, unsupported status/currency/calculation, malformed UUIDs/tokens and SQL/path/URL attempts fail safely. Read audit or database failures disclose nothing; audits remain immutable.
- No network/provider/document fetch, LLM arithmetic or consequential case action. Source observations, descriptive facts and model signals have distinct output classes. Missing expected activity/status/sampling/documents are explicit, not inferred. [Controls, acceptance and residual limitations](PHASE3_3_RETRIEVAL_ANALYTICS.md).
## Phase 3.4 reference corpus controls

- Curated local safe text only; no arbitrary document/URL upload or runtime network fetch. Exact HTTPS publisher allowlist (`ecfr.gov`, `govinfo.gov`, `fincen.gov`, with www variants), no credentials/custom ports/fragments/traversal. Reject binary/PDF/Office, XML entities, ambiguous sections and oversized/deep documents. Malware scanning remains unavailable; parsing is not a malware-safety claim.
- SHA-bound original/extracted/complete-section text, parser version and metadata; immutable PostgreSQL versions, chunks, source approvals, releases and lifecycle events. Human approval must cover provenance, rights, dates and exceptions. Proposed and unknown-validity sources remain unpublished; synthetic fixture approvals are test-environment-only and cannot certify legal quality.
- Server-bound U.S.-bank/English/November-2 historical context; explicit active corpus grant **and** current case scope on search and citation resolution. Approval/access/withdrawal/jurisdiction/entity/language/dates filter before ranking. No client scope override, generic tool executor or RF policy-as-law conversion.
- Current actor/case/context locks serialize disclosure against assignment changes, grant revocation and curation; audit must commit before disclosure. Read audit contains query/response hashes and counts, not query text or customer features. Malicious reference text is inert data, never instructions.
- Bounded shared authenticated budget, four read slots, 12 KiB request, five passages, <=256 KiB response, <=1,000-chunk citation scan and PostgreSQL lock/statement limits. 404 hides unauthorized/forged citations; sanitized failures expose no source text, SQL or internal traces.
- Ordinary SQL update/delete/truncate guards are not protection from privileged database administrators. Production SQL roles, external audit retention, signed reviewer workflow, source freshness monitoring and tenant governance remain unresolved. This phase claims local technical acceptance only, not production certification. [Review gates](PHASE3_4_APPROVAL_DOSSIER.md).
## Phase 3.5.1 evidence-only investigation boundary

- No LLM/provider call, regulatory lookup, free-form tool, new public API or case/SAR action. Explicit stored model selection or omission; raw predictors stay outside manifests/packets. Observations, derived facts, model recommendations and human disposition are distinct fields.
- Current actor/case/source checks and revision fingerprints guard admission, each retrieval, publication and disclosure. Stale/revoked results are withheld; no silent source/model refresh. Requester-only run access is the MVP scope.
- Separate worker registry and purpose-hashed secret, 60-second lease/45-second deadline, unpredictable fence, bounded attempts/backoff/queue/record/step/body sizes and cooperative recovery. Worker uses a private scratch snapshot signer; it does not need the API JWT key.
- Independent source-row Decimal/reference checks reject altered financial output and references; worker verification claims are not trusted. Immutable run/packet/key/audits, deferred envelope/publication guards and atomic rollback prevent partial completion. Serialization warnings become sanitized errors rather than customer-data logs.
- Tests use synthetic fixtures in disposable schemas on a recovery clone, not the live demo; real stored model projection uses existing pinned RF/SHAP services only as setup. No change to frozen models, routing or explanations. [Scope, bounds, races and acceptance](PHASE3_5_1_EVIDENCE_COORDINATOR.md).
- This does not establish semantic/legal correctness, validated AI behavior, production tenant isolation/SQL privileges/retention/HA or future provider security. Those approvals and Phase 3.4 regulatory human gates remain pending.
## Phase 3.5.2 - Simulation-only provider boundary

- External calls remain disabled, including when the unsupported external-enable flag is set. No network adapter, provider key, unapproved regulatory retrieval or arbitrary tool is registered. Simulation requires an explicit server configuration and request; fake results never represent live model accuracy.
- Reuse current case/source authorization, parent evidence/access/assessment manifest and independent raw-record verification before delivery/publication/disclosure. Cross-case identifiers, forged references, unsupported numbers, provider-written trusted fields, tool requests and legal citations fail closed. Server-rendered facts and constrained uncertain inquiry templates avoid laundering free factual narratives as verified output.
- A fixed Linux child receives no DB/JWT/provider environment secrets, raw source text, customer/account/case identity, raw predictors or private artifact hashes. Wall/process/output/CPU/memory bounds, conservative immutable attempt reservations, <=3 retries and fences bound execution. No arbitrary-plugin sandbox or future LLM prompt-injection certification is claimed.
- Child requests/jobs/receipts/results/audits commit atomically with parent admission or publication as appropriate; immutable history and deferred envelope/budget/result guards prevent partial success or budget resets after a crash. Unknown usage is null and retained reservations are not refunded automatically. Live provider/data/region/egress/retention/cost approval and independent semantic evaluation remain required. See [design and acceptance](PHASE3_5_2_LLM_INVESTIGATOR.md).
# Upload workspace update — 2026-11-18

- Upload session membership never grants case access. Current role, ownership and assignment predicates remain mandatory; session counts, pagination and lookup are server-scoped.
- Actor locks, version checks, creation-key idempotency and atomic upload binding prevent stale requests from moving uploads or silently replacing a newer selection. No raw predictors/tokens are persisted in browser storage.
- Raw CSV expiration is unchanged; stored imports/results survive session changes. See [UPLOAD_SESSIONS.md](UPLOAD_SESSIONS.md).
# Candidate 0023 integration gate

- Deferred regulatory intents are server-owned and bound to the immutable child configuration, including the admitted reference context/release/grant revision fingerprint. Revoke/regrant invalidates old authority. Admission/preparation require candidate schema 0023; the database rejects an attempt without a matching frozen case/actor/parent/query/snapshot/packet binding and an admitted-authority digest.
- Only existing approved-only G5 retrieval is used. Research metadata does not authorize passage transmission; evidence-only v2 approvals cannot gain deferred regulatory scope.
- Context is never renewed during recovery. Source/actor authority, clock epoch and expiry are rechecked using existing services. Missing approved context fails before provider reservation and remains a manual-review failure.
- No stable independent runner is currently available; no live acceptance, production certification or general analyst activation follows from offline tests. See [gate status](FINAL_INTEGRATION_DEMO_GATE.md).
