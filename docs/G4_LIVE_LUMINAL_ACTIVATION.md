# G4 - bounded Luminal activation review

**Decision: LIVE ACTIVATION BLOCKED; offline verification passed.**
**Live Luminal inference requests executed: 0.**

## 1. Authorization and actual execution

- Review date: November 16, 2026, session date; not trusted clock attestation.
- Owner authorized the unchanged G4.2B.1 synthetic package, maximum three attempts, $1 application ceiling and no automatic paid retries. These grants supersede the earlier checklist's corresponding pending decisions; the historical proposal remains unchanged.
- Owner subsequently answered **"Accept for the exact synthetic probes only"** after disclosure of 7-day retention, up to 90-day flagged retention and DeepSeek China/training fallback. This resolves the disclosed privacy-consent gate for these probes only.
- Continued analyst live generation, broader data transfer and operating spending remain gated. No provider authentication, discovery, account/balance or inference request was made. Public documentation was reviewed without credentials or synthetic payloads.

| Measurement | Actual result |
| --- | --- |
| Provider/model identity | Candidate only: Luminal / `deepseek-ai/DeepSeek-V4.1-Flash`; authenticated identity unverified |
| Strict structured output / model response | Offline contract tests pass; actual API behavior untested |
| Provider-reported tokens / latency | Not measured; no response |
| Inference spending attributable to this task | $0; no inference dispatched; vendor invoice not queried |
| Application reservations for live attempts | None created; proposed A/B/C reservations total $0.06945792, not actual usage |

## 2. Verified package and configuration

- Package digest: `338703d5b331f6d98e84e58be4977adb49cf80a269af2fb49cacbe74b0d99183`.
- All three raw request hashes match the [original proposal](G4_2B_1_LUMINAL_PROBE_PLAN.md); rebuilding with the current adapter reproduces identical bytes. Independent source membership, amounts, currencies, counts and window checks pass. Probe C remains four synthetic USD observations totaling 160.09; incomplete coverage requires abstention.
- Key present under `LLM_API_KEY`; expected `INVESTIGATION_PROVIDER_API_KEY` binding absent. Supported binding was verified **in memory only**, with execution disabled; no worker received the key. `.env` unchanged; effective external flag false and call allowance zero. Key validity remains untested.
- Reused [adapter](../backend/app/services/luminal_provider.py), [immutable reservations](../backend/app/services/investigation_drafts.py), [hard limits](../backend/app/services/provider_budget.py) and independent verifiers. No application-source changes or second provider pipeline.

## 3. Remaining live gates and remedies

| Gate | Evidence / required next action |
| --- | --- |
| Billing/token upper bound | [Published pricing](https://www.luminal.com/pricing) still lists $0.1425/M input and $0.5700/M output including reasoning. Exact tokenizer accounting and whether the submitted completion cap bounds all billable reasoning remain unverified. Obtain an authoritative contract; byte admission and 2x pricing margin do not establish a reliable bound or invoice cap. |
| First-probe execution | Adapter requires `contract_verified` before transmission. No approved first-probe executor validates this package against a scoped grant and immutable attempt ledger. Do not assert compatibility to bypass that gate or call the adapter outside accounting. Implement the bounded procedure separately once prerequisites are resolved. |
| Source authority | Prepared packets came from disposable schemas. Archived-source correctness does not establish current case/assignment authority. Establish explicit probe-fixture authority without weakening case-worker checks; rematerialization changes payload hashes and requires review of the replacement package. |
| Clock/release health | Two 60-second observations: 60 host round trips each; zero host/guest/PostgreSQL backsteps or sampler errors. TSC clocksource; kernel read-only synchronization query returned 0. Historical WSL2 instability and independent-runner acceptance remain unresolved; no synchronization settings changed. |

- Official [terms](https://dash.luminal.com/terms), effective October 21, and [privacy](https://dash.luminal.com/privacy), effective October 7, were reviewed through public indexed pages. Findings remain consistent with the earlier review; exact current HTML hashes were not re-retrieved. The accepted synthetic-only conditions do not certify broader processing suitability.
- Strict `json_schema` support and authenticated availability remain unverified, not proven unsupported. No permissive parsing fallback was introduced.

## 4. Actual verification

| Check | Passed / Failed / Skipped |
| --- | --- |
| Linux/PostgreSQL provider, package and budget | 58 / 0 / 0 |
| Linux/PostgreSQL provider integration, verifier, API and human casework | 73 / 0 / 0 |
| Linux/PostgreSQL coordinator, snapshots, controlled clocks and release checks | 112 / 0 / 0 |
| React | 111 / 0 / 0 |
| Chromium investigation / human casework | 5 + 3 / 0 / 0 |
| Pinned Linux ML | 178 / 0 / 0 |

- Frozen parity: RF 4,000, maximum error 0; policy 12,000, zero route/trace/count mismatches; SHAP 4,000, zero mismatches, maximum reconstruction residual `3.1086244689504383e-15` against `1e-6`. Missing income 87 and zero income 22 remain distinct.
- Tested disabled transport, budget/concurrency limits, ambiguous outcomes, forged references, incorrect financial values, permission/source revocation and expired replay. Chromium exercised actual revocation denial and controlled clock denial; model generation was simulated.
- Ruff check/format, ESLint, Prettier, TypeScript/Vite build and publication checks passed. No full backend-suite or production-capacity claim. Initial frontend launch was blocked by PowerShell script policy, then sandbox path resolution; `npm.cmd` in the approved environment passed without policy changes. A local audit helper initially used Python-mode instead of JSON-mode strict deserialization; corrected locally, with all package checks subsequently passing. No application defect was established.
- Git whitespace verification passed under the repository's normal settings. A diagnostic `core.autocrlf=false` override flagged existing CRLF lines as trailing whitespace; the override was removed and the normal check passed. Existing line endings were preserved.
- Preservation: all 464 baseline files unchanged, including `.env`, frozen assets and unrelated work; original backups and retained G1/G2 cohort unchanged. Checked 111 foreign keys, zero orphans/invalid constraints/indexes. Original demo stayed stopped and its current schema was not queried. Stopped only the owned rehearsal cluster; retained records/volumes/backups.
- Exact known-key-byte scan: zero findings in 4 frontend bundle files, 401 public source/report files, 102 current diagnostics and 269 Git index blobs. Scope excludes unknown secrets, encoded variants and complete history. Publication check passed for 425 candidates.

Reproduction commands, from repository root unless specified:

```powershell
.venv\Scripts\python.exe runtime/g4-live/audit.py
.venv\Scripts\python.exe runtime/g4-live/run.py --mode unit --label activation-provider-contract
.venv\Scripts\python.exe runtime/g4-live/run.py --mode materialize --label activation-verifier-and-casework
.venv\Scripts\python.exe runtime/g4-live/run.py --mode regression --label activation-snapshot-clock-security
.venv\Scripts\python.exe runtime/g4-live/measure_clocks.py --label activation-clock-observation
.venv\Scripts\python.exe runtime/g4-live/measure_clocks.py --label activation-clock-observation-repeat
.venv\Scripts\python.exe runtime/g4-live/browser.py --suite probe
.venv\Scripts\python.exe runtime/g4-live/browser.py --suite human
.venv\Scripts\python.exe scripts/run_ml_verification.py --check tests
.venv\Scripts\python.exe scripts/run_ml_verification.py --check scoring
.venv\Scripts\python.exe scripts/run_ml_verification.py --check policy
.venv\Scripts\python.exe scripts/run_ml_verification.py --check shap
.venv\Scripts\ruff.exe check backend scripts
.venv\Scripts\ruff.exe format --check backend scripts
.venv\Scripts\python.exe scripts/check_publication.py
# frontend working directory:
npm.cmd test -- --reporter=dot
npm.cmd run lint
npm.cmd run format:check
npm.cmd run build
```

Labels create exclusive artifact directories; repeat executions require new labels. Protected diagnostics: directory identified by `runtime/g4-live/current.json`. Original request/source files remain in `runtime/g4-2b-1/approval/`; not published.

## 5. Frontend and disposition

- Existing [draft gateway](../backend/app/services/draft_api.py), [API projection](../backend/app/schemas/draft_api.py) and [React findings](../frontend/src/drafts.tsx) explicitly support offline simulation. Historical simulations remain labeled; no real result is claimed or exposed.
- Live frontend integration is deferred until a successful controlled probe, independent quality acceptance and separately authorized operating budget. Human decisions remain separate. Regulatory sources remain unpublished; no case closure or SAR action.
- Branch `codex/project-initialization`, HEAD `a3b2ba49cd92c4aa0401842fa4999897fdc28713`. No commit, push, deployment, live demo migration, credential/role change or scientific modification. Conditional probe authorization is recognized; unresolved technical prerequisites prevent dispatch.
