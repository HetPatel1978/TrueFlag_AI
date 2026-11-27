# G3.1 — Functional, security and visual QA

## Environment and current decision

- Branch `codex/project-initialization`; initial HEAD `a3b2ba49cd92c4aa0401842fa4999897fdc28713`. No commit, push or deployment authorized/performed.
- Preserved baseline: **435 files**, including G4.3A, prior unrelated edits, `.env`, scientific/regulatory assets. Protected diagnostics: directory identified by `runtime/g3-1/current.json`.
- Only identity-verified owned rehearsal PostgreSQL is used; all test/browser schemas are disposable. Candidate schema **0018**; original demo remains stopped, with current schema unverified (last known `0012_evidence_foundation`). No original-demo startup/migration/repair.
- Windows/WSL/Docker is not an independently clock-stable runner. A local passing workflow cannot establish release acceptance or resolve upstream time instability.

## Verification ledger — updated after completion

| Check | Result recorded so far |
| --- | --- |
| Initial PostgreSQL casework run | 9 passed / 5 failed. Three failures were duplicate-keyword construction in the new test helper; remaining negative-path assertions exposed missing HTTP 409 conflict mapping. |
| Second PostgreSQL run | 11 passed / 3 failed. One full-workflow fixture repeatedly logged in and reached existing HTTP 429 login admission. Two negative cases required the new casework conflict mapper. Test helper now reuses actual authenticated sessions; production limits unchanged. |
| Third focused PostgreSQL run | **13 passed / 1 failed / 0 skipped**. Remaining assignment-isolation expected-success read received safe 503 during observed clock rewind: now **1794857796** < high-water **1794857798**, epoch 2, regressed true. Security assertion was not relaxed. |
| Initial React regression | 99 passed. |
| React with new casework tests | **111 passed / 0 failed / 0 skipped** (12 new UI cases). |
| First human Chromium run | **2 passed / 1 failed**. Cross-analyst denial and source-revocation withholding passed. Main journey stopped before draft generation when the existing investigation UI reported time verification unavailable; this does not establish the rest of that journey. |
| TypeScript / Vite | Build passed, 49 modules. Initial sandbox esbuild could not read its existing config; owner-context invocation passed without ACL changes. |
| Frontend lint | Passed at initial component verification. |

No clock guard, snapshot expiry, financial verifier, login quota or worker lease was weakened. Subsequent runs, screenshots, scientific replay and preservation results are appended below after actual execution.

## Final test results and exact commands

Commands below run from repository root using `.venv/Scripts/python.exe -B` unless noted. Protected Linux runners verify the owned cluster/database identity before starting disposable schemas. They retain value-free summary/clock diagnostics; private failure artifacts are not publication inputs.

| Command / suite | Passed | Failed | Skipped | Scope / limitation |
| --- | ---: | ---: | ---: | --- |
| `runtime/g3-1/run.py --mode unit --label verified-casework-final` | **20** | **0** | **0** | Final casework source: real PostgreSQL/API, source/hash membership, authorization, immutability, idempotency, concurrency, audit/transaction rollback, revocation, stale approval, interim resumption and stale escalation return. |
| `runtime/g3-1/run.py --mode materialize --label final-casework-draft-regulatory` | **212** | **2** | **0** | 214 tests: casework, existing case workflows, G4.3A gateways/drafts/verifier, G4.2A evaluation and regulatory boundaries. This group predates the two final resumption cases; those pass in the focused 20-test run above. |
| `runtime/g3-1/run.py --mode regression --label evidence-clock-worker-security` | **111** | **1** | **0** | Coordinator, snapshot integrity/policy, clock-health, worker recovery and release compatibility. |
| `frontend/`: `npm.cmd test` | **111** | **0** | **0** | Nine files, including 12 new casework component/API-contract cases. |
| `scripts/run_investigation_e2e.py --suite human` — final run | **3** | **0** | **0** | Actual Linux/PostgreSQL/API/offline-worker/Chromium, **16.7 seconds**. Full analyst-to-independent-supervisor journey, cross-analyst denial, source-revocation withholding. |
| `scripts/run_investigation_e2e.py --suite drafts` | **4** | **1** | **0** | Existing G4.3A browser regression. Main workflow, partial-evidence abstention, cross-case denial and controlled clock-denial scenarios passed. Queued-source-revocation scenario stopped before the revocation action; do not count it as passed. |
| `scripts/run_ml_verification.py --check tests` | **178** | **0** | **0** | Actual pinned Linux scientific runtime, no network, 10.123 seconds. |

Counts are **per invocation**, not an aggregate of unique tests. The complete backend repository suite was not run or claimed. A passing final focused rerun does not erase failures in broader runs.

| Frozen comparison command | Actual result |
| --- | --- |
| `scripts/run_ml_verification.py --check scoring` | **4,000** ID-matched scores, max absolute error **0**, **0** mismatches/failures; absolute tolerance `1e-12`, relative tolerance zero. |
| `scripts/run_ml_verification.py --check policy` | **12,000** route matches; **0** route/trace mismatches and retained/reduction-candidate count differences. Thresholds and policy artifacts unchanged. |
| `scripts/run_ml_verification.py --check shap` | **4,000** verified, **0** mismatches/unavailable; encoded/grouped/base and model-score differences **0**. Maximum reconstruction residual `3.1086244689504383e-15`, tolerance `1e-6`. Missing income **87** / observed zero **22**, preserved distinctly. |

### Retained failures — not resolved by rerunning

| Test | Observed cause / boundary |
| --- | --- |
| `test_stale_forged_revoked_source_and_hidden_history` | Broad-run `ClockUnavailable`; now **1794858612** < floor **1794858613**, epoch 2, regressed true. Same security case passes in the final focused suite; clock stability remains unestablished. |
| `test_missing_partial_conflicting_evidence_is_preserved_with_abstention[partial]` | Existing draft expected-success assertion after clock guard; now **1794858752** < floor **1794858753**, epoch 2, regressed true. |
| `test_legacy_aggregate_case_has_no_invented_transactions` | Existing coordinator read denied; now **1794858527** < floor **1794858528**, epoch 2, regressed true. No transaction evidence was fabricated to satisfy the test. |
| G4.3A Chromium queued-source-revocation scenario | Existing protected Investigation subtree detached before summary submission. The browser reported time-verification unavailable before reaching the source-revocation action; other G4.3A security scenarios passed. This scenario remains incomplete in this invocation. |

Earlier broad invocation `casework-and-draft-acceptance`: **209 passed / 1 failed**; the existing requester-history detail test coincided with now **1794858078** < floor **1794858079**, epoch 2. The historical intermittent analytics 503 cause remains unconfirmed; do not attribute it to these new findings.

### Development defects and corrections

- Conflict mapper: new casework `EvidenceConflict` initially inherited the generic 503 evidence boundary. Added an explicit sanitized **409** mapping; clock/integrity failures retain 503.
- Fixture login pressure: new helper logged in before every command and reached the real login budget. Reused actual per-actor authenticated sessions; no quota increase or auth bypass.
- Initial new helper passed default rationale/links twice; corrected dictionary construction. A later expansion temporarily introduced a misplaced rollback assertion (one collection error) and missing `UUID` import; corrected before the final **20/20** run. Intermediate expansion recorded **12 passed / 8 failed**; seven helper failures and one clock-denied immutable-delete setup, not evidence of a passing build.
- Browser run ledger: first three runs **2 passed / 1 failed** each. First was time-verification denial; second used an exact wrapped-label selector that included option text (fixed to exact accessible combobox role/name); third completed all consequential actions but incorrectly expected login to survive a reload. Test now reauthenticates through the real login screen; no browser credential storage was added. Both subsequent runs passed **3/3**.
- Source resumption review identified a workflow lock: an interim outcome invalidates prior draft versions, and a stale escalation must permit return without approving stale evidence. Final policy selects only current reviews for approval, requires new verified reviews after version changes and allows stale escalation return only. Original history remains intact; dedicated real PostgreSQL tests pass.
- Existing simulated-draft wording no longer claims that no human review exists anywhere. It states that human review decisions are recorded separately in Investigation Casework; the original simulation and verifier boundaries remain explicit.
- New TypeScript fixture signatures were corrected and production build rerun successfully. No production credential, system-time setting or filesystem ACL was changed.

## Browser interaction and security coverage

| Interaction/control | Actual verification |
| --- | --- |
| Evidence and simulated draft | Assigned analyst logs in, reviews source evidence, generates a real verified parent and offline simulated draft through existing durable workers. |
| Notes and requests | Source-linked note, request creation, current-record-backed response and persisted history; author/time shown. PostgreSQL also covers own-note addenda and denied modification. |
| Finding review | Original simulated claim is hash-bound and rejected with human rationale. Original finding content/hash remains unchanged in PostgreSQL. Acceptance is never a criminal/SAR approval. |
| Escalation/resolution | Analyst escalation appears in supervisor queue; separate authenticated supervisor reviews, explicitly confirms approval, then explicitly confirms a matching internal resolution. Seven journal entries appear in browser history; backend journey with an addendum records eight. |
| Persistence/refresh/logout | Activity History shows the human resolution; reload requires login, after which stored history is retrieved. Logout removes protected views; local/session storage remain empty. |
| Authorization | Anonymous, wrong-assignment, cross-case, inactive/revoked supervisor, self-approval, other-author correction and analyst queue access denied. Current source/assignment checks remain server-enforced. |
| Integrity/atomicity | Forged source/hash/claim denied; DB update/delete/truncate rejected; competing finalizations yield one winner; entry/audit/case-state rollback verified under injected persistence failure. |
| Staleness | Changed evidence withholds historical rationale and source binding; intervening work invalidates final approval; stale escalation may be returned only. Current verified review required after interim outcome. |
| Accessibility | Actual Chromium Axe WCAG 2 A/AA + 2.1 AA scan over casework returned **zero violations**. Confirmation receives focus, traps Tab navigation, permits Escape cancellation when not submitting and restores focus. Automated scan is not a comprehensive accessibility certification. |

## Visual captures

**13 actual synthetic screenshots** from final browser directory `browser-0f4666f418a3469fab17c97c98678aa2`; SHA-256, image dimensions and viewport metadata in `runtime/g3-1/screenshots/manifest.json`. No generated mockups or fabricated financial results.

| State | Capture |
| --- | --- |
| Incomplete / prerequisites | [incomplete-casework-desktop.png](../runtime/g3-1/screenshots/incomplete-casework-desktop.png) |
| Notes | [investigation-notes-desktop.png](../runtime/g3-1/screenshots/investigation-notes-desktop.png) |
| Evidence request | [information-request-desktop.png](../runtime/g3-1/screenshots/information-request-desktop.png) |
| Finding review | [finding-review-desktop.png](../runtime/g3-1/screenshots/finding-review-desktop.png) |
| Tablet / mobile | [casework-tablet.png](../runtime/g3-1/screenshots/casework-tablet.png), [casework-mobile.png](../runtime/g3-1/screenshots/casework-mobile.png) |
| Supervisor queue / confirmation | [supervisor-queue-desktop.png](../runtime/g3-1/screenshots/supervisor-queue-desktop.png), [supervisor-review-confirmation.png](../runtime/g3-1/screenshots/supervisor-review-confirmation.png) |
| Resolution confirmation / completion | [case-resolution-confirmation.png](../runtime/g3-1/screenshots/case-resolution-confirmation.png), [completed-case-resolution-desktop.png](../runtime/g3-1/screenshots/completed-case-resolution-desktop.png) |
| Activity History | [human-casework-activity-history.png](../runtime/g3-1/screenshots/human-casework-activity-history.png) |
| Access denial / source revocation | [casework-access-denied.png](../runtime/g3-1/screenshots/casework-access-denied.png), [casework-source-revoked.png](../runtime/g3-1/screenshots/casework-source-revoked.png) |

Reviewed desktop **1440×1000**, tablet **834×1112**, mobile **390×844**. Shared branding, colors, typography, navigation, plain-text rationale, spacing, expandable provenance and responsive stacking are preserved. Actual tablet/mobile body-overflow assertions passed. The complete multi-form workflow is vertically long on mobile; progressive disclosure remains a future usability refinement, not an implemented feature.

## Final preservation and acceptance decision

- `runtime/g3-1/finalize.py --stop` verified the **435-file** initial baseline: exactly **18** intended existing-file changes plus new casework files; unrelated pre-existing work, `.env`, scientific and regulatory assets unchanged. Original/G1.1 backup hashes matched; original G1 template and G2 cloned cohort states matched their pre-run snapshots.
- Original PostgreSQL container/image identity unchanged and still stopped. Current live schema **not SQL-verified**; no startup, repair or migration. Disposable schemas alone exercised candidate **0018**, empty rollback and refusal to downgrade retained human history.
- Preserved copy integrity: **111** foreign keys; **0** orphan rows, **0** invalid constraints/indexes. Its retained schema remains 59 tables / 153 indexes / 332 constraints / 110 triggers / 39 functions, proving the candidate migration was confined to disposable schemas. Temporary schemas cleaned; stopped only the owned rehearsal PostgreSQL; volumes/backups/original records retained.
- Final Python Ruff check/format passed (**236 files**); frontend ESLint, Prettier, TypeScript/Vite build passed (**49 modules**); `git diff --check` passed; publication boundary scanner **PASS, 409 candidates**. Sandbox emitted global Git-ignore read warnings; no Git configuration/ACL change.
- Final source fingerprint `1d78ef3975cb322e596e26609dd9036faedfa5965072e9445978fffe73977271`; build `43b03a93aa789f4c83c447aba5a507393579d3eb103b19b00f06b0d7ca319c99`. Matching ignored metadata generated; final frontend build passed. Branch/HEAD unchanged; all work remains uncommitted. No push or deployment.

**Decision:** G3.1 human workflow is implemented and demonstrated on real isolated services. **Unconditional release acceptance remains blocked** by clock instability and retained broader regression failures. No full-backend, stable-runner or production security certification is claimed.

Remaining G3/product scope: reopening and post-resolution addenda, optional server-side draft notes, richer request assignment/notifications, independently reviewed operational policy and larger-cohort end-to-end acceptance. Existing supervisor scope is project-wide, inherited from the current synthetic RBAC model; no organization/tenant hierarchy is invented. UI refresh checks are bounded at 15 seconds × 20 attempts with manual refresh; revocation is enforced on every server read/write, not via instantaneous push notifications.

Ready for further **isolated** end-to-end testing after clock-stable runner availability and review of internal decision policy. Original demo migration/startup, live-provider activation and unapproved regulatory integration require separate authorization/gates. Stop after G3.1.
