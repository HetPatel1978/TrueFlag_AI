# Reuse manifest

Original paths are relative to sibling `../github`, or are ZIP members in `../private_handoff/main/TRUEFLAG_PRIVATE_ASSETS.zip`. Every main asset and both delivery manifests are verified before staging. The original work is never overwritten.

| Component | Original path | New path | Action | Status |
|---|---|---|---|---|
| Selected RF/preprocessor | Archive `research/Deliverables/TrueFlag_Model_Selection_20261018_183648/selected_pipeline.joblib` | `assets/local/baseline/model/selected_pipeline.joblib` | Byte-preserving local copy | Staged; not served |
| 27-field contract | Archive `research/data/splits/datarobot_provisional_v1/predictor_contract.json` | `assets/local/baseline/contracts/predictor_contract.json` | Preserve exclusions/missingness | Staged; validator pending |
| Frozen policies | Selection archive `selected_policy_settings.json` | `assets/local/baseline/contracts/selected_policy_settings.json` | Preserve full precision and KYC semantics | Staged; policy service pending |
| Feature definitions | Archive `research/data/data_dictionary.csv` | `assets/local/baseline/contracts/data_dictionary.csv` | Local evidence | Staged, ignored |
| Cleaned data | Archive `research/data/processed/datarobot_cleaned_v1.csv` | `assets/local/baseline/data/datarobot_cleaned_v1.csv` | Synthetic replay fixture only | Staged, ignored |
| Saved predictions/traces | Selection archive `final_evaluation_predictions.csv`, `decision_traces.csv` | `assets/local/baseline/validation/` | Preserve future replay reference | Staged; no rescoring |
| Cleaning / serialized classes | `research/src/trueflag/*.py` | `assets/local/baseline/reference/research/src/trueflag/` | Unmodified private reference | Staged; no public redistribution |
| SHAP implementation | `extensions/src/*.py`, `adapter/explanation_adapter.js` | `assets/local/baseline/reference/extensions/` | Unmodified method/reference | Staged; no service integration |
| Scientific versions | `extensions/requirements-explanations.txt` | Local reference plus `backend/ml-requirements.txt` | Exact recorded versions | Separate environment |
| API transaction/idempotency pattern | `legacy_api/src/trueflag/local_workspace.py` | New service design and roadmap | Conceptual reuse; no legacy application copied | Authentication foundation implemented; review service pending |
| Scientific reports | Archive selection/refinement/budget reports | Original archive remains authoritative | Reference, no duplication | Preserved |

## Rights and publication

- No LICENSE/COPYING permission was supplied for teammate source. Local reuse is authorized by the project request; public redistribution permission is unresolved.
- Consequently all copied teammate code, model binaries, data, saved predictions and private evidence remain under ignored `assets/local/`.
- No license is invented or applied to teammate assets. New source is committed without claiming rights to original work; receiving owners decide a repository license.
- Publication verification rejects private formats, local secrets, credential patterns and accidentally tracked assets. It does not establish legal rights or publisher authenticity.
- `baseline.manifest.json` records source/local paths and exact hashes privately; no model is loaded by staging.

## Namespace and behavior preservation

- API uses `app`, never `trueflag`. Preserve `trueflag.model_feasibility.TrainingScopeGuard` and other serialized module names inside the isolated ML runtime.
- Worker paths must be rooted at staged local assets, with explicit identity checks; no implicit import/read of the original teammate workspace.
- Keep source SAR labels separate from analyst recommendations. Do not retrain from workflow actions automatically.
- Existing original UI/explanation preview are not copied into the public frontend or silently activated.
