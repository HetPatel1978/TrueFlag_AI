# Investigation page blockers — 23 November 2026

## Confirmed runtime diagnosis

| Symptom | Evidence | Cause |
|---|---|---|
| Research context HTTP 503, `Evidence service unavailable` | Underlying `VerificationFailed("research_context_invalidated")`; unchanged packet digest, evidence revision, clock epoch and retrieved passages; only the 900-second deadline failed | Read-only public research text incorrectly used the paid-dispatch freshness check. The old request had expired; this was not a database, worker or missing-source failure. |
| `No authorized provider is available` | Capabilities returned `provider: unavailable`; research enabled, contract verification/general analyst generation/research dispatch disabled, owner exact approval absent | Paid activation is correctly blocked. The UI did not distinguish a controlled research request awaiting approval from ordinary provider unavailability. |

Native API, assessment/import/evidence workers and frontend were ready. Frontend: `http://127.0.0.1:54464`; API: `http://127.0.0.1:54463`. The API deliberately does not load the provider credential. The separate controlled execution helper reads it only after approval, source and clock checks; a configured credential is not dispatch authorization.

## Narrow correction

- `ResearchEvidenceService.passages_for_read` permits authorized viewing of unchanged public research text after the dispatch deadline. It rechecks current scope, actor/case/source authority, evidence revisions, exact retrieval identity and clock health. It returns no new financial findings and grants no dispatch authority.
- Paid `provider_input`, independent verification and dispatch still require the original strict 900-second snapshot/epoch checks. No deadline, historical binding or clock floor was rewritten.
- The research context response explicitly reports `authorizes_dispatch: false` and current/expired binding status.
- Protected case capabilities distinguish `request_required`, `approval_required` and `request_expired`. React displays a disabled owner-approval action and the actual reason. General analyst generation remains disabled.
- Research remains labeled **Unapproved**, historical as of 2026-11-02. No official source approval or production publication was created. FinCEN material remains excluded.

## Verification completed

| Check | Actual result |
|---|---|
| Native PostgreSQL research/context/Claude/snapshot tests | **88 passed, 0 failed, 0 skipped**, 82.73 seconds; one existing Starlette/httpx warning |
| React | **167 passed**, 18 test files |
| Frontend build and ESLint | Passed |
| Modified Python Ruff lint/format | Passed |
| Browser verifier JavaScript syntax | Passed |

```powershell
.venv-windows/Scripts/python.exe scripts/verify_windows_runtime.py backend --candidate-source --tests test_academic_research.py test_regulatory_context.py test_claude_provider.py test_snapshot_clock_policy.py test_snapshot_clock_integrity.py
cd frontend
npm.cmd test
npm.cmd run build
npm.cmd run lint
```

New tests cover expired research text readability while dispatch stays rejected, source revocation, truthful approval capabilities and disabled UI actions. Chromium verification now additionally checks the approval explanation and disabled action without sending a paid request.

## Runtime activation and remaining acceptance

The owner explicitly authorized an application-only refresh. API, workers and frontend now use the verified private source snapshot; all five services report ready. PostgreSQL remained running (`database_stopped: false`) and no migration was applied.

- Test case: `8a8b6f51-863e-4d49-b316-8355786e874b` (authorized connected synthetic priority case).
- The original `academic-claude-research-review-2026-11-23-v1` request is expired and remains unchanged. It cannot be approved for a current dispatch.
- Post-refresh actual Chromium passed: real research passages and historical link, explicit disabled owner-approval action, refresh/session persistence, human casework availability, tablet rendering, wrong-user denial and logout denial. Private receipt/screenshots: `research-browser-3f4acada-d922-44b3-858b-01452de9b9b5/`. No backend mocks or external requests were used.
- Directly checked the original expired v1 binding: public research text remained readable; paid provider input was rejected. Seven protected configuration/historical approval/source files matched the preservation baseline.
- **Live inference requests executed during this work: 0.** No genuine Claude + research-RAG end-to-end acceptance is claimed.

## New exact-payload approval package

Private directory: `runtime/windows-native/c60bf6f3100c4eba97fc5450a5906891/academic-demo/academic-claude-research-review-2026-11-23-v2/`.

| Field | Value |
|---|---|
| Approval identifier | `academic-claude-research-review-2026-11-23-v2` |
| Complete body | `request.json`, **28,583 bytes** |
| SHA-256 | `3809a693f3da6350752735503d8672f9a44c500c4579684744ceb5cba0507f0b` |
| Model / destination | `claude-sonnet-5-5`; `https://api.anthropic.com/v1/messages` |
| Draft run | `cf3fc3f0-0263-4c2d-900c-70ce9479d268` |
| Financial input | 12 synthetic transactions, 17 authorized references, two verified financial facts; stored RF/Policy/SHAP signal |
| Financial fact references | `c5da47ce-31d3-54ef-91e9-378634da6f97`; `0a9b6b5a-c1c0-558e-8bad-e526363e16a6` |
| Research references | `616cf4cb-4a31-5cc3-b089-a51df84349f6` (§1020.320); `d4d91d35-6cab-5c22-80e9-2ae82843bf34` (§1020.210), historical 2026-11-02 |
| Limits | Input reservation/acceptance 32,768 tokens; output cap 4,096; timeout 20 seconds; one attempt, no automatic retry; provider-wide reservation lock |
| Application reservation | $2.14; not a guaranteed provider invoice cap |
| Dispatch snapshot deadline | **23 November 2026, 08:45:08 America/New_York** (`2026-11-23T13:45:08Z`) |
| Non-billable review | Byte-exact reconstruction, immutable configuration hash, current source/case/snapshot/clock authority, configured credential present and absent from body, four closed schema objects: passed at `2026-11-23T13:32:56Z` |
| Outstanding gates | Exact owner approval absent; provider HTTP/schema acceptance and independent live findings verification not exercised. General generation and research dispatch remain disabled. |

`context.json` provides complete source/evidence bindings; `configuration.json` provides execution limits; `approval-package.json` and `pre-dispatch-review.json` record the exact review scope. Full public passages and synthetic evidence are in `request.json`. FinCEN is excluded. No prior approval was reused. If the deadline passes, a newly identified request and new approval are required; never extend this binding.

No `.env`, frozen scientific asset, original demonstration database, source approval, immutable history or database clock floor was modified. No commit, push or deployment was performed.
