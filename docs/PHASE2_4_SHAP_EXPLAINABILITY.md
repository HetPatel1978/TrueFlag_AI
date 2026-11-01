# Phase 2.4 — verified RF explanations

Starting point: clean `22c0afb`, branch `codex/project-initialization`. Exact SHAP explanations are implemented as a reusable internal service. No HTTP endpoint, deployed worker, database mutation, automatic dismissal/closure or baseline retraining is added.

## Method and interfaces

| Component | Implemented responsibility |
|---|---|
| `backend/trueflag_ml/explainability.py::ExplanationService(authorize, artifact_root=None)` | Require a trusted host authorization callback; independently load approved RF pipelines for explanation and existing score-service comparison; validate pinned SHAP runtime |
| `explain_one(record_id, features)` / `explain_batch(records)` | Strict 27-feature snapshots, unique validated IDs, batches of 1–64, per-record authorization before work and again before disclosure |
| `explanation_contract.py` | Immutable result/method/contribution structures and separately named, record-bound rational input hash |
| `explanation_verification.py` | Independent input/provenance, class/score, weighted-root base, encoded mapping, aggregation, reconstruction and ranking checks; no generator validation function imported |
| `explanation_reference.py` / `explanation_regression.py` | Verify approved historical outputs and compare all 4000 cases by technical record ID, with explicit original input-hash handling |
| `scripts/stage_explanation_reference.py` | Explicit staging of three hash-approved private reference files into ignored `assets/local/explanation_reference/`; no teammate modifications or baseline-manifest rewrite |
| `scripts/verify_shap_explanations.py` | Full actual-artifact acceptance; aggregate output only; failures exit nonzero |

The model remains the approved 300-tree RF. Dependencies retain the existing scientific pins, including SHAP **0.51.0**, numba **0.68.1**, llvmlite **0.50.0**, slicer **0.0.8** and cloudpickle **3.1.2**. The RF loader/scorer/policy implementations are unchanged.

- Use `TreeExplainer(forest, feature_perturbation="tree_path_dependent", model_output="raw")`, `approximate=False`, `check_additivity=True`. Background is the fitted per-node weighted training counts; no evaluation background or fitting.
- For this scikit-learn RF, the returned shape is `(rows,41,2)` with a two-value base. Verified `classes_ == [0,1]` selects SAR-positive class 1 at index 1. This `raw` output reconstructs **`predict_proba` probability**, with no logit conversion or calibration.
- Expand the actual fitted OneHotEncoder: 9 state columns, 7 KYC columns, and 25 numeric passthrough columns. Sum encoded attributions into exactly 27 original predictors. The verifier independently derives the mapping from encoded labels and the base from averaged fitted-root class proportions.
- Check every parsed tree's native missing-value defaults against the actual forest. For each batch, compare both SHAP-internal class predictions with the full fitted pipeline and the positive output with the existing scoring service. Check both class reconstructions and opposite class contributions.
- Missing income becomes native NaN only inside the model frame; zero remains zero. Missing flags and versioned input hashes preserve that distinction. JSON NaN/infinity/numeric-string inputs are rejected by the original strict schema.

Reference method evidence is retained privately in `reference/extensions/src/{explain,verify_explanations,case_inputs}.py`. Its UI/cohort-bound loader is replaced by the secure general-purpose snapshot service; its original files remain unchanged. [SHAP output-space documentation](https://shap.readthedocs.io/en/latest/generated/shap.TreeExplainer.html) distinguishes RF probability outputs from other models' raw margins.

## Results, ranking and independent verification

Verified results contain record/model/contract identities, input digest/schema, method metadata, base value, model score, 41 encoded contributions, 27 named feature contributions/directions/missing flags, a full absolute-magnitude ranking and reconstruction residual. No recorded feature values, notes or SAR labels are returned.

The compact summary follows the retained method: two largest nonzero absolute contributions, plus the strongest opposing contribution if not already selected; the remaining subtotal is explicit. Ties use original feature order. Grouping encoded attributions is **not** a separately calculated group-level Shapley game.

| Check | Absolute tolerance | Relative tolerance |
|---|---:|---:|
| Existing scorer / saved score / SHAP internal prediction | 1e-12 | 0 |
| 41→27 grouping, saved encoded/grouped/base parity, stability | 1e-12 | 0 |
| Base + encoded or grouped contributions versus score | 1e-6 | 0 |

These are the original generator/verifier tolerances; none were widened. No residual redistribution, rounding, imputation or reference correction occurs. Verification also rejects stale input/model/contract identity, wrong output/class, incomplete/nonfinite contributions, false missing flags and misleading rankings. Only independently checked candidates become `verified`; errors return `unavailable` with a reason code and empty contributions/base/score, without changing separate scoring or policy results.

An independent six-case, two-feature path-conditional Shapley test enumerates coalitions, including native NaN routing. It fits **one synthetic test-only DecisionTree**, never the project's RF or private data. Full-forest checks independently validate contracts/arithmetic/root counts and compare the retained reference allocation; they are not a second independent full-forest TreeSHAP implementation. Reconstruction alone cannot establish attribution allocation or causality.

## Authorization and runtime security

- No default allow-all callback. The trusted caller must supply current case authorization; only explicit `True` permits computation. Exceptions/denials return identical `not_authorized` outcomes before feature validation or inference. Recheck before disclosure to handle revocation during computation.
- This is a library boundary, not newly implemented enterprise IAM. Future API/worker integration must derive callbacks from server-side authenticated case scope and recheck retrieval permissions; caller-provided IDs/hashes or callbacks must never become client-granted authority.
- Strict schema, immutable scalar snapshots, record-bound hashes, SHA-verified models, encoded-map checks, bounded batches, shared scientific execution lock and sanitized exceptions/warnings prevent misleading partial results. No feature values or raw exceptions are logged.
- Windows Application Control blocks the pinned `llvmlite.dll` on this host. No host policy or dependency pin was changed. Actual SHAP acceptance runs in the local `Dockerfile.ml-verify` image: non-root, read-only filesystem/mounts, no network, no added capabilities, no-new-privileges, bounded memory/CPU/PIDs and temporary scratch space. No `.env`, host credentials or private assets enter image layers; no service is deployed or image pushed.
- SHAP describes this model's score under its path-dependence assumptions. It does not establish causality, criminal conduct or a factual explanation of money laundering; human investigation remains required.

## Actual acceptance

| Verification | Result |
|---|---|
| Full private evaluation/reference replay | **4000 matched, 4000 verified, 0 unavailable, 0 mismatches** |
| Maximum saved scorer/encoded/grouped/base difference | **0.0** for every comparison |
| Maximum independent reconstruction residual | **3.1086244689504383e-15** |
| Income coverage | **87 missing**, **22 zero**; both preserved and verified |
| Linux scientific ML/policy/SHAP suite | **178 passed, 0 failed, 0 skipped** |
| Backend/PostgreSQL regressions | **153 passed, 0 failed, 0 skipped** |
| Backend/SQLite regressions | **145 passed, 0 failed, 8 PostgreSQL-only skips** |
| Windows API-runtime library boundaries | **115 passed, 0 failed, 63 private/scientific-runtime skips** |
| Linux API container without private assets/SHAP | **96 passed, 0 failed, 82 expected private/runtime skips** |

Tests cover aggregation, correct probability space, positive class, missing/zero/unknown-state behavior, single/batch/reordered/repeated/concurrent stability, authorization denial/revocation, malformed inputs, dependency/artifact failures, tampered output, wrong class/base/mapping/ranking and sanitized errors. Existing ingestion, authorization, concurrency and rollback regressions pass. The backend Starlette TestClient/httpx deprecation remains non-blocking; native Windows SHAP execution remains an environment limitation. No remote CI run is claimed.

Three privately staged reference identities are pinned: payload **`c09c102e789e894e287f400bee444c26f9cdf9e79a686a0f811041ecb12a6a7b`**, metadata **`99e3c35b99b2c9aebb0cb80d32382976e77445914a814f83d75fe20a47fc396e`**, verification **`8195bf09bfe9d0dbb96c14b4a981321c706c97f56d556f2f8e405bd6fe179383`**. The original full report binds the payload and metadata and records saved-case PASS; new stability tests are separate from its unset fixture-stability flag. Historical policy/UI hashes are preserved as historical context, never installed as current policy or used for authorization.

Original lexical input hashes are recomputed from the hash-verified source CSV. New results use `trueflag.explanation-input.rational.v1`, bound to record ID and exact validated numeric values; this is distinct from both ingestion and original lexical hashes. No original private/UI output is rewritten or silently promoted to the frontend. All original 25 staged baseline identities remain unchanged.

```powershell
.\.venv\Scripts\python.exe -B scripts/stage_explanation_reference.py
.\.venv\Scripts\python.exe -B scripts/run_ml_verification.py --build --check tests
.\.venv\Scripts\python.exe -B scripts/run_ml_verification.py --check shap
```

## Next boundary

Proposed Phase 2.5, after separate authorization: immutable assessment/policy/explanation persistence with input/model/policy/method provenance, atomic audit and idempotency, plus permission-checked retrieval. Worker timeouts/cancellation, HTTP integration and case workflow changes remain separate later acceptance gates. Phase 2.4 stops at verified library behavior.
