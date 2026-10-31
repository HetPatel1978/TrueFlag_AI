# Audited teammate architecture

This document describes the sibling `../github` source and verified assets inside `../private_handoff/main/TRUEFLAG_PRIVATE_ASSETS.zip`. Archived member paths below are not restored files. There is no current live model-to-API integration.

```mermaid
flowchart TB
  subgraph Research[Offline research]
    Raw[Synthetic alert aggregates: 10000 rows] --> Clean[Cleaning and source provenance]
    Clean --> Contract[27 predictors and recorded partitions]
    Contract --> CV[6000 development rows: shared five folds]
    CV --> Select[Candidate and frozen policy selection]
    Select --> RF[Fitted preprocessing + selected RF]
    RF --> Saved[4000 saved evaluation scores and 12000 traces]
    CV --> Budget[Saved OOF review-budget study]
  end
  subgraph Browser[Later standalone presentation]
    UI[Embedded saved cases and scores] --> JS[JavaScript policy replay]
    JS --> Reviews[Human reviews]
    Reviews --> Local[Browser localStorage and local export]
    Reg[Six saved regulatory searches] --> UI
  end
  Saved --> UI
  subgraph Legacy[Separate earlier demonstration]
    Old[300 earlier saved scores and policies] --> API[FastAPI saved-score routing]
    Web[Legacy HTML and JavaScript] <--> API
    API <--> SQLite[(SQLite runs and reviews)]
  end
  RF --> SHAP[Separate offline SHAP generation and verification]
  Saved --> SHAP
  SHAP --> Preview[Separate preview: browser acceptance pending]
  Budget --> Workload[Optional workload tool]
  Regulatory[Separate saved regulatory human-review prototype]
```

## Implementation evidence

| Responsibility | Original path |
|---|---|
| Cleaning/provenance | `../github/research/src/trueflag/datarobot_cleaning.py` |
| Preprocessing/fit scope | `../github/research/src/trueflag/model_feasibility.py` |
| Selection/refinement | `../github/research/src/trueflag/model_selection.py`, `model_refinement.py` |
| Predictor contract | Archive: `research/data/splits/datarobot_provisional_v1/predictor_contract.json` |
| Selected pipeline/results | Archive: `research/Deliverables/TrueFlag_Model_Selection_20261018_183648/` |
| Current UI | Archive: `presentation/current.html` |
| Earlier API and persistence | `../github/legacy_api/src/trueflag/local_workspace.py` |
| Legacy UI | `../github/legacy_api/TrueFlag_Workspace.html`, `src/trueflag/web/workspace.js` |
| Explanation extension | `../github/extensions/src/{explain,verify_explanations,build_preview}.py` |
| Workload analysis | `../github/research/scripts/review_budget_lib.py`, `../github/extensions/src/workload.py` |
| Regulatory worksheet | Archive: `optional/regulatory_review/` |
| Technical status/limits | `../github/docs/TECHNICAL_HANDOFF.md` |

## Limits

- No incoming transaction stream, entity graph, live retrieval, LLM provider, inference API, or integrated later-model persistence.
- Demo roles are visibility controls, not authentication. Current HTML embeds data accessible independently of role visibility.
- SAR is a synthetic disposition proxy; previously exposed evaluation records do not establish new independent validation.
- Global importance, policy traces and individual attributions are different evidence. Original hidden TreeSHAP provenance is incomplete; the separate extension establishes a different chain.
- Both source roots use regular package `trueflag`; naive combined import paths collide. Full historical training requires optional recovery inputs and remains unverified.
