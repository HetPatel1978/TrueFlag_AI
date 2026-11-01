# Phase 2 — AML risk intelligence integration plan

**Phases 2.1-2.7 implemented and verified locally:** approved scoring/policies/SHAP, immutable persistence, durable bounded Linux jobs and [protected assessment APIs](API_ASSESSMENTS.md). Workbench, operational monitoring and production acceptance remain pending; ingestion does not automatically score and model results cannot dismiss cases.

## Confirmed retained evidence

All 25 staged artifact/reference identities match `assets/local/baseline/baseline.manifest.json`. Phase 1 only hashed the model; Phase 2.1 verified loading. Phase 2.2 scores all 4000 saved evaluation records through the unchanged fitted pipeline with maximum absolute error 0.0 and zero mismatches. No training, policy or SHAP execution occurs in Phase 2.2.

Phase 2.3 independently verifies frozen policy settings and all 12000 saved routes/audit traces against actual RF scores: zero mismatches or retained/dismissed total differences. Invalid inputs/evaluation failures return manual-review recommendations with failed status and no successful-retention/dismissal credit.

Phase 2.4 verifies all 4000 actual SHAP explanations against original approved outputs, with zero encoded/grouped/base/score differences and maximum reconstruction residual 3.1086244689504383e-15. A new general-purpose authorization-gated snapshot adapter replaces UI/cohort-bound loading; original references remain private and unchanged. Actual SHAP runs in Linux because Windows Application Control blocks the pinned native DLL.

| Item | Exact reference |
|---|---|
| Fitted pipeline | `assets/local/baseline/model/selected_pipeline.joblib` |
| Model identity | `20261018_183648_RF`, RF_base; SHA-256 `ea0806d579345d7085c00d26c188805e74de574028bda4a4573222b06e739917` |
| Predictor contract | `assets/local/baseline/contracts/predictor_contract.json`; SHA-256 `97ec1a8c39bb368621609ea66d1a652179dee8a1c910bc7c14c1b3ff81f72747` |
| Frozen policies | `assets/local/baseline/contracts/selected_policy_settings.json` |
| Replay fixtures | `assets/local/baseline/validation/final_evaluation_predictions.csv` (4000 rows), `decision_traces.csv` (12000 rows), retained cleaned synthetic CSV |
| SHAP implementation | `assets/local/baseline/reference/extensions/src/{explain,verify_explanations,case_inputs}.py` |
| Compatible serialized classes | `assets/local/baseline/reference/research/src/trueflag/`; preserve module names including `trueflag.model_feasibility.TrainingScopeGuard` |

RF remains 300 trees/minimum leaf size 5. The supplied explanation loader is coupled to an approved HTML hash and exactly 4000 existing cases; **it is a reference, not a general-purpose live-case service**. Separate numerical verification does not repair the original hidden UI attribution payload's historical provenance.

## Boundaries and proposed interfaces

| Component | Inputs → outputs | Required authority / failure behavior |
|---|---|---|
| Trusted loader | Configured private artifact and allowlisted identities → fitted pipeline handle | Verify model/code/contract/version before deserialization; no client-supplied path/pickle; refuse startup/readiness on mismatch |
| Input adapter | Persisted alert ID, immutable input snapshot/hash, contract → ordered 27-column DataFrame | No SAR/notes/IDs/priority/split fields; JSON missing income → native NaN only for RF, zero preserved; do not fit/scale/impute |
| Scorer | Verified pipeline + ordered snapshot → positive-class score or typed failure | Use complete pipeline `predict_proba`; resolve `classes_ == 1`; require finite score in [0,1]; never infer crime/calibration |
| Policy evaluator | Score/status, original KYC, frozen policy ID/mode → recommendation + trace | Implemented deterministic rules; failure yields `manual_review`/failed with no successful-retention/dismissal credit; every output requires human decision |
| Explanation adapter | Approved RF/preprocessor, same snapshot, score → verified feature contributions or unavailable status | Implemented exact SHAP and independent checks; host authorization before/after; unavailable payloads contain no contributions. Internal persistence, bounded worker and protected APIs wired; workbench pending |
| Assessment persistence | Request identity, versions, score/failure, recommendations, explanation references → immutable assessment ID | Atomic result/audit write, safe duplicate submission, permission-checked retrieval; no case closure or assignment mutation |

Implemented protected API: authenticated `POST /api/v1/cases/{case_id}/assessments` with an idempotency key and allowlisted mode; `GET /api/v1/cases/{case_id}/assessments/{assessment_id}` with the same case scope as current reads. Job execution is an internal worker capability, never an unprotected model-call endpoint. Submission uses the same current assigned-analyst/workspace-manager scope as Phase 2.5. See API_ASSESSMENTS for the exact asynchronous contract and read endpoints. Reads must recheck current case access after reassignment.

Request envelope: schema version, assessment/request IDs, case/alert IDs, snapshot/hash, model SHA/version, predictor-contract SHA/version, policy SHA/version and requested mode. IDs/policy metadata are alignment fields, never predictors. Worker accepts only validated trusted internal requests. Result envelope: execution status, positive score or null, processing reason code, per-mode recommendation/trace, explanation status/reference, provenance and timings. No raw exception strings in public results/logs.

## Runtime and preprocessing dependencies

- Separate Python 3.11 scientific runtime using `backend/ml-requirements.txt`: numpy 2.3.5, pandas 3.0.1, scikit-learn 1.9.0, scipy 1.17.0, joblib 1.5.3, threadpoolctl 3.6.0, SHAP 0.51.0 and pinned associated packages.
- API package remains `app`; reserve the serialized `trueflag` namespace inside the worker. Mount only approved local artifacts read-only; no implicit reads of the teammate workspace or private UI.
- Use recorded predictor order and fitted encoders. Unknown categories follow the fitted encoder; native missing income remains native. Do not change global income handling, add predictors, calibrate, fit, tune or replace the RF.
- Confirmed by Phase 2.1 fitted-object inspection: one-hot columns are `state` **and** `kycRiskScore`; numeric passthrough contains the other 25 predictors, including income. This yields 41 encoded features; preserve the actual fitted configuration.
- Bound worker concurrency, timeouts and queue size. A durable assessment/job record with lease/retry state can start in PostgreSQL; Kafka, multiple agents and a dedicated model server are not prerequisites.
- Teammate code redistribution rights remain unresolved. Keep reference code/models private and local; obtain rights before packaging third-party implementation into a shared image/repository.

## Frozen recommendations — never automatic case disposition

| Mode | Exact threshold / rule |
|---|---|
| Efficiency | Retain recommendation at score >= `0.19088491043724937` |
| Balanced | Retain recommendation at score >= `0.16040515630453706` |
| Coverage | Balanced threshold plus every successfully processed KYC 3–6 case |

KYC 0–2/3–6 is project-defined Standard/High. Only Coverage has a priority override. Equal scores stay together. Store a below-threshold outcome as a **system recommendation**, not a workflow dismissal. Every case remains reviewable with unchanged human status/disposition. No automatic suppression, closure, filing, training-label update or feedback-driven retraining.

## Explanation contract

- Reuse the documented exact TreeSHAP method: `tree_path_dependent`, `model_output="raw"`, `approximate=False`, additivity checks enabled; validate that this classifier's output reconstructs the positive `predict_proba` score.
- Verify fitted encoding dimensions/class order and native NaN tree routing; group encoded columns back to exactly 27 original fields. Grouped encoded contributions are not a separately calculated group-level Shapley game.
- Preserve full precision, explicit missing state and sign; rendering alone may round. Model-score explanations and policy decision traces remain separate.
- Saved-score tolerance: absolute 1e-12, relative 0; attribution reconstruction: absolute 1e-6, relative 0. A stale/missing/unverified explanation returns unavailable, never a fabricated rationale.
- Store model/input/contract/method/library and generator/verifier identities. Approval to show detailed explanations in a future UI requires browser acceptance; old hidden payloads are not promoted as verified.

## Persistent assessment design (Phases 2.5-2.7 implemented; workbench pending)

- Reuse `ModelScore` for completed score/failure records and `Decision` for versioned policy recommendations; preserve their existing processed/failed semantics. Keep pending/running/retry state in a separate assessment/job entity instead of inserting a fake pending score.
- Implemented: versioned assessment ID linking alert/case, current actor, input fingerprint, model/policy/contract identity, immutable SHAP, timing and atomic audit; no human workflow mutation. See migration 0004 and the Phase 2.5 contract.
- Completed-result publication is atomic and idempotent using a global run ID and actor-scoped hashed key. Durable worker publication, leases and failed attempts are implemented in Phase 2.6; never key only by case/model.
- Existing ingestion input hashes use exact numeric canonicalization; historical explanation hashes use recorded source lexemes. Retain these as distinct, named provenance contracts; do not silently overwrite/reinterpret one as the other.

## Acceptance gates before enabling assessment requests

1. Verify exact artifact and dependency versions; reject changed hashes, unsupported modules/classes and wrong positive-class ordering. Prove no training/fit is invoked on the retained model.
2. Validate every supported input and failure boundary: complete 27 fields/order, null versus zero income, finite values, KYC boundaries, unknown state category and forbidden label/metadata fields.
3. Replay all **4000** retained reference predictions at fixed tolerance; compare all **12000** frozen routes, including threshold equality and Coverage overrides. Replay is identity evidence on previously exposed synthetic records, not new independent evaluation.
4. Independently validate explanation score/additivity/grouping/hash contracts, native missing-income behavior, order/batch stability and negative/stale payloads. Do not suppress additivity errors or repair residuals.
5. Persist score, recommendation, failure and provenance records atomically. Test duplicate submissions, worker retries/crashes, rollback, stale input/result rejection and restart recovery.
6. Re-run case IDOR, reassignment, role revocation, failure logging and sensitive-data tests for every new endpoint. Case membership is not permission to load arbitrary private artifacts.
7. Simulate unavailable worker/model, timeout, malformed result and failed explanation. Keep case visible/manual review required; no false successful-capture or dismissal credit.
8. Demonstrate that low-score recommendations do not change case state/visibility/disposition; human decision workflow remains separate. No performance or calibrated-risk claims beyond available evidence.

**Phases 2.1-2.7 accepted locally. Proposed next subphase, after a new request:** assessment API/worker operational monitoring and bounded load/recovery acceptance. Frontend, LLM/RAG and consequential human decisions are separate later work.
