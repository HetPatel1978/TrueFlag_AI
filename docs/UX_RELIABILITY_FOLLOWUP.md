# Navigation rate-limit and investigation empty-state correction

## Confirmed findings

- The local account's HTTP budget was at 120 requests with 46.6 seconds elapsed in its window while a batch remained active. This is a request-accounting observation, not proof of host CPU/memory exhaustion.
- `BatchAssessmentService.advance()` debited `_budget()` for every dispatched job. Case workflow, evidence, assessment history and result reads used the same per-account HTTP budget. Normal navigation could therefore be denied while background dispatch consumed its allowance.
- `CaseView` retained its error string after a later successful overview read, leaving an obsolete error visible. Its fixed interval also did not honor a longer HTTP 429 Retry-After.
- With no accessible source records, Investigation showed repeated unavailable notices, tabs, version panels, empty histories and disabled generation controls. None could supply missing transaction evidence.

## Narrow corrections

| Area | Result |
|---|---|
| HTTP request budget | Existing authenticated limit and storage remain unchanged: default 120 requests per 60-second window. Existing unauthorized/hidden requests still count. |
| Background dispatch | Separate rolling allowance, default 120 originated jobs per configured request-window duration. `batch_assessment_dispatch_rate_limit` is configurable from 1–10000. |
| Durable accounting | Count distinct originated job IDs through existing batch items and immutable job creation timestamps. Actor FOR UPDATE serializes concurrent dispatchers. Reused jobs and rolled-back writes do not consume additional admission slots; previous jobs still count after restart/upgrade. No migration or new service. |
| Backpressure | Existing queue capacity, bounded groups, actor/batch capacity, scheduling interval and request/source authorization remain enforced. Reaching the dispatch allowance produces existing durable backpressure. |
| Recovery UI | Case reads use a non-overlapping timeout loop, honor Retry-After, show a disabled retry countdown and clear transient errors on successful authorized reload. Protected case contents remain hidden when access cannot be verified. |
| Missing-source UI | One **Supporting records needed** card with a return to the assessment and **Show details and history**. Detailed tools/history are mounted only after expansion; no disabled generation controls or duplicate warnings appear by default. |

## Boundaries

- Sessions, canonical cases, completed model assessments and audit history are retained. No session reset, synthetic case seeding, fabricated transactions or result insertion.
- Existing clock/snapshot/authentication controls, the 27-feature contract and frozen RF/policy/SHAP artifacts are unchanged.
- No provider activation, regulatory publication, live inference request, commit or push.
- The independent dispatch allowance intentionally no longer competes with HTTP reads. Individual HTTP requests can still legitimately reach their own limit; the UI must obey the returned wait.
- Rate accounting uses the existing immutable job timestamps and database current time. Existing synchronized-clock prerequisites still apply. This is not a replacement for snapshot clock-health controls.
- The indexed batch/job relationships and existing SQL statement timeouts bound the query path. Large historical datasets may benefit from a separately reviewed timestamp index; no production throughput guarantee is inferred from local tests.

## Verification

- PostgreSQL tests cover independent HTTP/dispatch accounting, strict HTTP denial, exhausted-HTTP dispatch, multi-batch concurrency, restart-safe admission accounting, rolling-window expiry, rollback, existing capacity and case authorization.
- Time-window tests use a scoped clock simulation; immutable job timestamps and host/database clocks are not altered. An initial fixture attempted to rewrite job history and was correctly rejected; the test was corrected rather than weakening the guard.
- React tests cover the minimal missing-source screen, explicit detail expansion, revocation cleanup, timed retry and automatic recovery after success.
- Reproducible isolated commands:

```powershell
.venv\Scripts\python.exe runtime/local-app/test_upload_sessions.py backend/tests/test_batch_assessments.py backend/tests/test_assessment_api.py backend/tests/test_case_workflows.py backend/tests/test_batch_export.py
.venv\Scripts\python.exe runtime/local-app/test_upload_sessions.py backend/ml_tests
.venv\Scripts\python.exe runtime/local-app/ux_e2e.py --suite investigation
.venv\Scripts\python.exe runtime/local-app/ux_e2e.py --suite batch
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run build
```

## Acceptance results

| Verification | Actual result |
|---|---|
| Affected Linux/PostgreSQL backend suite | 111 passed, 0 failed, 0 skipped |
| React suite | 140 passed, 0 failed |
| Pinned Linux ML suite | 178 passed; 88 subtests passed; frozen scientific acceptance checks retained |
| Chromium investigation suite | 6 passed: numeric/reference verification, idempotency, partial evidence/abstention, assignment/source revocation, real clock-health denial and concise feature-only state |
| Chromium batch suite | 6 passed: real RF/policy/SHAP, export, failures, revocation, restart/recovery and persistent upload sessions |
| Static checks | Ruff, ESLint, Prettier and TypeScript/Vite build passed; private/publication and whitespace checks passed |

- Two existing browser expectations were aligned with the current UI: expand the assessment-version disclosure before inspecting it, and enter the Evidence route before testing evidence rendering. Authorization, source checks and clock-denial assertions were retained.
- The owned local services were stopped gracefully before rebuilding release metadata, then started without schema migration or record resets. This avoids mixed worker release identities while preserving durable queued work.
- Live read-only Chromium verification: **eight consecutive case-workflow requests returned 200** while the existing batch continued processing; one readiness card, optional details, no default disabled generation controls, and zero automated WCAG-tagged findings in the examined desktop/mobile states.
- A subsequent aggregate observation showed **15 HTTP requests** and **17 background dispatches in the preceding 60 seconds**, with pending and running jobs preserved. These are point-in-time observations, not throughput guarantees.
- The user's selected session contained 2,000 uploaded cases at verification. It was not replaced with another session; older sessions and canonical history remain retained.
- Local artifacts: ignored `runtime/calm-workspace-review/verification.json` and desktop/mobile screenshots. Credentials and raw feature values are excluded from reports and Git.
- Remaining limits: local processing uses the existing bounded worker setup; a large batch can still wait for capacity. Missing supporting records still prevent evidence-backed investigation. Neither RAG nor an LLM can supply an absent transaction history.
