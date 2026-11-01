# Phase 2.2 — RF scoring and identity regression

Starting point: clean `bce4f78`, branch `codex/project-initialization`. Scope is an internal Python scorer and read-only regression. No inference HTTP endpoint, ingestion hook, deployed worker, persistence, policy execution or SHAP is added.

## Interfaces

| Interface | Contract |
|---|---|
| `backend/trueflag_ml/scoring.py::RFScoringService(artifact_root=None)` | Load once through the Phase 2.1 SHA-verified loader; deployment-owned root only. Missing/incompatible assets raise sanitized `ModelLoadError` before a service is available |
| `score_one(record_id, features)` | One strict 27-feature record; returns `ScoreResult` |
| `score_batch(records)` | Sequence of `ScoringRecord(record_id, features)`, 1–1000 rows; returns an ordered tuple of results |
| `ScoreResult` | `record_id`, full-precision `score` or null, `model_version`, model SHA, `processing_status`, reason code and positive-class label |
| `backend/trueflag_ml/regression.py` | Verified reference loading, explicit ID/label alignment, historical CSV conversion, bounded scoring and comparison |
| `scripts/verify_rf_scoring.py` | Fixed approved evaluation, aggregate JSON only; nonzero exit on integrity/ID/scoring/numeric failure |

Record IDs are unique within a batch, 1–128 ASCII characters using the existing source-ID character set. Empty/oversized batches, malformed envelopes/IDs and duplicate IDs raise `ScoringInputError` before prediction. IDs are alignment metadata and never enter the 27 predictors. Repeated calls are read-only computations; there is no persistence or idempotency ledger in this subphase.

## Scoring behavior

- Reuse `LoadedPipeline.feature_frame` and the existing `AlertFeatures` schema. Reject labels/notes/extra/missing fields, numeric strings, booleans, nonfinite numbers and unsupported KYC. Preserve recorded state values; the fitted encoder handles unknown state categories.
- Invoke the full original `pipeline.predict_proba`, including its fitted `state`+`kycRiskScore` encoder and numeric passthrough. No fitting, scaling, imputation, calibration, rounding, clamping or model-parameter changes occur.
- Confirmed class mapping: fitted `classes_ == [0,1]`; extract the position of label **1**. Evidence: private `reference/research/src/trueflag/model_selection.py::final_population/score` builds targets from integer `SAR` and extracts `list(p.classes_).index(1)`; `model_feasibility.py::load_development` likewise selects `SAR` as target. Class 1 is the project's SAR-positive target, without a calibrated criminal-risk claim.
- Capture the verified class mapping at initialization and fail if it changes. Require correctly shaped floating probability output; every accepted row must be finite, within [0,1], and sum to 1 within absolute 1e-12.
- An invalid feature row gets `failed / invalid_features / score=null` and never reaches inference; valid rows in the same batch still score. Malformed output rows get `invalid_model_output`. A prediction exception/warning fails the valid sub-batch with `inference_failed`; no row retry or fabricated score occurs. Changed classes produce `model_state_invalid`.
- Keep the original RF `n_jobs=1`. A process-wide scoring lock coordinates temporary single-thread numeric limits and warning filters across service instances; filters/limits restore on exit. Warnings become sanitized failures, and customer values/exception messages are never logged. This is bounded synchronous CPU work; queues/timeouts/deployment remain later integration.

## Reference integrity and alignment

| Private reference | Reviewed SHA-256 | Coverage |
|---|---|---|
| `validation/final_evaluation_predictions.csv` | `3803602f70fc5a1b31e5e38b7d7019ed034c85284853f18bd072558d71f004e2` | Exactly 4000 RF/processed saved predictions |
| `data/datarobot_cleaned_v1.csv` | `17244da02f7262bdf3c3b582671fa4d3675681489c1dfc23f1ae23e415da173f` | 10000 source records; select the exact 4000 evaluation IDs |

Both files are read into bounded, hash-verified snapshots; an editable artifact-side manifest cannot authorize replacements. No dataset is copied into Git, reports or test output.

1. Reject duplicate/invalid reference IDs and duplicate source IDs, including unselected source records.
2. Require all 4000 evaluation feature records and matching source/reference SAR metadata; the other 6000 source records are intentionally outside this evaluation.
3. Select only the 27 approved predictors. For historical CSV transport, reproduce the original `pandas.to_numeric(errors="raise")` conversion and missing-income token handling, then validate through the unchanged strict schema. Labels, IDs, notes and partition metadata never become predictors.
4. Score in bounded batches, match results by ID independently of output order, reject duplicate/missing/unexpected result IDs and wrong model/class identities.
5. Compare every successful score at **absolute tolerance 1e-12, relative tolerance 0**. Processing failures count as mismatches. No model/reference correction, threshold change or row exclusion is permitted.

## Actual acceptance

| Check | Executed result |
|---|---|
| Standalone 4000-record replay | Matched **4000**, scored **4000**, maximum absolute error **0.0**, mismatches **0**, processing failures **0** |
| Missingness in evaluation | **87** missing-income records and **22** zero-income records retained distinctly |
| Scientific ML suite | **81 passed, 0 failed, 0 skipped**: 34 retained loader tests + 47 scoring/alignment/failure tests |
| Changed batch boundaries | All 4000 scores match at batch sizes 1000 and 137 |
| Determinism/ordering | Repeated, reversed, single-versus-batch and concurrent calls verified with the actual fitted RF |
| Backend/PostgreSQL regressions | **153 passed, 0 failed, 0 skipped** |
| Backend/SQLite regressions | **145 passed, 0 failed, 8 PostgreSQL-only skips** |
| Service-runtime ML boundaries | **50 passed, 0 failed, 31 private/scientific-runtime skips**; CI configured to run the same suite |

Positive scoring/replay acceptance uses the actual model and reference records. Fault injection is confined to negative tests or wrappers that invoke the real fitted pipeline. The existing Starlette TestClient/httpx deprecation remains non-blocking. CI lacks private assets/scientific runtime; no remote CI execution or new generalization evaluation is claimed. This replay proves retained numerical identity.

```powershell
.\.venv-ml\Scripts\python.exe -B scripts/verify_rf_scoring.py
.\.venv-ml\Scripts\python.exe -B -m unittest discover -s backend/ml_tests -v
```

## Pending boundary

Proposed Phase 2.3, after separate authorization: pure Efficiency/Balanced/Coverage recommendation evaluation and 12000 saved-route identity checks. No automatic dismissal, suppression, closure, filing or case-visibility mutation. Persistence, worker/API integration and SHAP retain their separate acceptance gates.

Technical reference: [RandomForestClassifier probability class ordering](https://scikit-learn.org/1.9/modules/generated/sklearn.ensemble.RandomForestClassifier.html).
