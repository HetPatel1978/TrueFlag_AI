# G4.3A — Functional, security and visual acceptance

## 1. Acceptance decision

- **Offline UI workflow: PASS in the isolated development fixture.** Final real Chromium run: **5 passed, 0 failed, 0 skipped**, 30.4 seconds; actual FastAPI/PostgreSQL services and constrained Linux simulation subprocess. No API response mocking.
- **Unconditional backend/release acceptance: NOT established.** Relevant backend regression groups retained three existing one-second clock-denial failures. Windows/WSL/Docker is not an independently clock-stable release runner.
- Real-provider generation remains disabled and unmeasured. No regulatory source approved/published, no semantic/legal/criminal conclusion certified, no autonomous case action.

## 2. Safe environment and schema

- Branch `codex/project-initialization`, unchanged HEAD `a3b2ba49cd92c4aa0401842fa4999897fdc28713`, plus preserved unrelated working-tree edits. No commit, push or deployment.
- Only existing owned rehearsal cluster `tf-g0-3-db-674bf460c1f147fab6dfc9530dd96ed2`; cluster identity, forbidden original identity, database and internal network checked through existing rehearsal helpers.
- API tests use random `tf_ingestion_test_<uuid>` schemas; browser fixture uses `tf_frontend_acceptance_<uuid>`. Only these disposable schemas upgrade to candidate **0017_live_provider**. Successful case/draft requests exercise the existing schema-compatibility gate. No new migration exists.
- The original demo database remains stopped. Container identity/image may be inspected read-only, but current SQL schema/system identity cannot be rechecked without starting it; **not authorized here**. Last known demo schema is `0012_evidence_foundation`, not claimed verified in this phase.
- Existing pinned Linux image `trueflag-assessment-verify:phase2-5`, read-only code/scientific/corpus mounts, 2 CPUs, 3 GiB, 128 PIDs. Private fixture generates approved synthetic cases and random ephemeral login credentials; strict normal password/JWT validation remains enabled.
- Existing fixture/worker code reused. Simulation is explicitly enabled and external execution false only in the disposable browser fixture. No `.env`, production credential or database-role change. Original G1/G2 cohorts and backups are outside test schemas.

## 3. Final verification ledger

Commands from repository root use `.venv/Scripts/python.exe -B`; frontend commands run under `frontend/`.

| Command/check | Actual result |
|---|---|
| `runtime/g4-3a/run.py --mode unit --label gateway-after-fix` | **14 passed, 0 failed, 0 skipped**: actual HTTP gateway and Linux fake-provider subprocess, idempotency/concurrency, authorization, projection, rollback, explicit clock denial and lock ordering. Included again in the broader group below. |
| `runtime/g4-3a/run.py --mode materialize --label backend-acceptance` | **174 passed, 1 failed, 0 skipped**: new gateways, existing packet API/draft/worker/verifier tests, G4.2A evaluation and regulatory context/publication boundaries. |
| `runtime/g4-3a/run.py --mode regression --label snapshot-worker-security` | **110 passed, 2 failed, 0 skipped**: coordinator, snapshot-integrity/policy, clock-health and release compatibility. |
| `python -m pytest backend/tests/test_investigation_evaluation.py backend/tests/test_regulatory_review_workflow.py -q --tb=short -p no:cacheprovider --basetemp runtime/g4-3a/native-evaluation-<new-uuid>` | **45 passed**. Initial default native TEMP invocation had 41 passed / 4 setup permission errors; workspace-owned fresh temporary directory resolved invocation isolation, no application/test assertion change. |
| `scripts/run_ml_verification.py --check tests` | **178 passed**, pinned Linux real private artifacts, no network. |
| Same script `--check scoring` | **4,000 matched**, maximum absolute error **0**, zero mismatches, original `atol=1e-12`. |
| Same script `--check policy` | **12,000 matched routes**, zero route/trace/retained/dismissed-total differences. |
| Same script `--check shap` | **4,000 verified**, zero encoded/grouped/base reference differences, score difference **0**; maximum reconstruction residual **3.1086244689504383e-15**, original tolerance `1e-6`. Missing-income 87 and observed-zero 22 preserved. |
| `npm.cmd test` | **99 passed**, eight files: 85 baseline + 14 new component/transport tests. |
| `scripts/run_investigation_e2e.py --suite drafts` — final run | **5 passed, 0 failed, 0 skipped**, 30.4 s. Real default request budgets and strict authentication retained. |
| Frontend lint / format / TypeScript / build | `npm.cmd run lint`, `format:check`, `build`: passed. No deployment. |
| Python lint / format | Ruff passed; **230 files** formatted. |

Do not sum overlapping focused/native/repeated runs as unique tests. The two main backend regression groups are disjoint: 284 passed / 3 failed; no full backend-suite run is claimed.

## 4. Confirmed correction and earlier results

### New gateway lock-order defect

- Initial Chromium run: **1 passed / 4 failed**. PostgreSQL fixture recorded five `DeadlockDetected` / SQLSTATE **40P01** events. Generation and supporting-record inspection completed before later reads failed; this was not attributed to clock instability.
- Cause: new gateway `detail → _owned` acquired actor/case row locks **before** existing `InvestigationDraftService.get` entered the coordinator advisory gate. Worker held that gate before obtaining actor/case locks, creating a cycle.
- Controlled PostgreSQL regression `test_detail_poll_and_worker_use_the_same_gate_before_actor_locks` reproduced **40P01** before the fix: `gateway-lock-before-fix`, **11 passed / 1 failed**.
- Minimum correction: the new detail gateway enters `coordinator._gate(session)` before `_owned`. Worker/core verifier, transaction semantics, clock rules and timeouts are unchanged. The same controlled regression passes in the final 14-test focused run and the broader suite. No deadlocks were recorded in the final selected Chromium fixture.
- This establishes the cause/fix for the **new draft route** only. The earlier G2 analytics-503 root cause remains unconfirmed.

### Other development/test observations

- First gateway run (`gateway-first`): **10 passed / 1 failed**; setup of the disabled-mode test observed now **1794836647** below high-water **1794836648**, epoch 2; `ClockUnavailable`, no security assertion bypass.
- Chromium second run: **4 passed / 1 failed**; source-revocation scenario failed before first evidence load, with the clock-unavailable UI. It did not test revocation and was not counted as such.
- Chromium third run: **4 passed / 1 failed**; the clock probe received **429** before clock verification, after the shared analyst's default request budget was spent. This is real admission protection, not proof of clock rejection. Final fixture uses its existing authorized supervisor account for the independent clock scenario; all default per-user limits remain **120/60 seconds**. No quota increase, arbitrary sleep or authentication bypass.
- Source-revocation browser test accepts the existing evidence guard clearing the protected subtree before its status button can be clicked. It requires a source-specific invalidation/unavailable state and no findings; clock denials are not substituted for revocation proof.
- Initial component duplicate-click test queried the old button label after the button became “Requesting…”. Corrected the fixture to click the same captured button twice; implementation lock/idempotency remained enforced.
- Visual review caught missing padding caused by the existing direct-child panel selector. Localized `.drafts-workspace .panel` padding now matches design tokens; no global style change. UTC dates and source-record version labels remain explicit.

## 5. Retained backend clock failures

| Test | Evidence / stage |
|---|---|
| `test_expired_worker_recovery_keeps_budget_and_fences_stale_response` | now **1794839488** < high-water **1794839489**, epoch 2; `ClockUnavailable` during initial `get_case_context` in `ready`, before the recovery assertions. |
| `test_missing_conflicting_multicurrency_reversals_and_decimal_profiles[corrections]` | now **1794839741** < high-water **1794839742**, epoch 2; clock guard fired, followed by expected-success assertion failure. |
| `test_publish_audit_database_failure_rolls_back_packet_and_job` | now **1794839769** < high-water **1794839770**, epoch 2; `ClockUnavailable` before intended audit-failure acceptance. |

- All observed `regressed=true`, `unsafe=true`. Failures remain failures; the 900-second window, floors/epochs, source checks and authorization remain unchanged.
- Other actual worker-crash/restart, audit rollback, malformed-reference/numeric and stale-source tests ran in the broader groups. The failed cases' specific assertions are not claimed verified by a different passing test.
- Final local/browser success does not resolve upstream clock instability or supply G1 stable-runner acceptance. No host time/synchronization setting changed; controlled clock simulation affected only the disposable schema.

## 6. Real browser acceptance matrix

| Scenario | Final measured interaction |
|---|---|
| Assigned analyst workflow | Login → source evidence → verified summary → paused-worker Pending → actual worker completion → verified simulated findings. |
| Record inspection | Transaction, customer and account source APIs, current version/hash checks, visible source details, close/focus restoration. |
| Resume/logout | Browser reload/relogin → requester history → original draft without another POST; logout removes protected UI, local/session storage empty. |
| Missing evidence | Actual incomplete-history source → verified abstention and limitations; no invented complete history. |
| Cross-analyst scope | Foreign assigned case denied; no findings/history exposed. |
| Source revocation | Real access withdrawal after enqueue; stale content withheld and source-specific notice. |
| Clock uncertainty | Previously completed draft withheld on controlled backward-clock observation; actual HTTP 503 / `clock_uncertainty`. |
| Accessibility/layout | Axe WCAG 2A/2AA/2.1AA on findings: no violations. Desktop 1440×1000; tablet 834×1112; mobile 390×844; tablet/mobile document width bounded by viewport. |

The supervisor clock actor is authorized through normal server policy; it is not a privileged clock bypass. No test changes a production identity/role, disables clock checks, fabricates stored job states or mocks successful API responses.

## 7. Screenshot evidence

**13 real synthetic-only PNGs**, exact byte hashes and pixel/viewport dimensions in [capture manifest](../runtime/g4-3a/screenshots/manifest.json). Owner-protected artifacts, ignored by Git. Copied unmodified from fully passing browser fixture `browser-c884b7a4900f42429296a04a07492ddb`; earlier captures/reports retained separately.

| Capture | File under `runtime/g4-3a/screenshots/` |
|---|---|
| Case Investigation tab | [case-investigation-desktop.png](../runtime/g4-3a/screenshots/case-investigation-desktop.png) |
| Request/Pending | [simulated-draft-pending.png](../runtime/g4-3a/screenshots/simulated-draft-pending.png) |
| Verified simulated findings | [verified-simulated-draft-desktop.png](../runtime/g4-3a/screenshots/verified-simulated-draft-desktop.png) |
| Transaction inspection | [supporting-record-details.png](../runtime/g4-3a/screenshots/supporting-record-details.png) |
| Customer / account inspection | [customer-supporting-record.png](../runtime/g4-3a/screenshots/customer-supporting-record.png), [account-supporting-record.png](../runtime/g4-3a/screenshots/account-supporting-record.png) |
| Draft history | [draft-history-desktop.png](../runtime/g4-3a/screenshots/draft-history-desktop.png) |
| Tablet / mobile | [verified-simulated-draft-tablet.png](../runtime/g4-3a/screenshots/verified-simulated-draft-tablet.png), [verified-simulated-draft-mobile.png](../runtime/g4-3a/screenshots/verified-simulated-draft-mobile.png) |
| Abstention | [missing-evidence-abstention.png](../runtime/g4-3a/screenshots/missing-evidence-abstention.png) |
| Access denial / revocation | [access-denied.png](../runtime/g4-3a/screenshots/access-denied.png), [source-revoked.png](../runtime/g4-3a/screenshots/source-revoked.png) |
| Clock denial | [clock-unavailable.png](../runtime/g4-3a/screenshots/clock-unavailable.png) |

Visual checks: preserved logo/navigation/tokens, restrained hierarchy, padding, readable numbers/UTC periods, explicit simulation and review states, expandable provenance/records and stacked mobile cards. History uses bounded horizontal table scrolling on narrow screens. Capture files are not AI-generated mockups or proof of production security certification.

## 8. Preservation and remaining gates

- Initial baseline covers **423 files**, including prior uncommitted application/docs changes, `.env`, scientific and privately staged regulatory/review assets. Intended changes are confined to the new gateway/UI/tests and small router/client/fixture extensions.
- Test/browser services are temporary; this is not a persistent demo deployment. Screenshots and diagnostics remain local. Original demo must not be started, repaired or migrated without separate authorization.
- Source/reviewer publication gates, live-provider authorization/privacy/retention/model/schema/spend acceptance and independent semantic evaluation remain pending. No evaluated-live result is available through these simulation-only endpoints.
- Existing coordinator gate serializes brief admission/read/worker transactions; it is a known scaling boundary, not a demonstrated production capacity guarantee. No broad lock/queue refactor was performed.
- Earlier analytics 503 investigation and independently clock-stable runner release acceptance remain unresolved.

## 9. Final preservation, build and cleanup verification

| Check | Actual result |
| --- | --- |
| Baseline preservation | Compared all **423** initial files. Only nine explicitly allowed existing paths changed: router registration, three client/workspace files plus workspace test mock, two isolated test launchers, and two ignored release-build identity files. All other baseline files, `.env`, privately staged scientific/regulatory assets and prior unrelated work retained their original SHA-256. New G4.3A files are listed in the implementation document. |
| Original records and backups | Original G1 template and G2 cloned cohort matched their pre-run snapshots. Both original/G1.1 backup hashes matched. No live database writes or migrations. |
| Isolated database integrity | **111** foreign keys checked; **0** orphan rows, **0** invalid constraints, **0** invalid indexes. Inventory: 59 tables, 153 indexes, 332 constraints, 110 triggers and 39 functions. Temporary test schemas cleaned. |
| Original demo | Container/image identity unchanged; PostgreSQL remains **stopped**. Current live schema **not SQL-verified**. Last known revision is `0012_evidence_foundation`; isolated candidate tests used migration `0017`. The demo was not started, repaired or migrated. |
| Cleanup | Stopped only the identity-verified owned rehearsal PostgreSQL container. Ephemeral browser API/frontend/worker fixtures and test schemas were removed by their launchers. Volumes, backups and original records retained. This is not a running demo handover. |
| Publication | `python -B scripts/check_publication.py`: **PASS, 395 source candidates**; private/secret ignore boundaries verified. No source approval/publication action. Git emitted sandbox permission warnings for the user's global ignore file; no configuration/ACL change was made. |
| Python / frontend checks | Ruff check and format passed (**230** files). Frontend lint, Prettier check, TypeScript and Vite production build passed (**46** modules). `git diff --check` passed; existing LF/CRLF conversion notices were informational. |
| Release identity | Source fingerprint `e1e5217e4fe04d803bf2cdcc3fa1edb574e5485a1d30311196144712f20a54f9`; build fingerprint `4550c435b3b545b919c032b9a65700bd355e363de7d822a65d982940ddc7dff7`. Generated metadata remains ignored. |
| Git | Branch `codex/project-initialization`, HEAD `a3b2ba49cd92c4aa0401842fa4999897fdc28713` unchanged. Changes remain uncommitted. No commit, push or deployment. |

Reproducible final preservation command: `.venv/Scripts/python.exe -B runtime/g4-3a/finalize.py --stop` (owned isolated environment only). Protected results are `database-preservation.json` and `preservation.json` under the directory referenced by `runtime/g4-3a/current.json`.

**Decision:** G4.3A's offline browser workflow is demonstrated using real PostgreSQL/API/durable-worker services and independently verified simulation outputs. Broader release acceptance remains **blocked** by the three retained clock-related backend failures and the unavailable stable runner. No claim of real-LLM semantic quality, approved regulatory applicability, live-demo compatibility or production certification is made. Stop here; live-provider activation requires separate authorization and evaluation.
