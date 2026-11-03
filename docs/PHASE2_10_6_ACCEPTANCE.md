# Phase 2.10.6 — Full-workflow acceptance (2026-11-03)

## Decision and boundary

**PASS ? Phase 2.10 local synthetic acceptance, within documented limits.** All required local regression/security/recovery checks passed; no critical unresolved failure in the exercised scope. This does not authorize production deployment or certify security/capacity. Starting branch `codex/project-initialization`, commit `9f1263d`; unrelated branding/startup edits are excluded. This subphase adds acceptance evidence, not AI investigation features or production certification.

## Acceptance matrix

| Requirement | Executable evidence | Required invariant |
|---|---|---|
| Complete CSV → results/export | `backend/tests/test_batch_acceptance.py`; `frontend/e2e/batch.spec.ts`; `scripts/benchmark_batch.py` | Explicit mapping/units/import/assessment; actual approved Linux RF/policy/SHAP; verified persisted results |
| Counts, source links, metadata | Cross-stage acceptance and benchmark | Imported + excluded + conflicts = processed; every successful source links to canonical alert/case; exact model/policy identity and income missingness |
| Rejection/reuse/conflict | `test_cross_stage_conflict_reuse_rejection_history_export_and_replay`; `test_csv_imports.py` | Existing source never overwritten; rejected/conflicting rows never scored; matching retries add no assessments |
| Result/export/history parity | Cross-stage test, all benchmark result/export pages, browser workflow | Same case/assessment/score/route/model identity; 27 verified grouped contributions; one assessment history version |
| Auth/owner/case isolation | `test_csv_staging.py`, `test_csv_validation.py`, `test_csv_imports.py`, `test_batch_assessments.py`, `test_batch_export.py`, `test_assessment_api.py` | Anonymous/incorrect roles denied; other-owner/case concealed; aggregate/results/export scope rechecked |
| Role/assignment revocation | In-flight actual computation tests; Chromium revocation scenario | No unauthorized publication; stale case invalidates job; browser clears protected state |
| Malformed/large CSV, approval tampering | Staging/preview/import tests; default 5000-row rejection test | Byte/row/column/cell/JSON/deadline bounds; exact approved SHA/version/units; no partial canonical writes |
| Formula injection / export limits | `test_batch_export.py`; Chromium diagnostics/export | No raw cells in diagnostics; fixed result allowlist; prefix neutralization, row/byte bounds and audit-before-disclosure |
| Concurrent idempotency/capacity | Import/batch/API concurrency tests; four parallel benchmark approvals | One import/intent, unique jobs/assessments, durable retries and no queue overshoot |
| Import worker death | `test_real_linux_process_death_and_restart[False/True]` | Before-commit rollback; committed chunks retained; expired claim recovered; complete count after restart |
| ML worker death / expired lease | `test_assessment_worker.py`; batch crash/recovery and stale-fence tests | Child killed/reaped; retry bounded; stale worker cannot publish; exactly one completed result |
| Dispatcher restart | `test_dispatcher_process_crash_recovers_without_duplicate_jobs[False/True]`; browser restart | Group commit survives; incomplete group rolls back; bounded restart adds no duplicate jobs |
| PostgreSQL interruption | Import/dispatch own-connection termination; persistence rollback tests | Only fixture-owned connection interrupted; prior chunks survive; incomplete writes/audits roll back |
| API/browser restart/logout | Real TCP API/lifespan restart plus Chromium reload/resume; workbench logout tests | Durable intent survives; fresh login/current permissions required; no browser-persisted sensitive state |
| Saturation, downtime, partial failures | Batch capacity/rate tests; browser worker pause/fail scenarios | Backpressure preserves ready members; retrying distinct from terminal manual review; no false score |
| Logs / telemetry / diagnostics | Canary checks, `test_operations.py`, API privacy assertions and Chromium | Fixed metric/log fields, value-free diagnostics, no credential/feature leakage in exercised paths |
| No consequential automation | Cross-stage and load invariants, existing failure tests | Open cases and unchanged dispositions; only model recommendation records, no automatic dismissal/closure/SAR |
| Scientific regression | Pinned Linux ML tests; frozen RF/policy/SHAP replay | 4000 / 12000 / 4000 reference parity; no retraining/semantic changes |

## Reproducible load method

- Run `python -B scripts/run_assessment_verification.py --batch-benchmark` using the existing private pinned Linux verification image and local PostgreSQL. Aggregate-only artifact: `PHASE2_10_6_BENCHMARK.json` (written only on success).
- One generated test schema is created/dropped; no development records/volumes are reset. CSV bytes remain in private container tmpfs. Credentials/service tokens exist only in memory/pipes; model/reference assets are read-only mounts and remain outside Git.
- 100 and 1000 synthetic CSV records: two intentionally invalid income cells per file; **98 and 998 valid cases** must receive actual RF/policy/SHAP assessments. Alternating missing/observed-zero income, varying KYC/spend and unknown recorded state; no saved evaluation features/predictions used as live success.
- Explicit non-exact income column mapping; existing validation and approval binding. Four concurrent matching approval requests; same import identity required. Repeated assessment request must return the same batch/result history. Every bounded result/export page is compared, not sampled.
- Load uses the existing synthetic test JWT issuer (in-memory secret and fixture-only backdated issued-at for the documented Docker clock issue), fresh short-lived tokens, real signature validation and current SQL authorization. Password login/logout/re-authentication are exercised separately in Chromium/auth tests; login latency is excluded.
- Default parser/import/export limits and **120/minute shared actor budget** retained. Test queue cap **20** instead of deployment default 1000 deliberately forces bounded backpressure. Existing groups of 10, two-second dispatch interval and two real worker supervisors. Production configuration is unchanged.
- Linux container: **2 CPUs, 3 GiB, 128 PIDs, 512-MiB tmpfs, one-hour watchdog**; one native numerical thread per scientific child. Cold approved model/SHAP initialization for each case remains unchanged. Shared local PostgreSQL and development services run on the host; no dedicated-hardware isolation or production traffic model is claimed.
- TCP stage durations, request/worker and queued-to-persisted p50/p95/p99; dispatch accepted-to-last-job interval; throughput includes backpressure. Stage API quantiles have small sample counts and are descriptive. Request latency samples exclude retry sleeps; whole workflow duration includes them.
- Memory: sampled cgroup `memory.current` peak plus exact whole-container `memory.peak`; CPU: process plus reaped scientific-child CPU seconds and fraction of the two-core cap. PostgreSQL CPU/RSS excluded. Connection pressure: fixture application-name `pg_stat_activity` counts, sampled every second during import/five seconds during ML; no claim that sampling catches every transient peak.
- 5000 rows exceed the configured **2000-row limit** and must return 413 before any canonical work. Limits are not raised to manufacture a larger success claim.

## Measured load results

| CSV rows | Imported / rejected | Actual assessments | ML seconds | Assessments/s | Worker p50 / p95 | Sampled memory peak | Queue peak |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | 98 / 2 | 98 | 105.805 | 0.9262 | 2054.544 / 2277.310 ms | 512196608 bytes | 20 |
| 1000 | 998 / 2 | 998 | 1070.083 | 0.9326 | 2081.946 / 2338.831 ms | 519172096 bytes | 20 |
| 5000 | Rejected before import (413) | 0 | N/A | N/A | N/A | N/A | N/A |

- Completed 100-row observations: upload **0.055 s**, validation **0.072 s**, import approval through terminal receipt **5.106 s**; 36 backpressure events, 8 fixture DB connections / 2 active observed; CPU **177.051 s** across self/reaped children, **79.13%** of the two-core cap over the workflow. No ML failures, retries, duplicate assessments, lost jobs or case actions. Full-machine resources excluded.
- The [recorded JSON](PHASE2_10_6_BENCHMARK.json) retains all measured quantiles, stage/request samples, counts and limits.
- Completed 1000-row observations: upload **0.069 s**, validation **0.110 s**, import approval through terminal receipt **5.158 s**; 474 backpressure events; 8 fixture DB connections / 2 active observed; CPU **1799.462 s**, **83.18%** of the two-core cap. End-to-end workflow **1081.661 s**; default rate limits remain enabled. Four transient import-admission 429s across both workloads were retried with the same approval keys; no ML retries/failures.
- Accepted-to-last-job dispatch: **80.282 / 996.055 s**, **1.2207 / 1.0020 jobs/s** including backpressure. Queued-to-persisted p50/p95: **18.075/20.596 s** (100 rows), **19.128/20.884 s** (1000 rows). Whole-container exact peak **519925760 bytes (~495.84 MiB)** within **3 GiB**; sampled per-workload peaks differ by sampling method.
- The JSON `queued_to_persisted_latency` field uses immutable `Assessment.created_at`, assigned before transaction commit; it approximates queue-to-persistence and excludes commit acknowledgement. Worker wall latency includes the completed publication call.
- Batch-status API **236 samples**, p50/p95 **14.835/19.311 ms**; results API **44 samples**, **83.063/92.946 ms**; export **3 samples**, **1290.683/1325.746 ms** (small sample, bounded ranges). No sensitive-canary log/API leaks or automatic case actions were observed.
- A measured slow run is not a correctness failure; no invented latency/throughput threshold is used.

## Recovery measurements

- `python -B scripts/run_assessment_verification.py --full-backend` executes all backend/security/fault tests. `PHASE2_10_6_RECOVERY.json` records selected real Linux/PostgreSQL fault scenarios only when the complete suite passes.
- Times cover the **whole test call**, including injection, recovery/reprocessing and assertions; they are not isolated failover latency, an MTTR target or an HA guarantee. Existing deterministic lease-expiry injections test fencing without waiting a full deployment lease; actual OS process kills and owned-connection termination remain real.
- Browser restart is a real Uvicorn listener/lifespan/dispatcher restart, followed by reload/login/resume; abrupt dispatcher process death is independently tested before/after group commit. No shared database/service outage is injected into user data.
- New scientific fault scenarios SIGKILL the actual child at a controlled gate immediately after real RF or verified SHAP returns, before publication; restart uses the unmodified child and must produce one result. This tests scientific-stage boundary loss, not a claim of fault injection inside arbitrary native C++ instructions.

### Recorded recovery scenarios

All **14** selected real Linux/PostgreSQL scenarios passed. [Raw aggregate scenario timings](PHASE2_10_6_RECOVERY.json); durations below are whole test calls, not production MTTR.

| Scenario | Call seconds | Verified outcome |
|---|---:|---|
| Import process death before / after chunk commit | 0.9313 / 0.9615 | Uncommitted chunk rolls back; committed checkpoint retained; restart imports each source once |
| Dispatcher death before / after group commit | 1.1166 / 1.1385 | Exactly two jobs after restart; no lost committed group or duplicate dispatch |
| SIGKILL after actual RF / verified SHAP returns | 4.1472 / 4.9884 | No partial model result; normal restart succeeds with one assessment/recommendation |
| Dispatcher / import owned PG disconnection | 0.2577 / 0.2179 | Incomplete writes roll back; prior chunks survive; processing resumes |
| In-flight bulk-role / assignment revocation | 2.9086 / 3.7462 | Unauthorized/stale result publication rejected; manual review preserved |
| Expired ML lease | 0.2303 | Stale worker fenced; retry state accurately reflected |
| API/dispatcher restart + browser reload/resume | 18.1 | Real Chromium/TCP scenario, including full setup/actions; same batch/history version after re-authentication |

## Executed regression evidence

| Environment / check | Passed | Failed | Skipped |
|---|---:|---:|---:|
| Real Linux/PostgreSQL backend | 514 | 0 | 0 |
| Windows/PostgreSQL | 477 | 0 | 37 |
| SQLite | 313 | 0 | 201 |
| Pinned Linux ML unit tests | 178 | 0 | 0 |
| React component/API tests | 48 | 0 | 0 |
| Real Chromium/Linux/PostgreSQL E2E | 11 | 0 | 0 |

- Frozen **4000 RF / 12000 policy / 4000 SHAP** replay: zero score, route, trace or explanation mismatches; score/reference maximum error **0.0**, SHAP reconstruction maximum **3.1086244689504383e-15**. All **25** private baseline SHA-256 identities match.
- Frontend production build, ESLint, Prettier, Python Ruff lint/format (**122 files**), native/pinned dependency consistency and publication/ignore checks passed; npm production advisory check reported zero known vulnerabilities. This is not a comprehensive dependency/security certification.
- Alembic head upgrade/check passed, no drift: **0011_batch_assessments**, **24 domain tables**, rollback probe retains zero records. No runtime/schema/scientific source changes.
- Initial full backend run: **513 passed, one failed** due to the queue-capacity test's fixed-poll/application-clock assumption. The bounded database-clock fixture fix retains the exact final counts; final Linux rerun **514 passed**. Earlier benchmark-driver schema/timestamp assertions were corrected before recording the successful load artifact; reference outputs and production logic were not changed.
- Existing non-blocking Starlette/httpx TestClient deprecation warning remains. Windows/SQLite skips represent missing PostgreSQL/actual Linux capabilities; real Linux verification supplies acceptance rather than mocked scientific success.

## Security findings and residual risk

- **Malware scanning is unavailable.** Strict CSV/no execution/private storage/access controls are compensating controls, not a scanner or malware-safety claim.
- Active bulk permission remains **admin-only and owner-scoped**. Supervisor scope is the existing workspace, not institutional tenancy. Production IAM, team/tenant modeling, least-privilege SQL roles, TLS/perimeter/global quotas and independent audit storage remain deployment work.
- Browser revocation has existing poll/network delay (identity checks every ten seconds); hidden views await revalidation. Reload discards in-memory session/retry keys; durable import IDs/links and backend idempotency permit safe resume. No offline access or push invalidation is claimed.
- The existing queue-capacity regression exposed a test timing assumption: five immediate polls and application-clock fixture scheduling could leave one durable job unfinished at the assertion. The fixture now uses PostgreSQL time and polls to a bounded terminal condition; expected counts are unchanged and no production scheduler behavior was weakened. The final Linux rerun passed all 514 tests with unchanged production scheduling.
- The existing `decisions` table stores immutable **model policy recommendations**; it is not a human disposition record. Acceptance verifies recommendation uniqueness plus unchanged case state/disposition. Initial benchmark assertions were corrected to this actual schema; no model/reference output was altered.
- Cold per-record initialization and transactional queue/admission contention may dominate throughput. No caching, worker redesign, broker, larger quotas, retraining or scientific change is introduced to improve the measured result.
- Long-duration soak, multi-host failover, network partitions, backup/restore, retention/encryption/source rights, institution-specific threat modeling and representative customer-data quality remain outside local synthetic acceptance. Exported-file retention remains operator policy.

## Regression commands and stop gate

- Linux/PostgreSQL: `python -B scripts/run_assessment_verification.py --full-backend`; native Windows/PostgreSQL and SQLite: `pytest backend/tests -q` with/without `TRUEFLAG_TEST_POSTGRES_URL`, using private migrated test schemas/files.
- Scientific: `python -B scripts/run_ml_verification.py --check tests`, `--check scoring`, `--check policy`, `--check shap`; native Windows scientific limitations are covered with real Linux runs, not mocked success.
- Frontend: `npm test`, `npm run build`, `npm run lint`, `npm run format:check`; Chromium: `python -B scripts/run_frontend_e2e.py`.
- Ruff lint/format, Alembic head/drift, PostgreSQL rollback, private baseline hashes, dependency consistency/advisory and publication/ignore checks. No new schema migration or application feature is intended.
- Stop after verified local commit; no push, AI Investigation, LLM/RAG, automatic case action or Phase 3 implementation. Phase 3 needs a separately approved scope/data-source boundary.
