# Local application integration review

Review date: 18 November 2026. This is an isolated development review, not production acceptance. Existing uncommitted work was preserved; no commit, push, deployment, `.env` edit, live-provider request, or regulatory publication was performed.

## Functionality and verification

| Analyst screen | Existing services and integration | Status |
| --- | --- | --- |
| Overview | Current upload session and authorized case queues supply open, in-review, awaiting-approval, assessment-processing and assigned counts. | Connected; desktop/tablet accessibility check passed. No aggregated recent-activity or investigation workload service is claimed. |
| Cases | Existing case search, assignments, assessment, risk drivers and history. | Existing integration retained. |
| Imports | CSV staging, mapping, validation, approval, durable import, RF/SHAP assessment and authorized export. | Real Chromium/PostgreSQL suite: 6 passed. |
| Case investigation | Existing authorized evidence, financial analytics, packet, offline draft and human casework. One action requests a verified packet and then submits a simulated draft. | Real Chromium draft suite: 6 passed; human workflow suite: 3 passed, including escalation and supervisor decision. |
| Regulatory Guidance | Existing case-authorized reference search and citation resolution; interface displays only official curated results and rechecks a passage before opening it. | Search tested against unavailable corpus. No source is approved for publication; regulatory text is not supplied to simulated drafts. |
| Administration | Existing role-restricted provider usage interface. | Available to authorized administrators; live provider remains disabled. |

The one-action investigation sequences two existing durable jobs in the browser. Closing the page between completion of the first job and submission of the second can interrupt that sequence; the verified packet can be reopened and the simulated draft requested manually. It is not a single crash-safe backend orchestration. The simulated provider is not an LLM. Independent source and numeric checks remain required; findings are not proof of crime. Imported alert features do not automatically create transaction histories. Connected transaction fixtures were used only in isolated tests, not added to the user's workspace.

## Actual verification

- `frontend`: `npm.cmd test -- --run`: 144 passed; `npm.cmd run lint`, `npm.cmd run format:check` and `npm.cmd run build`: passed.
- `runtime/local-app/ux_e2e.py --suite batch`: 6 passed; `--suite drafts`: 6 passed; `--suite human`: 3 passed; `--suite investigation`: 6 passed. The investigation suite initially had 5 passes and 1 failure caused by an obsolete button assertion; the corrected suite passed. These suites exercise different isolated fixtures, not one uninterrupted production journey.
- Linux/PostgreSQL targeted investigation, draft, case workflow, human casework, reference and regulatory-context suite: **130 passed, 2 failed**. Both failures were `snapshot_clock_unavailable` fail-closed denials. A previous run had one such denial and an outdated migration-test expectation; those two tests passed targeted reruns after correcting the test to expect the current head revision. Clock stability is not established by passing reruns.
- Pinned Linux ML suite: 178 passed, 88 subtests; frozen scientific comparisons reported zero mismatches. `scripts/check_publication.py`: passed. No live model inference was performed.
- Overview screenshots at desktop and tablet sizes passed axe WCAG checks with zero reported violations. Other screens were exercised in Chromium; no claim of application-wide accessibility certification.

Reproduce the focused PostgreSQL run with `.venv\Scripts\python.exe runtime/local-app/test_upload_sessions.py backend/tests/test_investigation_api.py backend/tests/test_draft_api.py backend/tests/test_case_workflows.py backend/tests/test_human_casework.py backend/tests/test_references.py backend/tests/test_regulatory_context.py`. Browser suites use `.venv\Scripts\python.exe runtime/local-app/ux_e2e.py --suite <batch|drafts|human|investigation>`; run suites sequentially. They use disposable fixtures on the verified isolated cluster, not the original demonstration database.

## Screenshots

- `runtime/integration-review/overview-desktop.png` and `overview-tablet.png`: current empty local workspace.
- `runtime/integration-review/one-action-investigation-desktop.png` and `one-action-investigation-tablet.png`: isolated synthetic case and offline simulated findings.

## Operational and release blockers

- Live Luminal: disabled. Compatibility, reliable account-wide current balance and conservative upper-bound billing remain unverified; the $200 balance floor is not guaranteed. Historical approval for narrow synthetic probes is not unrestricted authorization for ongoing investigations.
- Regulatory: qualified source approval and independent benchmark labels remain incomplete. No approved corpus or regulatory context injection into findings is claimed.
- Repeated clock-related safe denials remain unresolved. A stable independent Linux runner and complete acceptance are needed before release claims.
- The requested complete navigation, comprehensive activity aggregation, durable server-side chaining and a single continuous end-to-end journey across import and a connected evidence case remain incomplete. No autonomous case decision or filing is enabled.

## Local operation

From the project root in PowerShell:

```powershell
.venv\Scripts\python.exe runtime/local-app/manage.py start
.venv\Scripts\python.exe runtime/local-app/manage.py status
.venv\Scripts\python.exe runtime/local-app/manage.py copy-password
.venv\Scripts\python.exe runtime/local-app/manage.py stop
```

Frontend: http://127.0.0.1:5173. Backend: http://127.0.0.1:8010. The `stop` command preserves database records and backups. The user's reset workspace was left empty rather than seeded with demonstration cases.
