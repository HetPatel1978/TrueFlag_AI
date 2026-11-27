# G2.3 — Visual and functional QA

## 1. Environment

- Windows Chromium/React with loopback Vite `15173`; disposable FastAPI acceptance fixture `18010`; existing owned Linux PostgreSQL 17.11 rehearsal cluster with no published DB port. Test schemas only, real pinned Linux assessment/import/investigation workers.
- Normal strict authentication, current 900-second snapshot policy, persistent floor/token epoch and numeric/reference checks preserved. No live demo access or migrations.
- Candidate branch/HEAD and scope: [implementation](G2_3_ANALYST_WORKFLOW_COMPLETION.md). Reproducible isolation and preservation evidence remains in ignored, owner-only `runtime/g2-3`.

## 2. Commands and actual results

Run from repository root unless stated otherwise.

| Command | Actual result |
|---|---|
| `.venv/Scripts/python.exe -B runtime/g2-3/run.py --mode workflows --label workflows-first` | 81 passed, 2 failed, 0 skipped. New test incorrectly indexed enqueue's tuple; existing gateway publication test recorded actual one-second DB-clock regression and safely denied. |
| Same runner `--label workflows-corrected` | 84 passed, 0 failed, 0 skipped; includes 18 workflow tests, existing case assignment/authorization tests and 15 investigation gateway tests. |
| `cd frontend; npm.cmd test` | 85 passed, 0 failed, 0 skipped, including 10 new workflow component/transport tests. |
| `.venv/Scripts/python.exe -B scripts/run_investigation_e2e.py --suite all` (first attempt) | 18 passed, 3 failed. Legacy list-response watcher used old endpoint; new unauthorized-navigation helper incorrectly expected case content; empty queue revealed unfocusable scroll-region accessibility defect. Fixed without relaxing assertions. |
| Complete Chromium attempt 2 | 20 passed, 1 failed: modal-boundary test incorrectly rejected focus moving to browser chrome; background inertness assertion retained. |
| Complete Chromium attempt 3 | 18 passed, 3 failed: existing velocity calculation returned 503 (cause not established), release check correctly detected metadata changed during the run, and Escape exposed a real focus-return defect. Modal now explicitly closes before returning focus; source/identity frozen before final run. |
| Runner `--mode workflows --label workflows-final` | 86 passed, 1 failed, 0 skipped. `test_invalid_requests_are_rejected_without_feature_reflection[score]` failed during context creation with `ClockUnavailable`; observed DB high-water 1794784666 vs now 1794784665. No security guard relaxed. |
| Runner `--mode workflows --label workflows-confirmed` | **87 passed, 0 failed, 0 skipped**: 21 new workflow tests plus existing case and gateway tests. Passing confirmation does not establish clock stability. |
| Final complete Chromium verification, same `--suite all` command, frozen candidate | **21 passed, 0 failed, 0 skipped (2.9 minutes)**. Includes existing batch, design, investigation and workbench suites plus both new workflow cases. UI/API identity comparison passed. |
| `.venv/Scripts/python.exe -B scripts/run_investigation_e2e.py --suite workflow` | **2 passed, 0 failed, 0 skipped**; complete assignment/reassignment, discovery, history, access-revocation and keyboard/modal workflow; 24 screenshots, zero axe violations at checked views. |
| `npm.cmd run lint`, `npm.cmd run build`, `npm.cmd run format:check` (frontend) | Passed on final frozen candidate; build includes TypeScript checks. 44 modules; CSS 25.62 kB / JS 319.65 kB before gzip. Initial effect reset and test formatting issues corrected. |
| `.venv/Scripts/ruff.exe check backend scripts`, `ruff.exe format --check backend scripts` | Passed; 201 Python files formatted. |
| `.venv/Scripts/python.exe -B scripts/check_publication.py` | Passed, 345 source candidates; private/secret ignore boundaries intact. |

No full backend/Windows/SQLite/pinned-scientific suite rerun is claimed for this frontend subphase. Real-model workflow/gateway/browser tests execute existing fitted RF/Policy/SHAP; preservation checks establish unchanged scientific files, not a newly claimed 4,000-row parity run.

## 3. Security acceptance

| Area | Evidence |
|---|---|
| Authorized queues/search/count/pagination | Real PostgreSQL role matrix; literal `%`/`_` matching; foreign/unassigned IDs cannot leak through totals or pages. |
| Manager and target eligibility | Existing assignment tests: active role/assignee rechecks, forged role/mass assignment rejection, closed/stale rejection, update/audit/commit rollback. New directory restricts active analyst fields. |
| Concurrent assignment | Two writers, one 200 and one 409; one recorded event; stale replay 409. No duplicate consequential retry. |
| Service-level revocation | Role deactivated after dependency resolution still denied inside locked service; cross-analyst history/overview unavailable. |
| Activity redaction | Raw private markers, source/actor/worker details and forged foreign job JSON `case_id` excluded. Unknown actions omitted. Boolean version values rejected. Read audit failure rolls back. |
| Actual saved assessment | New real-model test compares queue route with immutable saved decision and completion event with canonical assessment audit/version. |
| Existing investigation safeguards | Gateway/browser cases cover source/assignment revocation, unsupported requests, idempotency, immutable history and real controlled clock 503. |
| Session cleanup | Browser logout/reload/role/access changes remove protected case, evidence and batch state; no durable browser token. |

## 4. Visual review

- Frozen final UI/API build `d11f3b446186bc199a95005163c6da4e69451dea205fd85297de96acc635d1fe`; public-source digest `86bb7ae4657255e2e8c82fd7e33e38437d4a8f8e78e862d48af3a9a623d395e7`; expected test schema `0016_snapshot_clock`. Image digest remains unknown; no deployment attestation implied.

Screenshots under `runtime/g2-3/screenshots` are synthetic-only local artifacts, not published assets. The final manifest records hashes, dimensions and candidate identity.

| Screen/state | Required viewports |
|---|---|
| Case Queue / Assigned Cases | 1440×1000, 1024×768, 390×844 |
| Case Overview / Assignment Dialog | Same three |
| Activity History / Investigation Workbench | Same three |
| Empty queue / authorization error | Same three |

- Checks: typography/design token consistency, locally scrollable tables, legible statuses, reachable controls, no document overflow, dialog bounds/native focus trap/Escape/return focus, reduced motion and WCAG2 A/AA/2.1 AA axe findings.
- Initial visual inspection led to activity-panel padding, dialog field spacing and wider queue selector refinements. Empty scrollable table now has a labeled, keyboard-focusable region.
- Final **24 workflow PNGs** reviewed across three viewport contact sheets, with selected full-page queue/activity/dialog images inspected directly. Responsive navigation and controls remain reachable; tables scroll locally. No clipped controls or document overflow at checked views; zero axe violations across these captures. Native modal keeps the page background inert; browser chrome can receive focus at a browser tab boundary, as expected.
- Additional **20 existing design-regression PNGs** captured by the complete browser run. The [local manifest](../runtime/g2-3/screenshots/manifest.json) records all 44 PNG hashes/dimensions, viewport checks and frozen candidate identity. Review sheets: [desktop](../runtime/g2-3/screenshots/review-desktop.jpg), [tablet](../runtime/g2-3/screenshots/review-tablet.jpg), [mobile](../runtime/g2-3/screenshots/review-mobile.jpg). Runtime artifacts remain ignored, not published.

## 5. Acceptance boundary

- **PASS: local G2.3 functional and visual acceptance.** Final focused PostgreSQL 87/0/0, React 85/0/0, complete Chromium 21/0/0 (passed/failed/skipped), lint/format/TypeScript/build/publication passed.
- Historical environmental clock failures are retained as evidence. A passing rerun does not establish native clock stability; G0/G1 release acceptance remains blocked.
- Earlier velocity-analysis 503 had no captured reason header; its cause remains **unconfirmed**. Final full browser run passed unchanged analytics. Allowlisted clock/stale reason diagnostics were added for future failures; no speculative evidence/clock fix applied. This remains a reliability risk to investigate on the independent runner.
- No malware scanning, provider validation, regulatory approval, production-capacity/security or accessibility certification is claimed.
- G4/G5 require their own explicit authorization, provider/data-handling evaluation and independent source/label approval; neither starts here.

## 6. Preservation and shutdown

- `.venv/Scripts/python.exe -B runtime/g2-3/finalize.py --stop`: **PASS**. Baseline 364 existing files checked; only allowlisted G2.3 edits changed. `.env`, scientific assets/logic and original backups unchanged.
- Original G1 and G2-clone public-schema fingerprints unchanged; disposable schemas removed. 111 foreign keys checked; zero orphan rows, invalid constraints or invalid indexes.
- Original 16-case G1 cohort remains 6 completed assessments, 10 pending and 4 stored packets. Browser data belonged to disposable schemas; no forced historical completion claim.
- Live demo cluster/schema unchanged (`0012_evidence_foundation`); five demo containers remain running. Stopped only the verified owned rehearsal PostgreSQL container; volumes, records and backups retained.
- Branch and HEAD unchanged; all G2.3 edits remain local/uncommitted. No push, deployment, live migration, credential/role change, external provider activation or regulatory publication.
