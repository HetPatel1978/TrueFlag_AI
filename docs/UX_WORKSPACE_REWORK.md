# Task-first TrueFlag workspace — November 18, 2026

## Scope

Reorganize existing functionality around user tasks, improve readability and show details on demand. Reuse current API contracts and components; do not introduce a second frontend, speculative dashboards, model behavior changes or live LLM activation.

## Navigation and capability map

| Area | Entry / scope | Retained functions |
| --- | --- | --- |
| Cases | `#/`, all authorized roles | Assigned/all-accessible queues, search, expandable filters/sort, bounded pagination |
| Imports | `#/batch`, existing admin permission | Upload, contract/template, mapping, explicit units, validation, explicit approval, durable import, explicit assessment, results, resume and bounded export |
| Reviews | `#/supervisor-review`, supervisor/admin | Existing escalation queue and independent human review |
| Administration | `#/admin/provider-usage`, admin only | Existing protected provider/balance/usage status and disabled/blocked controls |

Case navigation exists in one place, inside the case, rather than duplicating it in the sidebar.

| Case section | Route | Presentation |
| --- | --- | --- |
| Overview | `#/cases/{id}` | Stored risk signal/recommendation, top five verified SHAP factors, expandable complete factors, model provenance and assessment history; clear continuation actions |
| Evidence | `#/cases/{id}/evidence` | Customer, account/relationship, transaction and source views; technical references are expandable |
| Investigation | `#/cases/{id}/investigation` | Deterministic summary and explicitly labeled AI/simulation findings; human notes/decisions grouped under `#/cases/{id}/casework` |
| Activity | `#/cases/{id}/activity` | Existing authorized chronological case activity |

The existing `#/cases/{id}/assessment` action route remains available for explicit first/repeated assessment. Existing URLs continue to resolve; the investigation route now starts with summaries/findings, and customer/transaction evidence has its own evidence route. No backend endpoint or authorization contract changes.

## Readability and disclosure

- Root text size 17px; navigation approximately 18px. Existing CSS values below 0.9rem raised to 0.9rem. Inputs/buttons have at least 46px height, pagination at least 44px. These are implementation measurements, not an accessibility certification.
- Desktop sidebar 300px, medium-screen sidebar 270px. Mobile uses a labeled Menu button with expanded state and closes after navigation. At narrow widths the import stepper shows the current step without shrinking its text.
- Sticky case navigation retains the current case reference. Source IDs, hashes, version details, complete histories, unused forms and advanced filters are expandable.
- Batch progress defaults to completed, running, waiting and manual-review counts. Waiting combines undispatched plus queued jobs; retries remain a subset of queued jobs. Detailed persisted counters remain available without double-counting the retry subset. Import approval and assessment start remain separate explicit actions.
- Queue-capacity/rate-limit messages explain waiting and server-side continuation. No invented ETA or queue position. Underlying single-worker throughput, shared request budget and queue capacity are unchanged.
- Complete 27-feature SHAP display is retained behind Show all factors. Financial values remain exact existing strings; no rounding, imputation, source edits or fabricated customer names.
- Simulation restrictions, missing/contradictory evidence and manual-review outcomes remain visible. Technical identifiers may be collapsed; substantive verification/authorization checks are unchanged.

## Boundaries and known gaps

- Resume uses the supported saved import link/ID. There is no new all-uploads directory or mocked import history; that requires an authorized listing API.
- Administration exposes existing provider status only. No invented user-management, model-promotion or provider-activation screen.
- No new LLM/RAG calls, autonomous disposition/SAR submission, source publication, scientific-artifact edits or database migration. Original demo and unrelated work remain preserved. The current local remembered-login behavior is retained.
- Temporary browser fixtures allow only their exact `http://127.0.0.1:15173` origin, matching the browser-session origin check. This does not relax running application origins or authentication.

## Verification

- React, build, lint, browser workflow and visual results are recorded after final acceptance below. Fixtures use synthetic records and disposable `tf_frontend_acceptance_*` PostgreSQL schemas on the approved isolated cluster; they do not reset the application's cases.
- Screenshots and the read-only desktop/tablet/mobile accessibility report are ignored runtime artifacts under `runtime/ux-rework/`. No provider key or browser credentials are included in reports.
- Initial browser-test failures identified outdated navigation/disclosure interactions, asynchronous logout assertions and the missing fixture origin. Updated tests explicitly expand the relevant controls and wait for completed logout; underlying security, complete SHAP, idempotency and workflow assertions remain.

### Final acceptance

| Check | Actual final result |
| --- | --- |
| React component/API/session regressions | 131 passed, 0 failed |
| Real Linux/PostgreSQL CSV/RF/SHAP/export/restart/revocation Chromium suite | 5 passed, 0 failed |
| Real human casework/supervisor/source-revocation Chromium suite | 3 passed, 0 failed |
| Real desktop/tablet/mobile/keyboard/reduced-motion/design Chromium suite | 3 passed, 0 failed |
| Running-application visual scan | 18 screens; no page overflow or automated WCAG-tagged axe findings in the checked states |
| Measured desktop navigation | 300px sidebar; 18.36px navigation text |
| Formatting/lint/build | Prettier, ESLint, fixture Ruff and TypeScript/Vite passed |

The final design check found a genuine keyboard-access issue after text enlargement made the transaction table overflow horizontally. All scrollable tables now expose labeled focusable regions and visible focus outlines; the unchanged accessibility assertion then passed. Initial failed runs remain failures in their retained logs and are not included in the passing counts above.

Reproduction (repository root):

```powershell
.venv\Scripts\python.exe runtime/local-app/ux_e2e.py --suite batch
.venv\Scripts\python.exe runtime/local-app/ux_e2e.py --suite human
.venv\Scripts\python.exe runtime/local-app/ux_e2e.py --suite design
node runtime/local-app/ux-review.mjs
# From frontend:
npm.cmd test
npm.cmd run lint
npm.cmd run format:check
npm.cmd run build
```

The local runner delegates to the existing acceptance server, verifies the approved cluster/container and uses disposable schemas. It writes screenshots/results into ignored runtime directories. The complete frozen 4,000 RF / 12,000 policy / 4,000 SHAP suites were not rerun for this presentation-only change; real fitted RF/policy/SHAP execution was exercised through the batch/browser workflow. Scientific assets, schemas and production authentication/authorization rules were not changed. These local checks are not production capacity or accessibility certification.
