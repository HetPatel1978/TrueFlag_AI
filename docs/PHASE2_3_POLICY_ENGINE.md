# Phase 2.3 — deterministic risk-policy recommendations

Starting point: clean `20a4ef2`, branch `codex/project-initialization`. Implemented as a separate pure Python component; RF loading/scoring code and the teammate's files remain unchanged. No HTTP endpoint, case mutation, assessment persistence, automatic dismissal/closure or SHAP is added.

## Frozen artifact and exact behavior

Artifact: ignored `assets/local/baseline/contracts/selected_policy_settings.json`; SHA-256 **`c530a4f71c554172a0dde4d2574f28efdc2ee860a4e32c74bd1ec548d359ac3f`**. Verify a bounded byte snapshot before parsing; no uploaded config or caller-supplied expected hash is accepted.

| Mode | Exact inclusive threshold | Priority behavior |
|---|---|---|
| Efficiency | `0.19088491043724937` | No priority override |
| Balanced | `0.16040515630453706` | No priority override |
| Coverage | `0.16040515630453706` | Retain every successfully scored High-priority case, including below threshold |

- KYC 0–2 = Standard; 3–6 = High. Whole-valued native integers/floats are supported as in the existing 27-feature contract. Booleans, numeric strings, nonfinite, fractional and unsupported KYC values fail explicitly. An optional declared priority must match KYC exactly.
- Threshold equality retains. Tied scores receive identical treatment within a mode/priority group. No rounding, fitting, calibration or threshold adjustment occurs.
- Original evidence: private `reference/research/src/trueflag/model_selection.py::run` computes `above = successfully_processed & score >= threshold`, `protect = successfully_processed & High & Coverage`, and retains `above | protect`. Its reason/flag semantics are preserved. `model_feasibility.py::policy_counts` excludes processing failures from both successful retention and dismissal credit.
- `override_reason` is present only when High-priority protection actually changes a below-threshold Coverage route. Above-threshold High cases still record protection, with no false changed-route flag.

## Internal interfaces and safety

| Interface / file | Contract |
|---|---|
| `backend/trueflag_ml/policy.py::RiskPolicyEngine(artifact_root=None)` | Load only the approved policy snapshot; deployment-owned root; `ready` and sanitized `load_failure` describe availability |
| `evaluate(score_result, policy, kyc_risk_score=..., priority_group=None)` | Accept the existing `ScoreResult` and case attributes; validate ID, model/version/SHA, positive class 1, processed status, score and priority; return `PolicyRecommendation` |
| `PolicyRecommendation` | Record reference, full-precision model score, selected mode, policy/model identities, threshold, KYC/priority, recommended route, override/reason/flags and processing status |
| `backend/trueflag_ml/policy_regression.py` | Actual RF scoring plus `(record_id, policy)` alignment against 12000 verified traces; independent totals and audit-field comparisons |
| `scripts/verify_risk_policy.py` | Aggregate-only acceptance report, nonzero exit on parity/integrity/processing failure |

The source artifact has no separate policy version field. The version is explicitly content-addressed as **`{original_model_version}:{policy_sha256}`**; original `20261018_183648_RF`, model SHA and policy SHA remain available independently. This identifies the exact frozen settings; it does not invent an upstream release number. Structured outputs support later auditing; durable audit/assessment storage remains pending.

`recommended_route` is one of:

- `retain_human_review`: threshold and/or Coverage protection recommends retention.
- `review_reduction_candidate`: the historical saved `Dismiss` outcome, represented as a recommendation requiring human authorization.
- `manual_review`: invalid input, failed scoring, unavailable/unverified policy or evaluation error. Status is `failed`, score is null, override/retention/protection flags are false; there is no successful-capture/dismissal credit.

Every result sets **`human_decision_required=true`**. No workflow consumer is enabled, and every case remains visible with unchanged status/disposition. Failed High-priority scores cannot become successful Coverage captures. Unsupported modes never default to Balanced/Standard; invalid references/modes and exception text are not echoed. Policy load failures produce an unready engine with manual-review outcomes and no fabricated verified version/threshold. Construct a new engine after correcting deployment assets; there is no silent fallback to defaults.

Rules do not load the RF, invoke inference, import NumPy/scikit-learn/joblib, read customer feature vectors or log feature values. Only score and required case metadata cross the interface. Future HTTP/worker integration must obtain scores/attributes from authorized server-side assessments; client-supplied model hashes are not proof of model execution.

## Regression and actual results

Reference: ignored `validation/decision_traces.csv`, SHA-256 **`7db5506ca2745fe99ec0230831c3e59eceea8852daabb0983aa7135f6cef33b8`**; all 12000 saved rows are processed cases. The RF scorer reproduces the 4000 underlying saved scores with **maximum absolute error 0.0**. Failure semantics are verified separately with synthetic negative tests.

- Reject duplicate/missing/unexpected IDs or modes and duplicate `(record_id, policy)` pairs, in both references and recommendations.
- Verify trace policy/model identity, exact threshold, KYC/priority, successful status, saved score alignment and schema. Compare routes, reason codes, protection/override flags, legacy review requirement and all provenance fields.
- The legacy `Retain human review`/`Dismiss` labels map explicitly to retention/review-reduction recommendations. Reference files are never edited. Route comparisons have no tolerance; score comparisons retain absolute 1e-12 / relative 0.

| Policy | Retained | Review-reduction candidates (saved dismissed) | Retained delta | Dismissed delta | Changed-route High overrides |
|---|---:|---:|---:|---:|---:|
| Efficiency | 934 | 3066 | 0 | 0 | 0 |
| Balanced | 1004 | 2996 | 0 | 0 | 0 |
| Coverage | 1460 | 2540 | 0 | 0 | 456 |

**12000 matched routes; 0 route mismatches, 0 audit-trace mismatches, 0 processing failures.** This is frozen-behavior identity validation; no new generalization or actual analyst workload claim is made.

| Executed checks | Passed | Failed | Skipped |
|---|---:|---:|---:|
| Scientific environment, full ML/policy suite | 135 | 0 | 0 |
| Existing backend/PostgreSQL | 153 | 0 | 0 |
| Existing backend/SQLite | 145 | 0 | 8 PostgreSQL-only |
| Service Python, private policy available but no scientific runtime | 101 | 0 | 34 |
| Linux API container, private artifacts absent | 82 | 0 | 53 |

Coverage includes all KYC bands, adjacent floating-point threshold boundaries, equal-score retention, monotonic retained sets, invalid score/type/priority inputs, failure/no-credit semantics, artifact tampering/missing assets, sanitized evaluation errors, deterministic/concurrent evaluation, and scientific-runtime separation. Actual artifact/replay tests establish positive acceptance; synthetic fixtures only exercise parser/validation/comparison contracts. The existing backend Starlette TestClient/httpx deprecation remains non-blocking. CI is configured for boundary tests; no remote CI execution is claimed.

```powershell
.\.venv-ml\Scripts\python.exe -B scripts/verify_risk_policy.py
.\.venv-ml\Scripts\python.exe -B -m unittest discover -s backend/ml_tests -v
```

## Subsequent progress

Phase 2.4 has since been separately authorized and verified: [exact SHAP service and 4000-reference acceptance](PHASE2_4_SHAP_EXPLAINABILITY.md). This document retains Phase 2.3's policy-only evidence. Persistent assessments, authorized HTTP/worker integration and human decision workflows remain separate later acceptance gates.
