# Target architecture — five-week MVP and later expansion

**22 November native Windows execution:** the existing application now runs as the primary local candidate on native PostgreSQL/FastAPI/React with Windows Job Object child bounds; durable queues, lease fencing, source authorization, independent verification and the 900-second snapshot policy are preserved. This is a platform adaptation of the existing services, not another application. [Measured native acceptance](WINDOWS_NATIVE_RUNTIME.md); [source-review and live Claude gates](WINDOWS_LIVE_INVESTIGATION_GATE.md). Official source approvals and a verified real grounded Claude response remain missing; no provider activation is implied.

**22 November private development candidate:** the existing Claude adapter now supports a smaller versioned flat wire format, converted into the original typed proposal and independent verifier. Existing PostgreSQL jobs, authorization, clock fencing and immutable audit remain the execution boundary. A new exact-approval-scoped development financial policy omits the withdrawn monetary prerequisites, preserving all other scopes. No new provider framework, public API, frontend activation or regulatory publication. [Implementation and pending exact request](CLAUDE_DEVELOPMENT_UNBLOCK_2026_11_22.md).

**November 21 workflow presentation:** [Guided workflow UX](TRUEFLAG_WORKFLOW_UX_SIMPLIFICATION.md) maps the existing protected services to Assess Alert, Review Evidence, AI Investigation and Human Decision. Administration groups imports, provider usage and diagnostics. This adds no backend service, scientific behavior or permission. Candidate atomic AI admission remains on the existing PostgreSQL workers; its local-demo schema and clock-health acceptance gates remain unresolved.

## G5.3 candidate integration ? 21 November 2026

- Existing PostgreSQL parent/child workers remain the execution boundary. The protected atomic-start API admits evidence preparation and findings intent together; browser polling is not job orchestration.
- Optional regulatory context is stored immutably with existing packet, source/version/release/citation, grant revision and clock identities. Admission, dispatch, completion and reads revalidate current authority; ordinary evidence-only requests do not require a corpus.
- The existing React workbench renders typed, independently verified Claude or simulation results with distinct labels. General Claude activation defaults off; official RAG remains blocked by missing human approvals.
- Candidate migration 0021 depends on candidate 0020 and is not installed in the local app, which remains schema 0019. One actual Claude attempt returned HTTP 400. [Implementation, acceptance failures and remaining gates](G5_3_CLAUDE_REGULATORY_INTEGRATION_REPORT.md).


**November 18 UI update:** [Task-first workspace](UX_WORKSPACE_REWORK.md) reorganizes existing APIs into Cases, Imports, Reviews and Administration, with a unified four-section case workspace. No new backend services, schema or scientific behavior; protected roles, evidence boundaries, human decisions and local remembered login remain in place. Earlier phase descriptions below are historical architecture records.

Phase 3.1 design proposals are collected in [Investigation architecture](PHASE3_1_INVESTIGATION_ARCHITECTURE.md), [evidence model](PHASE3_1_EVIDENCE_MODEL.md), [retrieval/RAG contracts](PHASE3_1_RETRIEVAL_RAG_CONTRACTS.md) and [security/evaluation](PHASE3_1_SECURITY_EVALUATION.md). The investigation/RAG proposals remain pending; Phase 3.2 internal synthetic evidence is implemented below.

This is a target, not an implementation claim. Initialization status is in PRODUCT_SCOPE and SETUP_STATUS. Use a modular service with a separately pinned scientific worker; introduce distributed systems only when justified.

**November 21 integration boundary:** [Regulatory/Claude bridge](REGULATORY_CLAUDE_INTEGRATION.md) binds a verified investigation to currently approved case-scoped passages and revalidates citations before provider handoff/result verification. The protected investigation endpoint and React guidance client are implemented. Source publication, durable draft-binding persistence and general Claude activation remain blocked or pending; no separate retrieval engine was introduced.

Current acceptance is in [IMPLEMENTATION_STATUS](IMPLEMENTATION_STATUS.md). Phases 2.1-2.9 include approved ML, immutable results, bounded durable Linux jobs, protected APIs and [internal operational monitoring/load-recovery evidence](PHASE2_8_OPERATIONS.md). The [React workbench](PHASE2_9_FRONTEND.md) consumes scoped overview/request/status/history/detail APIs; production deployment acceptance remains pending; ingestion does not automatically score.

| Boundary | Implemented now | Pending |
|---|---|---|
| API/security | Current JWT/roles/case scope, protected assessment APIs, strict DTOs, shared per-user request budget, queue admission and sensitive-read audit | Enterprise IAM, tenancy, perimeter and production SQL roles |
| Case service | Scoped list/detail, filtered pagination/sorting, versioned assignment and transactional change audit | Notes, approvals, reports and full review state machine |
| Data | Synthetic ingestion, receipts, 36 domain tables including versioned synthetic evidence, immutable assessments/jobs and bounded operational rollups | Production retention/governance, new sources and least-privilege SQL roles |
| UI | Memory-only React sessions, authorized alert dashboard, safe case details, verified SHAP/history and asynchronous assessment workflow | Assignment editor, notes, evidence, human approval/report workflows |
| Scientific worker | Bounded Linux execution, fencing/recovery/retries, stage timing and measured local fault/load acceptance | Production capacity/SLO, HA and operational deployment |
| Policy engine | Frozen rules, 12000-route parity, immutable recommendations and case-scoped HTTP retrieval | Human review workflow; no automatic case action |
| Explanation service | Exact SHAP, verified 41-to-27 grouping, immutable storage, bounded worker, redacted APIs and reusable case/batch UI | Production acceptance |

Implemented Phase 2.10.1-2.10.3 staging/preview/import boundary: admin-only contract/template/raw-CSV upload/owned metadata, private durable API volume, upload receipts plus versioned mapping/preview and diagnostic tables, expiry/orphan reconciliation and audit. Only explicit approved import creates canonical alerts/cases; no ML jobs are created. See [phased onboarding](PHASE2_10_BATCH_ONBOARDING.md) and [concrete staging contracts](PHASE2_10_1_CSV_STAGING.md) and [mapping/preview API](PHASE2_10_2_VALIDATION_PREVIEW.md) [durable import](PHASE2_10_3_DURABLE_IMPORT.md) and [explicit bounded batch assessment](PHASE2_10_4_BATCH_ASSESSMENT.md).

```mermaid
flowchart LR
  Admin[Current active admin] --> Stream[Authenticated bounded CSV stream]
  Stream --> Spool[Private generated spool]
  Spool --> Structural[UTF-8/CSV syntax and resource checks]
  Structural --> Receipt[(Owned upload receipt and creation audit)]
  Structural --> Bytes[(Private retained file)]
  Receipt --> Owned[Owned metadata API]
  Bytes --> Preview[2.10.2: permission-checked versioned mapping and streaming validation]
  Preview --> Diagnostics[(Value-free paginated diagnostics and completion audit)]
  Preview --> Approval[2.10.3: explicit owner approval bound to preview]
  Approval --> Queue[(PostgreSQL import queue and audit)]
  Queue --> ImportWorker[Separate scoped Linux import worker with read-only CSV]
  ImportWorker --> Chunks[Canonical transaction core and fenced chunk commit]
  Chunks --> Rows[(Alerts, cases, row receipts, checkpoints and audits)]
  Rows --> Explicit[Explicit 2.10.4 Start Assessment]
  Explicit --> Dispatch[Bounded API dispatcher and existing shared budgets]
  Dispatch --> AssessmentQueue[(Existing ML jobs and atomic member links)]
  AssessmentQueue --> ML[Existing trusted Linux RF / policy / SHAP worker]
  ML --> BatchResults[Verified results and SQL aggregate progress]
  React[2.10.5 admin React batch workflow] --> Stream
  React --> Preview
  React --> Approval
  React --> Explicit
  BatchResults --> React
  React --> Export[Bounded owned result export and formula protection]
  Export --> AuditExport[(Committed range and digest audit)]
```

Implemented Phase 2.8 operational flow (no frontend or additional service):

```mermaid
flowchart LR
  Request[API request guard] --> Buffer[Bounded fixed-label histograms]
  Worker[Existing worker and numeric child timings] --> WorkerBuffer[Bounded worker histograms]
  Buffer --> Export[Independent PostgreSQL exporter]
  WorkerBuffer --> Export
  Export --> Metrics[(Cumulative operational rollups)]
  Operator[Current active admin JWT] --> Internal[Internal metrics API]
  Metrics --> Internal
  State[(Jobs and durable audit counts)] --> Internal
  Request --> Logs[Sanitized correlated logs]
  Worker --> Logs
```

Implemented Phase 2.7 API flow (all routes require current authentication and case scope):

```mermaid
flowchart LR
  Client[Authenticated API client] --> Budget[Current DB role and persistent actor budget]
  Budget --> POST[POST case assessment with version run and policy]
  POST --> Admission[Case and source checks plus idempotency and queue capacity]
  Admission --> Job[(Durable PostgreSQL job and request audit)]
  Job --> Worker[Existing bounded Linux RF policy and verified SHAP worker]
  Worker --> Result[(Atomic immutable assessment and audit and Succeeded job)]
  Budget --> GET[GET job status or case history/detail]
  GET --> Scope[Current assignment and resource binding]
  Scope --> Projection[Integrity check and bounded response projection]
  Result --> Projection
  Projection --> ReadAudit[Commit sensitive-read audit]
  ReadAudit --> Output[Status summaries or score policy and grouped explanations]
```

Implemented Phase 2.6 internal job flow (no public inference endpoint):

```mermaid
flowchart LR
  Caller[Trusted principal and explicit internal enqueue] --> Check[Current case scope and frozen request fingerprint]
  Check --> Queue[(PostgreSQL Pending job and enqueue audit)]
  Service[Active worker credential] --> Claim[SKIP LOCKED claim and fenced lease]
  Queue --> Claim
  Claim --> Child[Isolated Linux RF plus policy plus verified SHAP]
  Watchdog[Heartbeat and independent kill watchdog] --> Child
  Child --> Recheck[Current user and worker and source and lease checks]
  Recheck --> Commit[One assessment plus explanation plus audit plus Succeeded transaction]
  Claim --> Recovery[Expired lease recovery and bounded backoff]
  Recovery --> Queue
  Recovery --> Manual[Failed manual-review job after attempt limit]
```

Implemented Phase 2.5 internal flow (no HTTP inference endpoint or deployed worker):

```mermaid
flowchart LR
  Caller[Trusted server principal and run request] --> Scope[Current role and case authorization]
  Scope --> Snapshot[Validate alert and capture fingerprints]
  Snapshot --> Compute[Approved RF plus policy plus verified SHAP]
  Compute --> Recheck[Lock and recheck authorization and state]
  Recheck --> TX[One PostgreSQL transaction]
  TX --> Score[(Existing model_scores)]
  TX --> Decision[(Existing decisions)]
  TX --> Explanation[(Immutable explanations)]
  TX --> Assessment[(Versioned assessment and provenance)]
  TX --> Audit[(Linked completion audit)]
  Read[Internal bounded reads] --> ACL[Current case scope plus integrity check]
  Assessment --> ACL
  Recheck -->|Stale or revoked| Abort[Reject without partial writes]
```

Implemented library flow (the later API/workbench flow below remains a target):

```mermaid
flowchart LR
  Input[27-feature record] --> ACL[Host authorization]
  ACL --> Snapshot[Immutable validated snapshot]
  Snapshot --> Score[Existing approved RF scorer]
  Snapshot --> SHAP[Approved preprocessing and exact TreeSHAP]
  Score --> Verify[Independent score, grouping, base and provenance checks]
  SHAP --> Verify
  Verify --> Recheck[Recheck host authorization]
  Recheck --> Result[Verified contributions and ranking]
  ACL -->|Denied| Unavailable[Unavailable with no contribution payload]
  Verify -->|Failure| Unavailable
  Recheck -->|Revoked| Unavailable
```

```mermaid
flowchart TB
  subgraph Frontend[React + TypeScript frontend]
    UI[Analyst investigation workspace]
    Review[Human review / approval / report]
  end
  subgraph Boundary[Security and API boundary]
    Auth[JWT + server RBAC + body limits + persistent login throttle]
    API[Versioned FastAPI APIs]
  end
  subgraph Backend[Modular backend services]
    Ingest[Alert ingestion / validation / idempotency]
    Prepare[Customer references / exact feature contract]
    Cases[Scoped case reads + versioned assignment; review workflow pending]
    Policy[Deterministic policy and prioritization]
    Investigate[Bounded AI draft coordinator]
    Retrieve[Permission-aware evidence retrieval]
    Corpus[Scoped versioned regulatory ingestion]
    Jobs[Durable jobs / transactional outbox]
    Audit[Actor-attributed audit events]
  end
  subgraph ML[Isolated Python 3.11 scientific worker]
    RF[Unchanged fitted RF baseline]
    XAI[Verified SHAP + score provenance]
  end
  subgraph Storage[Persistence boundary]
    PG[(PostgreSQL domain records)]
    Objects[(Versioned local evidence / object-store interface)]
    Models[(Private trusted model artifacts)]
  end
  subgraph External[Approved external boundaries]
    Input[Synthetic alert batches]
    Sources[Approved official regulatory sources]
    LLM[Provider-neutral LLM adapter: Week 3]
  end
  Input --> Ingest --> Prepare --> Jobs --> RF
  Models --> RF --> Policy --> Cases
  RF --> XAI --> Objects
  UI --> Auth --> API
  API --> Cases
  API --> Ingest
  Cases --> PG
  Policy --> PG
  Cases --> Investigate --> Retrieve
  Sources --> Corpus --> Objects
  Retrieve --> Objects
  Retrieve --> Investigate --> LLM
  LLM --> Investigate --> Review --> Cases
  Cases --> Audit --> PG
  Ingest --> Audit
  Cases --> Jobs
  PG --> Monitor[Health / readiness / quality / latency / drift monitoring]
  Review --> Feedback[Reviewed outcomes: separate from source labels]
  Feedback --> Evaluation[Controlled offline evaluation and promotion gate]
  Evaluation --> Models
  Graph[Future entity resolution / graph analytics] -.-> Prepare
  Behavior[Future behavioral anomaly models] -.-> Policy
  Stream[Future transaction monitoring / event stream] -.-> Ingest
  Agents[Future specialized agents if justified] -.-> Investigate
  Enterprise[Future institution integrations / advanced MLOps] -.-> API
```

Solid arrows represent intended MVP flows; dashed arrows are future integrations. Monitoring/evaluation are MVP operational capabilities; automatic retraining and advanced registry infrastructure are not.

| Component | Responsibility |
|---|---|
| Ingestion/preparation | Validate exact contract, classify synthetic data, preserve missingness and source identity; never manufacture transaction history |
| RF/XAI | Produce versioned scores and independently checked explanations; no policy/filing authority |
| Policy | Thresholds, supported KYC and explicit processing failures; deterministic versioned decisions |
| Cases/review | Scoped reads, assignment and optimistic concurrency implemented; state transitions, approvals and authorized reporting pending |
| Retrieval/corpus | Evidence IDs, permissions, jurisdiction, institution scope, source hashes and as-of context |
| AI coordinator | One bounded provider workflow, source-cited draft or abstention; no autonomous consequential write |
| Audit/storage | Separate observations, scores, decisions, reviews and source labels with transactional linkage |
| Monitoring/evaluation | Operational failures and drift; reviewed offline experiments and explicit model promotion |

Preserve the baseline namespace in the worker; the API uses `app`. Do not add graph/behavioral features to the frozen 27-predictor pipeline. A graph database, Kafka, Kubernetes and multiple agents are not prerequisites for this MVP.

## Phase 2.10.5 batch browser and export boundary

- `frontend/src/batch.tsx`, `batch-api.ts` and `batch.css` reuse existing authentication, APIs and SHAP/history components. Exact server-generated mapping, separate explicit import/assessment, bounded cancellable polling and resume links; no browser model or raw-cell preview.
- One minimal backend export route reuses owned batch/current case scope, verified projections, fixed fields and shared rate budget. Bounded CSV bytes and range/digest audit commit before download; no new schema, queue or worker.
- [Concrete workflow, API, failure behavior and acceptance](PHASE2_10_5_BATCH_FRONTEND.md). Full 2.10.6 acceptance and Phase 3 remain pending; files are unscanned.

## Phase 2.10.6 acceptance boundary

- No new runtime service, public API, schema or scientific behavior. The complete existing CSV/approval/import/dispatch/Linux ML/persistence/React/export architecture is exercised through actual TCP APIs and isolated PostgreSQL schemas.
- New consolidated cross-stage tests verify rejection/conflict/reuse through history/export; controlled real RF/SHAP stage-boundary SIGKILL tests verify no partial publication; real API/lifespan/dispatcher restart plus browser reload verifies durable resume and no reassessment.
- Bounded 100/1000-row workloads retain default parser/import/export/rate limits; a test-only 20-job queue measures backpressure. 5000 rows are rejected at the default 2000-row ingress limit. [Acceptance matrix, measurements and residual boundaries](PHASE2_10_6_ACCEPTANCE.md).
- Local synthetic evidence does not certify production security/capacity. Malware scanning, enterprise identity/SQL roles/tenancy, TLS/retention/HA and source/data governance remain separate gates. No Phase 3 implementation.

## Implemented Phase 3.2 internal evidence boundary

```mermaid
flowchart LR
  Config[Fixed synthetic scenario UUID / seed / versions] --> Generator[Deterministic generator]
  Generator --> Validate[Regeneration / hashes / 27 declared inputs]
  Validate --> Store[(Immutable source and typed record versions)]
  Store --> New[Explicit new-case creation]
  New --> Ingest[Existing atomic Alert / Case ingestion]
  Ingest --> Bind[(Immutable binding / source grant / exact version links)]
  Store --> Manifest[Internal verified manifest / declared coverage]
  Bind --> Manifest
  Auth[Current role / assignment / source access] --> Manifest
  Auth --> New
  Manifest --> Audit[(Atomic revisions and audit)]
  Ingest -. explicit separate request .-> Queue[Existing durable assessment queue]
  Queue --> Worker[Unchanged pinned Linux RF / Policy / SHAP]
```

- No new service container, public evidence route or frontend. Twelve additive PostgreSQL tables and internal services support future retrieval. Full 27-field matrix, source/case isolation, correction/revocation semantics and tests: [Phase 3.2](PHASE3_2_EVIDENCE_FOUNDATION.md).
- Existing legacy Evidence anchors, alerts, cases, assessments and frozen scientific pipeline are preserved. One generated source can bind only to its newly ingested case. Existing cases retain unavailable raw-history coverage.
- All 27 RF features are explicit synthetic declarations; zero are claimed ledger-derived. Source coverage and observed transactions are separate from declarations. Unsupported/missing feature input blocks case creation while retaining an evidence-only fixture.
- Public retrieval/analytics in 3.3 and later RAG/provider/investigator work remain separate scope. No graph/vector/agent infrastructure is required here.

## Implemented Phase 3.3 retrieval and analytics

- [Read service](../backend/app/services/evidence_read.py) builds case-bound signed snapshots, exact authorized version projections, one-hop relationships and stored assessment views. [Decimal analytics](../backend/app/services/evidence_analytics.py) computes allowlisted single-currency/window facts with explicit reversal/coverage rules.
- [Six bounded API routes](../backend/app/api/evidence.py) share existing authentication, rate budget, PostgreSQL state and audit. No new container, schema, graph/vector service, broker or inference endpoint.
- Snapshot selection uses one highest authorized linked release per source; correction history is retained without duplicate totals. Withdrawals invalidate later reads/cursors. Existing 27 RF inputs and scientific behavior are unchanged; corrected declarations remain visibly separate from immutable case inputs.
- [Concrete architecture, parameters, limits and acceptance](PHASE3_3_RETRIEVAL_ANALYTICS.md). Regulatory corpus/LLM/provider/investigator/frontend work remains later scope.
## Phase 3.4 - Implemented reference boundary; publication gated

```mermaid
flowchart LR
    Official[Allowlisted official sources] --> Curated[Curated local UTF-8 XML / HTML / text]
    Curated --> Hash[Bounded full-section parser and SHA-256 manifests]
    Hash --> Versions[(Immutable PostgreSQL source versions / chunks)]
    Human[Authorized human source and release approval] --> Release[(Approved release / historical context / grants)]
    Versions --> Release
    Case[Authenticated current case scope] --> Read[Case and context authorization]
    Release --> Read
    Read --> Filter[Approval / withdrawal / scope / date filters]
    Filter --> FTS[PostgreSQL GIN lexical top-five or exact section]
    FTS --> Verify[Exact hash / locator verification and atomic read audit]
    Verify --> API[Bounded legal-context citations]
```

- Additive migration 0013, ten tables; no new service, model, frontend, embedding store or LLM. Reuse current actor/case authorization, safe API guards and audits. Historical scope: U.S. bank / English / November 2, 2026; knowledge cutoff November 4.
- Runtime never fetches URLs. Curator admission, source approval, release publication, explicit access and server configuration are separate operations. No official source is currently approved/published. Unconfigured authorized retrieval returns `unavailable`; FinCEN historical validity remains blocked.
- Citations identify exact immutable release/version/chunk/UTF-8 text with authority and limitations; they cannot assert a customer violation or authorize a case action. [Implementation and limits](PHASE3_4_REGULATORY_KNOWLEDGE.md), [human approval dossier](PHASE3_4_APPROVAL_DOSSIER.md).
## Phase 3.5.1 deterministic investigation foundation

- Implemented a separate PostgreSQL evidence-only coordinator/worker, immutable input manifests and packets, and raw-record numeric/reference verification. Reuse Phase 3.3 authorized projections/analytics and stored Phase 2 assessments; no new scoring, provider, regulatory lookup or frontend.
- Requester/case/source authority and revisions bind every run; publication and later disclosure recheck them. Separate purpose-bound worker identity, bounded steps/deadlines/leases/retries, idempotent intent bindings and atomic audit/result/job publication. Migration 0014 adds five tables; local demo deployment is unchanged.
- [Contracts, data flow, operational bounds, verification and exclusions](PHASE3_5_1_EVIDENCE_COORDINATOR.md). This is a deterministic evidence foundation, **not a validated AI investigator**; regulatory and provider approval gates remain independent.

## Phase 3.5.2 provider-neutral draft stage

- Optional PostgreSQL child jobs consume the existing independently verified packets; the existing coordinator remains the sole evidence admission/retrieval/financial-verification boundary. Migration 0015 adds six immutable intent/attempt/usage/result and queue tables. No broker, new database, frontend or public API is introduced.
- Only a fixed deterministic fake is registered, behind a default-off simulation setting. No real adapter or provider egress exists. A secret-free Linux subprocess enforces byte/time/resource limits. Current case/source and revision fences apply before processing and atomic publication/disclosure; interrupted attempts retain durable conservative budget reservations.
- Strict structured selection, exact numeric/reference validation and server-assembled factual summaries separate source observations, calculations, RF/SHAP signals, uncertain hypotheses and absent human conclusions. Human semantic/legal review is not replaced by structural verification. [Data flow and live-provider prerequisites](PHASE3_5_2_LLM_INVESTIGATOR.md).
# Upload workspace update — 2026-11-18

- Additive migration `0019_upload_sessions` persists per-user selection and upload provenance relationships; existing import rows determine uploaded-case membership.
- Cases is scoped server-side to the selected session. Historical sessions and model/evidence/audit records remain retained. See [upload workspace behavior and contracts](UPLOAD_SESSIONS.md).
# Navigation reliability update — 2026-11-18

- Separate HTTP request accounting from batch admission using existing durable originated jobs under the existing actor lock. No schema migration or additional service.
- Missing-source investigation screens show one readiness card, with detailed tools/history available on explicit expansion. [Details](UX_RELIABILITY_FOLLOWUP.md).
# Candidate 0023: durable regulatory start

- See [the final integration gate](FINAL_INTEGRATION_DEMO_GATE.md). The existing start API persists a bounded query intent with its parent/child jobs; the worker freezes permitted context only after verified parent completion and before provider reservation.
- Existing immutable binding, reference/numeric verification, leases, source revocation and human review remain authoritative. Retries reuse the original context and deadline.
- Candidate 0023 is not installed in the running application. Native Linux/PostgreSQL acceptance, qualified source approval, exact grounded-request approval and genuine Claude/browser verification remain pending.
