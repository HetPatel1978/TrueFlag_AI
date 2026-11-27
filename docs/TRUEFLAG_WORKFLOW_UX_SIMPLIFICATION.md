# TrueFlag workflow UX simplification

Date: 21 November 2026. Scope: existing React application, existing protected services. No scientific/business-logic changes, provider activation, source publication or database migration.

## Audit and capability map — recorded before implementation

| Existing capability / source | New location | Preserved backend contract |
| --- | --- | --- |
| `App.tsx`, `operational-overview.tsx` | Overview; concise attention/workload list | Authorized session-scoped case queue counts; no invented investigation totals |
| `workbench.tsx` Dashboard / `upload-workspace.tsx` | Cases; compact session selector, search and filters | Session membership plus independent case authorization |
| `human-casework.tsx` SupervisorQueue | Role-restricted Review Queue | Existing supervisor escalation queue/actions |
| `batch.tsx`, `provider-usage.tsx`, `release.tsx` | Administration secondary navigation; import shortcut where permitted | Existing admin-only import, usage and release APIs |
| Case Results / Explanation / Workflow | Stage 1: Assess Alert; three risk drivers, expandable full factors/history/provenance | Assessment history/detail/jobs; original RF/policy/SHAP outputs |
| `investigation.tsx` CustomerAccounts / ActivityWorkspace / Sources | Stage 2: Review Evidence; financial overview and preview, expandable sources/analytics/full history | Current case/source authorization, snapshots, Decimal/currency/window analytics |
| PacketWorkspace / `drafts.tsx` | Stage 3: AI Investigation; single main generation action, results and previous investigations | Existing atomic parent/child admission and protected draft/packet lifecycle; no new queue |
| `regulatory-guidance.tsx` | Regulatory Guidance inside AI results | Approved, authorized source resolution; explicit unavailable when no approved corpus |
| `human-casework.tsx` | Stage 4: Human Decision; notes, evidence requests, finding review, escalation and permitted outcomes | Casework revision, assignment and separation-of-duties controls remain server enforced |
| `case-workflows.tsx` ActivityHistory | Secondary Activity History view | Existing protected immutable historical activity |

Confirmed presentation issues: repeated case/assessment headers; nested case/subsection tabs; two competing AI generation controls; multiple unavailable-regulatory notices; five visible model drivers and verbose provenance; repeated simulation warnings; upload-session controls ahead of the main page; large sidebar items with repeated descriptions; concurrent auxiliary reads that can reach protected-read backpressure.

Workflow indicators must use actual backend facts. Navigation or a completed assessment does not prove evidence review, AI completion or a human decision. Missing state remains unconfirmed; failed verification stays unavailable.

## Implementation and verification

### Before / after

| Before | Implemented presentation |
| --- | --- |
| Five large sidebar destinations with descriptions | Four concise, role-aware destinations: Overview, Cases, Review Queue, Administration. Desktop collapse; existing mobile disclosure supports Escape/focus return. |
| Imports and provider usage compete with casework | Administration contains CSV Imports, Provider Usage and Diagnostics. Existing batch/provider deep links still work. Unimplemented settings are not shown. |
| Case tabs plus investigation subnavigation and tool tabs | Four stages in `workflow-navigation.tsx`; Activity History stays secondary. Existing case/evidence/investigation/casework/assessment/activity URLs remain supported. |
| Five model drivers and exposed technical clutter | Three signed drivers initially; explicit expansion retains all 27. Technical Details retains hashes, policy threshold, model identity, run and explanation verification. |
| Customer lists, full pages and calculations compete | Customer/account preview; exact server financial summaries; five transaction previews; expanded records, complete transaction pages, advanced calculations and source/counterparty references. Missing income remains distinct from zero. |
| Two competing AI generation controls | One Generate AI Investigation action uses the existing atomic `/investigation-drafts/start` admission. Parent/child work remains server durable; the browser only requests and polls. |
| Repeated unavailable guidance and large history cards | One Regulatory Guidance component handles authorized current/history citations and retrieval. Previous investigations, deterministic summaries, periods and metadata remain expandable. |
| Many equally prominent casework controls | Notes remain prominent; evidence requests, finding reviews, escalation and supervisory outcomes remain grouped disclosures. Escalation/finding review join existing supervisory/resolution confirmations. |

`workflow-ux.css` reuses existing tokens and readable 17px base typography. No remote assets, new frontend framework, generated model values or arbitrary confidence figures were introduced. Narrow/tablet layouts wrap the case header and assessment grid rather than reducing text size or hiding overflow.

### Reliability and safety

- Existing protected GETs and explicitly read-only evidence queries may retry **once** on HTTP 429, respecting a finite `Retry-After` up to 60 seconds. Cancellation aborts the wait. Authentication, revocation, stale-evidence, clock and other failures are not retried.
- Investigation/assessment/import writes and provider requests are excluded from that retry helper. A contract test verifies that an investigation submission is not automatically resent.
- No backend business logic, database migration, scientific artifact, source approval, `.env`, credentials or original demo records changed. Tests use identity-verified disposable PostgreSQL schemas and existing synthetic fixtures.
- Stage indicators use known server state. An assessment may be saved; evidence/AI review is not marked complete just because its tab was opened. Human decisions remain distinct from model recommendations and verified calculations.

### Screenshots and actual workflow scope

Screenshots are under [`runtime/workflow-ux/screenshots/`](../runtime/workflow-ux/screenshots/), with a synthetic-only manifest. The `before-investigation-desktop.png` baseline came from the preceding G5.3 browser run, **not** a controlled comparison of identical case IDs/data. The comparison above is grounded in the audited components.

After images include Overview, grouped Administration, Assess Alert, Review Evidence, AI Investigation and Human Decision; desktop/tablet viewport checks and accessibility assertions run in Chromium. Exact final run results are recorded below after all checks complete.

The connected investigation fixture and the uploaded alert fixture are separate legitimate data paths. A CSV row does not magically acquire customer transaction history. Imported alerts with no linked evidence still show the missing-evidence state; the investigation journey uses the existing source-linked synthetic cases.

### Provider / regulatory / operational limitations

- **Live Claude remains disabled.** The preceding G5.3 call returned HTTP 400 without verified findings. This UX task made zero external inference calls. The successful browser investigation uses the real coordinator/workers with the explicitly labeled deterministic simulation adapter; it is not Claude quality acceptance.
- **Official Regulatory RAG remains unavailable:** prior approval inventory found zero accepted official-source versions. No reviewer record, citation, label or publication was invented. The UI retrieves through existing governance and must show unavailable when no approved applicable context exists.
- The existing provider-usage backend exposes the Luminal ledger. No unsupported Claude financial dashboard or provider activation switch was added.
- The host remains Windows/WSL2; no independently stable Linux-clock acceptance or production capacity/security certification is claimed. Existing snapshot expiry, clock floor/epoch, authorization, evidence references, numeric verification and human separation of duties remain intact.
- Global recent-activity aggregates and a persisted completion flag for every analyst stage are not supplied by existing APIs; case-specific Activity History remains available. The UI does not invent those backend capabilities.

### Verification record

Initial React verification exposed obsolete navigation/factor-count assertions; these now assert the four stages and three default drivers while still testing expansion to all 27 and protected-role/logout behavior. Final expanded unit suite: **160 passed**; production build and ESLint passed before final minor copy/format verification. Pinned network-disabled Linux ML suite: **178 passed**. Existing PostgreSQL clock/numeric/provider security suite: **53 passed**.

Earlier browser results retained for transparency:

- Guided flow first run: 1 passed / 1 failed; the failure expected the old “Batch Processing” heading, while the actual page correctly said “Imports”. After assertion correction: 2 passed.
- Expanded guided run: 2 passed / 1 failed; new tablet capture detected real horizontal overflow at Assess Alert. Header/grid CSS was corrected; no assertion or text size was weakened.
- CSV suite first run: 4 passed / 2 failed. One helper still searched the old all-factors label; another expected the old batch-only denial heading. Corrected selectors preserve 27-factor expansion and explicit denial assertions. Its passing tests exercised validation diagnostics, worker downtime/partial failures, dispatcher restart/browser refresh, and upload-session isolation/recovery.

### Final verification results

Commands ran from the repository root, except npm commands from `frontend/`. Python commands use `.venv\Scripts\python.exe` on Windows. Linux workers, private fitted artifacts and PostgreSQL were exercised through the existing isolated verification helpers.

| Check / exact command | Final result | Scope and limits |
| --- | --- | --- |
| `npm.cmd test -- --reporter=dot` | 160 passed / 0 failed | Complete React suite, including 27-factor expansion, workflow states, role boundaries, single AI action and read-only retry limits |
| `npm.cmd run build` | PASS | TypeScript and Vite production build |
| `npm.cmd run lint` | PASS | ESLint, zero warnings |
| `npm.cmd run format:check` | PASS | Complete frontend Prettier check |
| `python scripts/run_g5_3_tests.py --security` | 53 passed / 0 failed | Real isolated Linux/PostgreSQL clock, snapshot-integrity and provider contract/security tests; controlled failures remain denied |
| `python scripts/run_ml_verification.py --check tests` | 178 passed / 0 failed | Pinned network-disabled Linux ML tests using the existing artifacts. Full 4,000/12,000/4,000 reference comparisons were not rerun in this UX task; preceding G5.3 parity is historical evidence only |
| `python runtime/local-app/ux_e2e.py --suite batch` | 6 passed / 0 failed | Real CSV upload, mapping, validation, approval, import, RF/SHAP, export, idempotency, worker downtime, restart, session isolation and protected-role journeys |
| `python runtime/local-app/ux_e2e.py --suite all --grep "guided workflow"` | **2 passed / 2 failed** | Final expanded guided Chromium run; both failures returned real fail-closed `503 clock_uncertainty`. Not accepted as a fully passing journey |
| `python scripts/check_publication.py` | PASS | Publication boundary check; does not grant source publication approval |
| `python -m ruff check scripts/run_investigation_e2e.py` and `python -m ruff format --check scripts/run_investigation_e2e.py` | PASS | Shared E2E runner includes simulation fixtures for explicit `--suite all`; real provider activation remains off |

Counts above describe separate suites; earlier overlapping successful reruns are not added. No tests were intentionally skipped in the listed selected suites. No full backend regression suite or fresh complete frozen-reference comparison is claimed.

The final sandboxed build initially failed because esbuild could not read an ancestor directory while resolving `vite.config.ts`. The identical `npm.cmd run build` passed with normal filesystem access; no configuration workaround was added. The last local checks returned HTTP 200 for frontend `/`, API `/health` and `/ready`. Readiness alone does not establish candidate AI-route compatibility or clock stability during a complete investigation.

#### Final guided browser failures

1. The connected analyst journey successfully generated verified simulation findings, inspected the unavailable approved-guidance result and reached human casework. Its consequential escalation POST returned `503 clock_uncertainty` instead of the required 201. The test failed; the write was not automatically retried.
2. Wrong-user access correctly returned 404. The subsequent authorized evidence retrieval returned `503 clock_uncertainty` before the source-revocation assertion could run. That final browser revocation check is **not verified** by this run; the UI withheld protected content.

Passing final guided tests verified role-aware navigation, administration grouping, desktop collapse, mobile drawer/Escape/focus, supervisor assignment, analyst access and assignment audit. An earlier three-test guided run completed the simulation-to-supervisor journey, but cannot replace the final expanded failures. One earlier run ended at login unexpectedly; its cause remains unconfirmed.

The Overview capture initially showed its transient loading state. Added a loaded-summary assertion and reran only `python runtime/local-app/ux_e2e.py --suite all --grep "guided workflow: admin overview"`: **1 passed**, confirming the real authorized summary before capture. Updated the three navigation images. This overlapping single-test run does not resolve the two guided clock failures above.

Sanitized final response diagnostics are in `runtime/workflow-ux/diagnostics/`: path templates, HTTP statuses and allowlisted error codes only. No request payloads, credentials or browser fixture secrets were copied. `clock_uncertainty` alone does not establish whether the host actually rewound or the database time observation was otherwise untrustworthy. No clock settings, snapshot expiration, token epoch, source checks or numeric-verification rules were changed. The test helper's bounded explicit **read refresh** was not exercised in that final run; it cannot retry an escalation or bypass a guard.

#### Visual evidence

| Screen | Desktop capture | Tablet/mobile capture |
| --- | --- | --- |
| Overview | [Overview](../runtime/workflow-ux/screenshots/overview-desktop.png) | Responsive navigation covered in mobile test |
| Administration | [Imports](../runtime/workflow-ux/screenshots/administration-imports-desktop.png) | [Mobile drawer](../runtime/workflow-ux/screenshots/administration-mobile.png) |
| Assess Alert | [Risk assessment](../runtime/workflow-ux/screenshots/assess-alert-desktop.png) | [Tablet](../runtime/workflow-ux/screenshots/assess-alert-tablet.png) |
| Review Evidence | [Financial evidence](../runtime/workflow-ux/screenshots/review-evidence-desktop.png) | [Tablet](../runtime/workflow-ux/screenshots/review-evidence-tablet.png) |
| AI Investigation | [Explicit simulation results](../runtime/workflow-ux/screenshots/ai-investigation-desktop.png) | [Tablet](../runtime/workflow-ux/screenshots/ai-investigation-tablet.png) |
| Human Decision | Casework functionality exercised in guided tests | [Analyst](../runtime/workflow-ux/screenshots/human-decision-tablet.png), [Supervisor](../runtime/workflow-ux/screenshots/supervisor-human-decision-tablet.png) |

Images were collected from several isolated synthetic runs, as the manifest states; some captures precede a later clock denial. Screenshot existence does not prove end-to-end acceptance. Visual inspection confirmed readable primary text, wrapped tablet content, progressive disclosures and explicit simulation/unavailable guidance labels. Full-page screenshots can place fixed navigation midway down the captured document; viewport overflow assertions separately check the live layout.

### Acceptance decision and next action

**UX changes implemented; full integrated acceptance remains blocked.** The selected React, CSV, pinned ML and PostgreSQL security checks pass. Resolve trustworthy clock availability on an independently synchronized Linux runner, then rerun the four guided tests without relaxing any denials. No automatic retries of consequential actions are an acceptable remedy.

The existing local frontend is `http://127.0.0.1:5173`, backend `http://127.0.0.1:8010`; disposable acceptance services use separate ports. The current demo schema is not migrated to candidate 0020/0021, so successful candidate atomic AI orchestration in the isolated environment does not establish its readiness in the schema-0019 local demo. Live Claude compatibility/evaluation/operating authorization, accepted official-source approvals and candidate migration/release acceptance are separate remaining gates. This task made **zero external inference requests**, did not publish sources and did not commit, push or deploy.
