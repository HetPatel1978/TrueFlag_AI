# Phase 2.1 — secure model loader and acceptance

Status: implemented and verified locally, starting from `635ec07` on `codex/project-initialization`. Scope ends at trusted loading, fitted preprocessing checks and feature validation. No live scoring API, training, model replacement, policy execution, SHAP generation, assessment persistence or automatic dismissal was added.

## Interfaces and trust boundary

| Interface / file | Responsibility |
|---|---|
| `backend/trueflag_ml/loader.py::load_approved_pipeline(artifact_root=None)` | Internal deployment-owned bundle directory; fixed filenames and approved hashes; returns fitted internal handle or sanitized `ModelLoadError` |
| `backend/trueflag_ml/trust.py` | Reviewed model/version, five artifact/source hashes and exact runtime versions; no caller-provided expected hash |
| `LoadedPipeline.feature_frame(mapping)` | Reuse existing `AlertFeatures` strict validation; reject missing/extra/label fields; order exactly 27 inputs; JSON null income becomes native NaN, zero remains zero |
| `scripts/verify_model_loader.py` | Real read-only load, synthetic preprocessing validation, bounded metadata output and nonzero exit on failure |
| `scripts/verify_baseline.py` | Existing offline replay utility now reuses the secure loader; no broad research `sys.path` import or duplicate deserializer. Replay was not run in Phase 2.1 |
| `backend/ml_tests/test_loader.py` | Standard-library unittest boundary tests and real private-artifact acceptance |

Default bundle: ignored `assets/local/baseline/`. Only five fixed files are read: `model/selected_pipeline.joblib`, `contracts/predictor_contract.json`, and private `trueflag/{__init__,datarobot_cleaning,model_feasibility}.py` under `reference/research/src/`. The editable staged manifest cannot approve different bytes. All original 25 staged identities are preserved.

## Loading sequence

1. Resolve bundle paths within the selected directory, reject missing/unreadable/escaping files, bound reads (8 MiB model, 256 KiB per other file), and compare SHA-256 to reviewed application constants.
2. Require 64-bit CPython 3.11 (patch releases allowed); verify six scientific distribution versions and five shared-schema dependency versions against `trust.py`. SHAP is not imported or required by this loader; its later integration has separate acceptance.
3. Check the retained predictor order/exclusions against the existing ingestion schema and its contract hash. Do not rewrite the original contract's historical undecided income-handling metadata; fitted RF inspection establishes the actual native-NaN behavior.
4. Under a loader lock, reject existing `trueflag` modules, register only the three hash-verified compatibility modules, and execute the verified source snapshots with no package search path. Preserve original serialized class names; always clean up temporary namespace entries.
5. Deserialize the verified model snapshot from `BytesIO`, with no memory mapping or second disk open. Treat scikit-learn inconsistent-version warnings as errors.
6. Verify exact pipeline steps, historical single fit and 6000-row training-scope hash, fitted column transformer/encoder and all 300 trees, RF minimum leaf 5, positive class order `[0,1]`, 27 inputs and 41 encoded features.
7. Transform two generated synthetic rows to verify income remains NaN versus zero. The actual fitted encoder handles `state` and `kycRiskScore`; the other 25 columns pass through numerically. No prediction or fit is called.

The returned frozen descriptor holds an internal mutable fitted estimator; it is never serialized to an API response. Load once per future scientific process. Temporary compatibility modules are removed after loading; re-pickling or sending the handle between processes is outside this interface—each process must load its own verified artifact.

Joblib loading executes trusted serialized code. Hash checks establish identity of this reviewed baseline; Python namespace/environment isolation does not provide an OS sandbox. The API never imports the loader, holds no fitted model, and exposes no model upload/path/hash control. Future worker deployment still requires approved read-only mounts, bounded resources and restricted credentials/network. Private teammate source remains untracked and unchanged; shared packaging requires source-use rights.

## Failure behavior

| Code group | Handling |
|---|---|
| `artifact_missing`, `artifact_unreadable`, `artifact_location_invalid`, `artifact_integrity_failed` | Stop before source execution/deserialization; no path/source content in error |
| `python_incompatible`, `dependency_missing`, `dependency_incompatible`, `feature_contract_invalid` | Stop before compatibility module execution/deserialization |
| `module_namespace_conflict` | Refuse conflicting package state, preserving preexisting modules |
| `pipeline_load_failed`, `pipeline_incompatible`, `preprocessing_incompatible` | No usable handle returned; clean temporary imports; suppress underlying exception text |
| `feature_input_invalid` | Reject input without values, labels or customer content in the message |

## Actual verification

| Check | Result |
|---|---|
| Scientific environment `.venv-ml` unittest | **34 passed, zero skipped/failed**; uses actual approved fitted model |
| Standalone loader verification | PASS; 27 predictors, 41 encoded features, 300 fitted trees; zero fits/predictions or dataset reads |
| Existing backend/PostgreSQL regression | **153 passed, zero failed** |
| Existing backend/SQLite regression | **145 passed, 8 PostgreSQL-only skips, zero failed** |
| Service environment loader boundary suite | **19 passed, 15 private/scientific-runtime skips**, zero failed; same boundary command added to CI |
| Ruff lint / format | Passed for backend and scripts |
| Scientific dependency consistency | `pip check`: no broken requirements |

Real-artifact success is not mocked. Tests cover modified/truncated model, changed contract/source, missing artifacts, arbitrary pickle rejection despite a forged manifest, Python/dependency mismatches, namespace conflicts/cleanup, changed class ordering, strict features, unknown state and missing versus zero income. One race test wraps the real deserializer, replaces the temporary disk artifact after hashing, and confirms that only the verified in-memory bytes load. Fit/predict entry points are blocked in a real-load test. Negative fault simulation does not substitute a fake fitted model for success.

Reproduce after private staging:

```powershell
.\.venv-ml\Scripts\python.exe -m pip install -r backend/ml-requirements.txt
.\.venv-ml\Scripts\python.exe -B scripts/verify_model_loader.py
.\.venv-ml\Scripts\python.exe -B -m unittest discover -s backend/ml_tests -v
```

CI has no private artifact/runtime and cannot independently prove real-model acceptance. No remote CI execution is claimed. The existing Starlette TestClient/httpx deprecation remains non-blocking in backend regressions. No 4000-score/12000-route replay was performed during this loading-only task.

## Next authorized boundary

Phase 2.2 is pending a separate request: pure positive-class scoring through the verified full pipeline and the 4000 saved-score identity regression at absolute tolerance 1e-12 / relative 0. Live endpoints, background jobs, persistent assessments, policies and explanations remain subsequent work.

Engineering references: [Joblib load security and file-object interface](https://joblib.readthedocs.io/en/stable/generated/joblib.load.html), [scikit-learn persistence compatibility](https://scikit-learn.org/stable/model_persistence.html).
