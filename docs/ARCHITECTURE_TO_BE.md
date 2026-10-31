# Target architecture — five-week MVP and later expansion

This is a target, not an implementation claim. Initialization status is in PRODUCT_SCOPE and SETUP_STATUS. Use a modular service with a separately pinned scientific worker; introduce distributed systems only when justified.

```mermaid
flowchart TB
  subgraph Frontend[React + TypeScript frontend]
    UI[Analyst investigation workspace]
    Review[Human review / approval / report]
  end
  subgraph Boundary[Security and API boundary]
    Auth[Authentication + server-enforced RBAC]
    API[Versioned FastAPI APIs]
  end
  subgraph Backend[Modular backend services]
    Ingest[Alert ingestion / validation / idempotency]
    Prepare[Customer references / exact feature contract]
    Cases[Case workflow / concurrency / permissions]
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
| Cases/review | Assignment, state transitions, optimistic concurrency, approvals and authorized reporting |
| Retrieval/corpus | Evidence IDs, permissions, jurisdiction, institution scope, source hashes and as-of context |
| AI coordinator | One bounded provider workflow, source-cited draft or abstention; no autonomous consequential write |
| Audit/storage | Separate observations, scores, decisions, reviews and source labels with transactional linkage |
| Monitoring/evaluation | Operational failures and drift; reviewed offline experiments and explicit model promotion |

Preserve the baseline namespace in the worker; the API uses `app`. Do not add graph/behavioral features to the frozen 27-predictor pipeline. A graph database, Kafka, Kubernetes and multiple agents are not prerequisites for this MVP.
