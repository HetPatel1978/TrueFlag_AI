# G0.1 - Linux/PostgreSQL test stability investigation

## 1. Scope and decision

- Baseline: branch `codex/project-initialization`, HEAD `a3b2ba4`; existing audit and branding/startup changes preserved.
- Investigate four intermittent failures; change only evidence-supported defects. No live migration, credential/role change, model/contract/policy/SHAP change or Git push.
- **Historical failures not reproduced; root causes unconfirmed.** The fresh full run passed 884/884; ten isolated repetitions and ten same-interpreter cycles each passed 40/40. Frozen ML verification passed. No application/test fix was justified; this is not a claim that the intermittent condition is resolved.

## 2. Original failures

The [audit](CURRENT_SYSTEM_AUDIT.md#current-full-suite-failures-release-acceptance-is-not-green), `runtime/full-audit-backend-tests.json` and `runtime/full-audit-focused-tests.json` establish the baseline: **880 passed, 3 failed assertions, 1 setup error, 0 skipped**, 2363.11 seconds. All four then passed once in isolation.

| Original test | Original observation | What remains to establish |
|---|---|---|
| `backend/tests/test_assessment_jobs.py::test_case_permissions_and_revocation` | `conftest.py` fixture POST alert returned 401, expected 201; body never ran | Why a newly issued fixture token was rejected |
| `backend/tests/test_cases.py::test_revoked_supervisor_and_inactive_analyst_access` | Assignment returned 401, expected current-role 403 | Token validation versus current-user/role lookup cause |
| `backend/tests/test_csv_imports.py::test_cross_user_isolation_unauthorized_and_case_scope` | Analyst GET import returned 401, expected 403 | Same distinction; no unauthorized-success response was observed |
| `backend/tests/test_references.py::test_withdrawal_serializes_with_inflight_disclosure` | Citation hook did not reach `entered.wait(2)` | Scheduling delay versus an exception/lock failure before the hook |

The original assertions contain insufficient evidence to identify a cause. A denied 401 is not evidence of unauthorized disclosure; a missing event alone is not proof of a PostgreSQL deadlock.

## 3. Reproduction environment and safeguards

| Component | Verified configuration |
|---|---|
| Linux image | `trueflag-assessment-verify:phase2-5` |
| Current image identity | `sha256:29425db4c34a1c89ac73df100a1160220e6370d9cd44d74cfa72f6451dd7fff7` |
| Runtime | Python 3.11.18; pytest 9.2.0; PyJWT 2.15.1; SQLAlchemy 2.0.55; psycopg 3.3.6 |
| PostgreSQL | 17.11; existing protected recovery clone, never the live demo database |
| Resource/IO controls | Original 2 CPU / 3 GiB / 128 PID limits; read-only source/artifact mounts; dropped capabilities; no-new-privileges; 512 MiB scratch |
| Test configuration | Real-PostgreSQL and real-assessment opt-ins; no xdist/shuffle; existing tests and assertion expectations unchanged |
| Schema isolation | Existing `platform` fixture creates a unique `tf_ingestion_test_<uuid>` schema and removes it in `finally`; migrations apply only inside these disposable schemas |
| Secrets | Fresh per-run/per-fixture test signing keys; DB connection supplied through stdin; no credentials, JWT strings, customer features or SQL parameter/text logs persisted by diagnostics |

The original audit recorded the image tag, not its digest; the digest above attests to this investigation's image. No image pull, package installation, clock adjustment, demo restart or live deployment occurred.

## 4. Diagnostics and inspected boundaries

Temporary local observers are under ignored `runtime/g0-1/`; they are diagnostic scratch, not application/test-contract changes.

| Area | Method / confirmed implementation | Interpretation limit |
|---|---|---|
| JWT validation | Observation wrappers call original PyJWT `iat`/`exp`/`nbf` validators unchanged; record exception class, numeric claim-to-validator-time delta and node ID only | Intentional expired/future-token tests may correctly emit rejection events; these must not be mistaken for flaky authentication |
| Guest clocks | Sample realtime versus monotonic every 20 ms; record negative wall/monotonic movement or relative backward adjustment exceeding 100 ms | Sampling cannot exclude shorter transients; no claim that host/guest/DB clocks are synchronized |
| Existing clock workaround | `backend/tests/test_foundation.py::headers()` backdates test `iat` by 2 seconds; production `security/auth.py` retains strict validation | Workaround existence is not proof of the original failures' cause; it remains unchanged |
| Reference concurrency | Observe executor exceptions and reference-test future duration/slow SQL; retain original two-second entry and 1.5-second release expectations | Does not relax timeouts, serialize threads artificially, retry failed assertions or change production locking |
| PostgreSQL failures | SQLAlchemy error observer records exception class/SQLSTATE, never statement text/parameters | Expected constraint/rollback/injected-error tests legitimately generate errors |
| Transactions | `services/evidence.py::atomic`: fresh Session + transaction, 2 s lock timeout, 5 s statement timeout, rollback on exceptions | Code review establishes mechanism; it cannot rule out every runtime schedule |
| Publication locks | `references.py::_context` locks current user/case/context; curator locks use the schema's `reference_sources` OID; withdrawal locks contexts before its event | No fixed global test-source lock collision is evident from this implementation |
| Shared state/lifecycle | `conftest.py`: function-scoped signing secret/schema/engine/client; `main.py` closes dispatcher, retention and metric threads on lifespan exit | This is not exhaustive proof of absence of thread leaks under all failure paths |

A read-only recovery-clone snapshot during the full run showed one other session, zero active/idle-in-transaction/lock-wait sessions, and zero ungranted database locks; transaction isolation was READ COMMITTED, server connection limit 100. This point-in-time sample (`runtime/g0-1/postgres-observation.json`) does **not** establish peak usage or exclude earlier/later contention. No SQL text, identities or table contents were collected.

Observation adds small execution overhead. Results describe this bounded local environment, not production capacity or all possible race schedules.

## 5. Exact commands and results

Executed from the repository root, using the existing installed environment:

```powershell
.venv\Scripts\python.exe -B runtime/g0-1/run.py --repeats 10 --label baseline
.venv\Scripts\python.exe -B runtime/g0-1/run.py --full --label original-full
.venv\Scripts\python.exe -B runtime/g0-1/run.py --cycles 10 --label same-interpreter
.venv\Scripts\python.exe -B scripts/run_ml_verification.py --check tests
.venv\Scripts\python.exe -B scripts/run_ml_verification.py --check scoring
.venv\Scripts\python.exe -B scripts/run_ml_verification.py --check policy
.venv\Scripts\python.exe -B scripts/run_ml_verification.py --check shap
```

The temporary launcher reproduces the existing `scripts/run_investigation_verification.py` clone guards, Docker resource/mount flags and real-ML opt-in; its additions are observation-only pytest hooks and sanitized reporting. Targeted runs select precisely the four node IDs in section 2, with fresh fixtures each time. Full execution uses `pytest.main` arguments:

```text
backend/tests -q --tb=short -p no:cacheprovider --basetemp /tmp/investigation-tests
```

The tracked standard runner remains `.venv\Scripts\python.exe -B scripts/run_investigation_verification.py --full --drafts`; do not attribute the diagnostic launcher's measured result to a separate execution of that command.

| Run | Passed | Failed | Setup/teardown errors | Skipped | Evidence |
|---|---:|---:|---:|---:|---|
| Historical full audit | 880 | 3 | 1 | 0 | Original baseline, not a new G0.1 run |
| Historical isolated rerun | 4 | 0 | 0 | 0 | Original audit record |
| Fresh targeted repetition: 10 x 4 | **40** | **0** | **0** | **0** | `runtime/g0-1/baseline-1.json` through `baseline-10.json` |
| Fresh full Linux/PostgreSQL | **884** | **0** | **0** | **0** | `runtime/g0-1/original-full-1.json`; 822.801 s |
| Same-interpreter cycles: 10 x 4 | **40** | **0** | **0** | **0** | `runtime/g0-1/same-interpreter-1.json`; 40 collected/executed, 43.870 s |
| Two preliminary duplicate-selector collection trials | **8** | **0** | **0** | **0** | `same-process-1.json`, `same-process-repeated-1.json`; only four executions each, not forty |
| Pinned offline Linux ML unit suite | **178** | **0** | **0** | **0** | `runtime/g0-1/ml-verification.json`; existing `trueflag-ml-verify:phase2-4` image |

| Frozen replay | Matched | Differences/failures | Numerical result |
|---|---:|---|---|
| RF scores | **4,000** | **0** | Maximum absolute error 0; `atol=1e-12`, `rtol=0` |
| Policy routes/traces | **12,000** | **0** | Exact routing parity; retained/reduction-candidate totals unchanged for all three policies |
| SHAP explanations | **4,000** | **0**, unavailable 0 | Encoded/grouped/base reference differences 0; score difference 0; maximum reconstruction residual `3.1086244689504383e-15` |

The SHAP replay preserved 87 missing-income versus 22 observed-zero-income records. Group/score tolerance remained `1e-12`, reconstruction tolerance `1e-6`, `rtol=0`. All ML runs used existing pinned images, read-only private assets and `--network none`; no retraining of the frozen RF, artifact modification or saved-reference adjustment. Existing unit tests fit a separate tiny synthetic decision tree for explainer checks; they do not retrain the teammate RF.

The first temporary launcher attempt failed before pytest initialization because its host/container root-path calculation was wrong. The ignored launcher was corrected; that bootstrap error is not counted as an application test failure. No assertion, production path or model behavior changed.

Pytest normalized repeated explicit node selectors to four tests in both preliminary collection trials. The final same-interpreter run explicitly repeated the four collected items ten times, preserving each result/failure and ordinary function-fixture teardown. Its collected count and actual pass count were both **40**; it did not retry failed assertions until they passed. Terminal progress percentages reuse duplicate node IDs and are not the execution counter. Total fresh focused executions were **88**, all passing; these overlap the full suite and are not 88 additional unique tests.

## 6. Confirmed causes and changes

- **No historical root cause confirmed.** All four problematic cases passed in the full run, the isolated repetitions and the same-interpreter repetitions. No fixture, assertion or production code was changed.
- A **real clock observation** occurred during the passing `test_sensitive_read_audit_is_immutable`: realtime moved backwards **11.526 ms** while monotonic advanced **20.075 ms** (relative adjustment -31.601 ms). No failing test/JWT rejection coincided with it. This confirms non-monotonic sampled realtime, **not** the cause of a prior token rejection despite the existing two-second test backdate.
- The only full-run JWT time rejections were the expected expired-token test (`ExpiredSignatureError`) and future-issued-token test (`ImmatureSignatureError`), both at **zero leeway**. No unexpected JWT time rejection was captured.
- The reference read/withdrawal futures completed in **18.367 ms / 12.982 ms** in the full run. The original two-second entry barrier passed; no reference SQL operation exceeded the probe's 250 ms slow-query threshold. Same-interpreter repetitions also completed without future exceptions. These observations do not prove all concurrency schedules.
- SQL diagnostics recorded **149** exceptions in passing tests: 130 immutable-trigger `P0001`, 7 unique `23505`, 2 check `23514`, 1 foreign-key `23503`, 5 deliberate backend disconnections `57P01`, 1 missing-table `42P01`, and 3 injected SQLAlchemy/operational exceptions without SQLSTATE. No `40P01` deadlock, `55P03` lock-timeout or `57014` query-cancellation state was recorded.
- The fresh full run took 822.801 s versus the historical 2363.11 s. The difference alone does not identify host load, scheduler behavior or clocks as the original cause.
- No application, authentication, database, test-fixture or assertion fix is justified by this evidence. Temporary diagnostic-launcher corrections were unrelated to the historical failures and are not application fixes.
- No increased leeway, disabled `iat`/expiry checks, timeout stretching, blind assertion retries or weaker authorization were introduced.

## 7. Remaining risks and G0.2 recommendation

- Passing reruns do not erase the failed historical full run or prove a flaky condition resolved.
- Existing fixture token backdating, observed small realtime discontinuity and short reference barriers remain environmental sensitivity; diagnose a recurrence before changing them. Production clock synchronization and strict unmodified live-login acceptance remain separate gates.
- Public CI lacks these private actual-model assets and this exact host scheduling environment. Diagnostic hooks do not certify production recovery/security.
- On recurrence, retain sanitized JWT validation reason/time delta, active-user lookup outcome, realtime/monotonic samples, original executor exception and PostgreSQL SQLSTATE/lock state. The current time-validator observers cannot explain a signature/issuer/user-state failure that did not recur.
- G0.2 should establish API/UI/worker image/source/schema identity and a reproducible release manifest. Carry unresolved stability uncertainty explicitly; do not automatically migrate/promote the older demo or claim G0 complete.
- Stop at G0.1; source alignment, migration rehearsal, runtime database roles and later product work require their own scoped tasks.

## 8. Repository preservation

- Only this Markdown report is a new unignored deliverable. Diagnostic launchers/JSON remain ignored under `runtime/g0-1/` for local review; their commands depend on that local scratch and the previously provisioned protected recovery clone.
- All 281 pre-existing tracked/unignored files, including six audit documents and unrelated branding/startup work, remain byte-for-byte unchanged. Private `.env` and the 25 baseline-manifest artifacts are verified unchanged.
- No live migrations, database-role changes, production credential changes, model/contract/policy/SHAP changes, commits or pushes. G0.2 was not started.
