# G4.2B.1 — Offline compatibility and reliability evidence

**Live Luminal inference requests executed: 0.** All provider success/error tests used HTTPX MockTransport or the existing mocked Linux child. Provider-test containers use the isolated internal PostgreSQL network without external provider access. Browser fixtures explicitly enable simulation only. No direct Luminal HTTP, account, model-list or token-validation request ran.

## Changes

| Files | Purpose |
| --- | --- |
| `backend/app/services/provider_budget.py`, `core/config.py` | Hard three-attempt/$1 preparation ceiling; configured request allowance defaults zero. |
| `backend/app/services/luminal_provider.py` | Reject absent/invalid call allowance, paid-retry configs and per-run spend above effective $1 bound before HTTP. Existing model/host/approval/secret/schema controls retained. |
| `backend/app/services/investigation_drafts.py` | Under existing grant lock, atomically count immutable reservations and cumulative spend across runs/processes; deny fourth request/budget excess; audit denial reason. No new queue/table/migration. |
| `backend/app/services/live_provider_runner.py`, `provider_readiness.py` | Forward only the additional count control to isolated child; report effective technical ceilings without claiming approval. |
| `backend/app/evaluation/luminal_probe.py`, `tests/test_luminal_probe_plan.py` | Prepare exact A/B/C requests from three new supported synthetic cases and independent source/Decimal checks, without provider invocation. |
| `backend/tests/test_probe_budget.py`, existing provider/readiness tests | Concurrency, restart, count/spend exhaustion, invalid allowance, no paid retry, existing failure/security coverage. |
| `scripts/run_investigation_e2e.py` | `--suite probe` selects the existing simulation browser test in this phase's isolated fixture. No live transport/activation command. |

This intentionally tightens candidate execution: formerly configurable live rate-limit retries are now prohibited; `max_attempts` must be one. Frozen RF, 27-feature contract, policy thresholds, SHAP, prompts and structured findings semantics are unchanged. Existing immutable configurations/history are not rewritten.

## Actual tests

Commands run from repository root using `.venv/Scripts/python.exe -B`; frontend commands run under `frontend/`.

| Command / suite | Passed | Failed | Skipped |
| --- | ---: | ---: | ---: |
| `runtime/g4-2b-1/run.py --mode unit --label probe-contract-and-budget-first` | **58** | **0** | **0** |
| `runtime/g4-2b-1/run.py --mode materialize --label provider-evidence-human-regressions` | **73** | **0** | **0** |
| `runtime/g4-2b-1/run.py --mode regression --label snapshot-worker-clock-regressions` | **112** | **0** | **0** |
| `scripts/run_investigation_e2e.py --suite probe --grep 'source revocation'` | **1** | **0** | **0** |
| `frontend/`: `npm.cmd test` | **111** | **0** | **0** |
| `scripts/run_ml_verification.py --check tests` | **178** | **0** | **0** |

These are focused/relevant suites, not the complete backend suite or a new stable-runner release acceptance. Historical clock regressions and broader release blockers remain recorded; this passing run does not identify or repair the host/WSL synchronization cause.

## Required negative coverage

| Requirement | Verification |
| --- | --- |
| Valid response; wrong/unsupported model; invalid credentials/schema | Existing HTTPX contract tests; exact identity, envelope and strict-format checks. No free-text downgrade. |
| Malformed response, missing/excess usage, incorrect numeric types | Existing parser/error tests reject safely, without reflecting provider bodies or secrets. |
| Rate limits/timeouts/network interruption | Mocked rejection; rate errors no longer schedule paid retry. Timeout/unknown delivery retains its immutable reservation. |
| Disabled/unapproved | Absent key/approval/terms/contract/enable/call allowance block before mock transport is opened. Boolean/out-of-range/missing call allowance denied. |
| Duplicate prevention | Existing identical intent/idempotency tests reuse one durable result. No duplicate consequential assessment or case action. |
| Grant count/concurrency/restart | Two completed calls plus competing preparations admit exactly one remaining reservation; fourth denied. Recreated service cannot reset retained counters. |
| $1 exhaustion | Synthetic operator ceiling $5 cannot permit two $0.73728-sized reservations; effective application ceiling is $1, even before count three. |
| Forged references/wrong financial totals | Existing independent source/numeric verifier rejects hostile proposals. Probe C independently recomputes four USD observations totaling 160.09. |
| Clock/source/assignment revocation | Existing controlled clock, expired replay, worker recovery, source revocation and human role tests passed unchanged. |

Known enforcement boundary: adapter HTTP contract tests are not evidence of a vendor-enforced monetary cap. Durable limits apply through the controlled worker/reservation path. Arbitrary use of a key outside it is not an authorized execution path.

## G4.3A browser revocation — separate from provider compatibility

- Historical failure stopped before revocation because the protected UI reported time verification unavailable and detached the summary control. Underlying host-clock instability and earlier analytics 503 are not declared resolved.
- Existing explicit checkpoints are retained: verified parent → requested durable draft → API confirms Pending → real source-service revocation acknowledged → API confirms Invalidated/draft absent → UI source denial/no Financial Observations.
- This phase's **1/1** actual Chromium test completed that sequence in **6.2 seconds**. It used only the existing offline simulation worker and real PostgreSQL/API. No authorization/snapshot/clock condition or timeout was relaxed.

## Scientific and secret checks

- Pinned Linux ML: **178 passed**, 9.402 seconds. RF **4,000** matches/max error **0**; policy **12,000** routes/no trace or count differences; SHAP **4,000** verified/no mismatches. Maximum reconstruction residual `3.1086244689504383e-15` under `1e-6`; missing income 87 and observed zero 22 remain distinct. Scientific fixtures were verification inputs only, never probe content.
- Exact known key-byte scan: **PASS** for frontend bundles, public source/reports, current task diagnostics and **269 current Git index blobs**. No value, fragment, hash or length emitted. This is not a complete secret/history/encoded-variant certification; existing publication ignore checks remain required.
- Current configuration has no usable expected key binding, external execution remains false, approval empty, contract false and allowance/spend zero. No process was provisioned with the stored key and `.env` is unchanged.

No source/customer values are logged; request/source dossiers are protected local synthetic artifacts. No commit, push, deployment, original-demo modification or live frontend activation.

## Final verification and preservation

| Check | Actual result |
| --- | --- |
| Formatting/static/build | Ruff check and format **PASS, 243 files**. Frontend ESLint, Prettier, TypeScript/Vite build **PASS, 49 modules**. `git diff --check` passed. |
| Publication | `scripts/check_publication.py`: **PASS, 424 candidates**. Private/secret ignore boundaries retained; no regulatory/source publication. Sandbox global Git-ignore read warnings did not alter configuration or permissions. |
| Exact known credential bytes | **0 findings** in 4 frontend bundle files, 400 public source/report files, 45 current diagnostic files and 269 indexed blobs. Only presence/results/counts emitted; no key fragments, fingerprints or lengths. Limits: current index/files, not complete history, unknown secrets or encoded variants. |
| Baseline | All **456** initial files compared. Exactly 11 intended existing paths changed: configuration/provider/count/reservation/runner/readiness controls, related tests, isolated browser launcher and two ignored release metadata files. New preparation/test/document files are additional. Unrelated work, `.env`, original backups and scientific/regulatory assets unchanged. |
| Database | Original G1 template and G2 clone unchanged. **111** foreign keys checked; **0** orphans or invalid constraints/indexes. Temporary schemas cleaned; no new migration. Original demo remains stopped, identity unchanged, current live schema unverified (last known `0012_evidence_foundation`). |
| Cleanup | Stopped only the identity-verified owned rehearsal PostgreSQL container. Backups/volumes/records and protected review package retained. Original assessment/import workers left unchanged. |
| Release/Git | Expected schema unchanged at **0018**. Source SHA `a8c94fc91687dd263512f81f869590e144e3abb3cb52afe6768ff16d15bf698f`; build `f19292ee3ebd1277363e92522e3019a24c7f8465dd6e44b0bb971d958fdfaf88`. Branch `codex/project-initialization`, HEAD `a3b2ba49cd92c4aa0401842fa4999897fdc28713`, unchanged/uncommitted. No push/deployment. |

Protected evidence is under the directory identified by `runtime/g4-2b-1/current.json`; the separate review package is at `runtime/g4-2b-1/approval/`. The proposal remains **pending**, all eight approval decisions null. External activation and configured call/spend allowance remain off/zero.

**Preparation accepted locally; future live execution NO-GO. Live Luminal inference requests executed: 0.** Passing local tests do not approve privacy, verify vendor billing/schema/tokenization, resolve historic clock instability or authorize a live investigator.
