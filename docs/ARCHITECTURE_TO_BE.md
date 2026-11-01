# Target architecture — five-week MVP and later expansion

This is a target, not an implementation claim. Initialization status is in PRODUCT_SCOPE and SETUP_STATUS. Use a modular service with a separately pinned scientific worker; introduce distributed systems only when justified.

Current acceptance is in [IMPLEMENTATION_STATUS](IMPLEMENTATION_STATUS.md). Phases 2.1-2.6 include verified RF/policies/SHAP, immutable assessments and [durable PostgreSQL jobs with a controlled Linux worker](PHASE2_6_DURABLE_JOBS.md). HTTP/workbench wiring and operational deployment acceptance remain pending; ingestion does not invoke ML.

| Boundary | Implemented now | Pending |
|---|---|---|
| API/security | JWT/Argon2, analyst/supervisor/admin, per-case SQL scope, body limits, request IDs, persistent login throttle | Enterprise IAM, tenant isolation, perimeter controls |
| Case service | Scoped list/detail, filtered pagination/sorting, versioned assignment and transactional change audit | Notes, approvals, reports and full review state machine |
| Data | Synthetic ingestion, durable receipts, 13 domain tables, immutable assessments, PostgreSQL jobs and atomic job/result/audit completion | New sources, admission/retention and least-privilege SQL roles |
| UI | React account verification, including supervisor identities | Case/session/assignment workbench |
| Scientific worker | Opt-in Linux worker, isolated bounded child, renewable leases/fencing, recovery and retries using approved libraries | Protected submission APIs, operational monitoring and throughput acceptance |
| Policy engine | Frozen deterministic recommendations, 12000-route parity and immutable linked decision records | Authorized HTTP/workflow integration; all recommendations require human decision |
| Explanation service | Exact SHAP, 41-to-27 grouping, independent checks, immutable storage and killable bounded worker execution | Authenticated HTTP/workbench wiring |

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
