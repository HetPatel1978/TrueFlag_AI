# Product scope

**TrueFlag AI — Intelligent AML Investigation Platform**

## Five-week MVP

| Capability | Intended behavior | Initialization status |
|---|---|---|
| Alert ingestion | Validate synthetic alert envelopes and exactly the approved predictors; deduplicate inputs; quarantine failures | Schema only; Week 1 API work pending |
| RF scoring | Load trusted fitted preprocessing/RF in isolated runtime; preserve full-precision positive-class score | Baseline staged privately; Week 2 integration pending |
| Routing | Versioned Efficiency/Balanced/Coverage semantics; failed cases require review | Original policies staged; service pending |
| Explainability | Verified model-score contributions plus separate deterministic routing rationale | Reference code staged; service pending |
| Investigation | Evidence-grounded, source-cited drafts; explicit abstention; human confirmation | Provider protocol only; Week 3 |
| Regulatory RAG | Approved jurisdiction/institution/as-of corpus; versioned passages and access filters | Planned; no corpus/provider configured |
| Case management | Assignment, notes, state transitions, approval, evidence links, reproducible reports | Initial relational schema; Week 4 |
| Security | Authentication, server RBAC, input validation, audit records, deployment controls | Account verification/RBAC implemented; hardening progressive |
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
