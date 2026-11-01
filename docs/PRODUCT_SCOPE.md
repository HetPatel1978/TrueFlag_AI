# Product scope

**TrueFlag AI — Intelligent AML Investigation Platform**

## Five-week MVP

| Capability | Intended behavior | Initialization status |
|---|---|---|
| Alert ingestion | Validate synthetic alert envelopes and exactly the approved predictors; deduplicate inputs; reject invalid requests | Admin-only single-alert API, atomic alert/case/audit persistence and durable idempotency implemented; batch/quarantine workflows remain future work |
| RF scoring | Load trusted fitted preprocessing/RF in isolated runtime; preserve full-precision positive-class score | Secure loader and pure single/batch scorer implemented; all 4000 saved scores match (maximum error 0.0); internal immutable assessment storage verified; bounded worker implemented; API integration pending |
| Routing | Versioned Efficiency/Balanced/Coverage semantics; failed cases require review | Pure verified policy engine and all 12000 saved route/audit traces matched; immutable recommendation storage; human-controlled results only, no workflow/API integration |
| Explainability | Verified model-score contributions plus separate deterministic routing rationale | Authorization-gated exact SHAP library, 41→27 grouping, ranking and 4000-reference parity verified in Linux; immutable authorized storage verified; bounded worker implemented; HTTP integration pending |
| Investigation | Evidence-grounded, source-cited drafts; explicit abstention; human confirmation | Provider protocol only; Week 3 |
| Regulatory RAG | Approved jurisdiction/institution/as-of corpus; versioned passages and access filters | Planned; no corpus/provider configured |
| Case management | Assignment, notes, state transitions, approval, evidence links, reproducible reports | Scoped case list/detail, pagination/filtering/sorting and protected versioned assignment implemented; review/approval/report workflows pending |
| Security | Authentication, server RBAC, input validation, audit records, deployment controls | Three-role case authorization, persistent login throttle, bounded bodies, safe request/failure logs and transactional assignment audit verified; deployment hardening pending |
| Monitoring/feedback | Health, readiness, failures, queue metrics and reviewed outcomes | Liveness/readiness implemented; remaining work pending |

## Boundaries

- Synthetic inputs only; no customer or institution production data without explicit access approval.
- Deployment-oriented demonstration, not certified enterprise banking software or evidence of regulatory compliance.
- Start as an alert-intelligence overlay; no autonomous suppression, case closure, regulatory advice or SAR filing.
- Do not alter the retained baseline features, preprocessing, thresholds, labels or experiment artifacts.
- No claim of independent validation, calibrated criminal risk or measured analyst-time savings from existing results.
- Source rights, external provider approval and recipient browser acceptance remain explicit gates.

## Future expansion

Graph/entity intelligence, behavioral anomaly models, stream-based transaction monitoring, enterprise integrations, multiple specialized agents, tenant isolation and advanced MLOps require separate data, scope and acceptance. A multi-agent system is not an MVP dependency.

## Product acceptance

- Demonstrate one permitted synthetic alert through validated ingestion, scoring, policy trace, cited evidence, human review, persisted approval and report.
- Unauthorized access and cross-case access are rejected server-side; retries do not duplicate consequential actions.
- Model/evidence/provider failures preserve review access and never produce fabricated evidence or silent dismissal.
- Publish measured limitations and actual test evidence, with no placeholders presented as completed functionality.
