# G2.2 — Visual and integration QA

## 1. Environment and release boundary

- Existing owned PostgreSQL 17.11 rehearsal cluster, source/demo cluster explicitly forbidden. Existing isolated G2 database, disposable test schemas; no live demo migration or deployment.
- Chromium uses the working-tree Vite frontend on loopback `15173`, proxied to disposable API `18010`, with actual pinned Linux RF/SHAP and investigation/import workers. These test URLs are temporary, not a handed-over live demo.
- Existing normal authentication/token validation is used (`strict_auth=true`); no timestamp backdating, expiry extension or disabled clock guard. The known local clock instability remains a release limitation.
- Disposable UI ingress bridge is separate from internal PostgreSQL. No database port is published. No `.env` or provider credentials are mounted; no external AI call is activated.
- Final build identity: `df732c5c46386cb51a222a031c85c6c0b6392647a33ecfcfbeeccbd0370265c8`; source SHA-256 `ea825ae61590c743d388f2dcc8797924ffee4a860476fb938ea2b9d6060ad0f7`; dirty working tree at HEAD `a3b2ba49cd92c4aa0401842fa4999897fdc28713`, expected schema `0016_snapshot_clock`. Image digest is unknown; no release tag or deployment is implied.
- Vite's compile-time identity and the test API's mounted release identity use that generated descriptor. Final frozen-source visual verification used this identity. The normal live demo image is not rebuilt.

## 2. Automated results

| Check | Passed | Failed | Skipped | Scope |
|---|---:|---:|---:|---|
| React/component/API contracts | 75 | 0 | 0 | Existing behavior plus terminology, exact Decimal formatting, semantic components and role-scoped navigation |
| Protected PostgreSQL gateway | 15 | 0 | 0 | Real coordinator/actual RF-SHAP-bound reads, idempotency, invalid input, cross-case isolation, revocation and clock denial |
| Complete Chromium suite | 19 | 0 | 0 | 2.7 minutes; 6 workbench, 5 batch, 5 investigation, 3 design tests; retries disabled |
| Final frozen-source visual/browser suite | 3 | 0 | 0 | 20.9 seconds; real RF/SHAP/analytics/summary and batch validation, desktop/tablet/mobile, after final cosmetic refinements |
| ESLint / TypeScript / Vite | PASS | | | Final candidate, 41 modules; JS 309.32 kB / gzip 93.83 kB; CSS 24.18 kB / gzip 5.89 kB |
| Frontend/Python formatting and Python lint | PASS | | | Ruff checked 197 files; Prettier checked frontend |
| Publication boundaries | PASS | | | 333 source candidates; secret/private ignore boundaries verified |
| Source/data preservation | PASS | | | 356 baseline files/private inputs; only intended frontend/test-harness/generated identity changes |

Initial React run failed 15 old-label assertions; after updating their expected business copy (without changing security assertions), one remaining paused-status wording assertion was corrected. These were presentation-test maintenance, not suppressed functional failures. New exact-money tests include values beyond JavaScript safe integer precision, negative amounts, zero and missing values.

The full 19-test run preceded the last cosmetic-only changes (evidence panel alignment, native meter color and a few business labels). The final frozen source then reran all 75 React tests and the 3 real-browser design tests, including actual assessments and summaries. The complete backend/ML regression suites were not rerun for this frontend phase; backend application and frozen scientific files match their original hashes. Counts above are separate overlapping runs, not an additive pass total.

## 3. Screenshot evidence

Screenshots must exist before a screen is marked visually verified. Real files are ignored under `runtime/g2-2/screenshots/`, using synthetic records only.

| Screen | Desktop 1440×1000 | Tablet 1024×768 | Checks |
|---|---|---|---|
| Login | `desktop-login.png` | Not required | Existing logo/watermark retained; captured and reviewed |
| Alerts & Cases / filters | `desktop-cases.png` | `tablet-cases.png` | Captured/reviewed; authorized rows, filters and pagination |
| Case overview and risk drivers | `desktop-case-overview.png`, `desktop-case-empty.png` | `tablet-case-overview.png` | Actual assessment/history and honest empty state; captured/reviewed |
| Assessment pending | `desktop-assessment-pending.png` | Not required | Actual queued state; captured/reviewed |
| Customer/accounts | `desktop-customer-profile.png` | `tablet-customer-profile.png` | Actual customer/account observations; captured; desktop reviewed |
| Supporting Evidence | `desktop-supporting-evidence.png` | Not required | Actual source details disclosure; captured/reviewed |
| Transaction analysis | `desktop-transaction-analysis.png` | `tablet-transaction-analysis.png` | Captured/reviewed; exact totals, locally scrollable table, frequency and concentration |
| Investigation Summary | `desktop-investigation-summary.png` | `tablet-investigation-summary.png` | Actual verified summary/history; captured; tablet reviewed |
| Batch upload | `desktop-batch-upload.png` | `tablet-batch-upload.png` | Actual contract controls; captured; desktop reviewed |
| Batch mapping / validation | `desktop-batch-mapping.png`, `desktop-batch-validation.png` | `tablet-batch-validation.png` | Actual mapping/validation/approval states; captured; desktop validation reviewed |
| Narrow layout | `mobile-cases.png` at 390×844 | | Captured/reviewed; working skip link/reduced motion, local table scrolling |

Automated visual checks: axe WCAG2A/AA/2.1AA tags; document horizontal overflow; visible non-table action bounds; keyboard focus and reduced-motion preference. Wide tables deliberately scroll inside their container rather than clipping the whole page. These are local checks, not an accessibility certification.

All 20 PNG files were recaptured by the final frozen-source run. Viewport dimensions above are browser dimensions; full-page PNG heights vary. An ignored screenshot manifest records actual pixel dimensions, SHA-256 and source/build identity. Representative preview: [tablet investigation summary](../runtime/g2-2/screenshots/tablet-investigation-summary.png).

## 4. Reproduction commands

```powershell
.venv\Scripts\python.exe -B scripts/build_release_manifest.py
# Existing protected G2 rehearsal marker/database must be available and verified.
.venv\Scripts\python.exe -B scripts/run_investigation_e2e.py --suite all
.venv\Scripts\python.exe -B runtime/g2-1/run.py --mode gateway --label g22-gateway
.venv\Scripts\ruff.exe check backend scripts
.venv\Scripts\ruff.exe format --check backend scripts
.venv\Scripts\python.exe -B scripts/check_publication.py
# frontend directory:
npm.cmd test
npm.cmd run lint
npm.cmd run format:check
npm.cmd run build
```

`--suite design` selects only the new visual tests; `workbench`, `batch`, `investigation` select existing suites. `all` includes every Chromium spec, with retries disabled. The runner uses a fresh protected control directory and ephemeral schema for each attempt. Existing opt-in test-fixture controls never become public HTTP endpoints.

## 5. Findings, residual risks and G2.3 readiness

- **PASS for the local G2.2 scope.** Confirmed definition-list accessibility defect corrected by nesting supporting text inside description elements; axe checks pass without disabling rules. Initial full Chromium run was 15 passed/4 failed: that accessibility defect plus stale summary selector, shared-fixture pagination count and renamed assessment navigation assertions. Tests were corrected without weakening authorization or security expectations.
- Visual review confirmed hierarchy/readability and corrected stretched evidence panels and Chromium's default green concentration meter. Layout uses brand teal/blue. Final captures show no page overflow, overlapping panels or clipped non-table actions at tested sizes; wide tables retain local horizontal scrolling.
- Export's internal offset remains unchanged; the field now reads **Rows to skip before export**. Technical evidence/version identifiers remain available for traceability, mainly under disclosure.
- Native independently clock-stable Linux release acceptance remains deferred; the G2.1 full backend failures remain historical unresolved release evidence, not erased by this presentation phase.
- Earlier intermittent browser analytics 503 cause remains unconfirmed. Bounded sequential evidence retrieval and safe error handling are preserved.
- Generic audit browsing, assignment controls, global investigation discovery, cross-session login persistence, team summary sharing and new analyst decisions are not implemented here.
- No claim of production security, AML legal compliance, accessibility certification or completion of an LLM investigator.
- Preservation: original G1 and G2 public-schema fingerprints match; disposable schemas removed; 111 foreign keys checked, zero orphan rows/invalid constraints/invalid indexes. Scientific inputs, original backups, logo and `.env` hashes unchanged. Unrelated release test restored to its exact original bytes after an incidental line-ending rewrite. Only the owned rehearsal cluster was stopped; all data/backups/volumes retained; the five live demo services remain running with schema `0012_evidence_foundation`.
- G2.3 recommendation: review analyst workflows and prioritize assignment/case discovery next, while tracking the independent stable-runner gate. Do not automatically start G2.3 or G3/G4/G5.
- No commit or push; branch and HEAD unchanged. G2.3 has not started.
