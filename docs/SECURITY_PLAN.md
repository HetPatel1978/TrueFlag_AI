# Security foundation and progressive controls

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
