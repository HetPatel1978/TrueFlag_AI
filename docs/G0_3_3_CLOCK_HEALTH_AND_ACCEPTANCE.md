# G0.3.3 — clock health and release acceptance

**Date:** November 14, 2026 (America/New_York). **Branch/base:** `codex/project-initialization` / `a3b2ba49cd92c4aa0401842fa4999897fdc28713`, existing dirty work preserved.

**Status: INVESTIGATION COMPLETE; RELEASE ACCEPTANCE BLOCKED.** Independent measurement confirms WSL2/PostgreSQL clock instability. Full Linux/PostgreSQL: **945 passed, 4 failed, 0 errors, 0 skipped**. All four failures have direct clock-regression/retained-floor evidence. Snapshot safeguards remain unchanged. No host/guest clock adjustment, live restart/migration, role/credential change by this task, deployment, LLM/RAG activation or push. A private `.env` hash changed during execution without a write by this task; it was neither inspected for values nor overwritten.

## 1. Failure classifications

Baseline: [G0.3.2](G0_3_2_CLOCK_SAFETY_AND_SNAPSHOT_POLICY.md), protected full-suite/guard diagnostics: **929 passed / 6 failed / 0 errors / 0 skipped**.

| Previous failing case | Classification supported by retained evidence |
|---|---|
| Numeric oracle `[inconsistent_kyc]` | Guard refused context before financial calculations: raw DB UTC second was below retained floor by 1 s |
| Packet profile `[multi_currency]` | Expected-success assertion failed after recorded safe clock denial, 1 s regression |
| Expired-lease recovery / stale-worker fencing | Context assembly denied before the test's lease-expiry simulation, 1 s regression |
| Provider process-group deadline | Context preparation denied before provider-timeout checks, 1 s regression |
| API/worker/fresh-process clock test | Its simulated initial time was already below bootstrap floor; corrected in G0.3.2 by choosing a valid injected starting instant, without changing real clocks/state |
| Real worker death/restart handshake | Parent expected `RETRIEVED`; exact original child exception was discarded. Historical cause remains unconfirmed |

The four uncontrolled availability failures are **environmental clock-health failures with correct fail-closed application behavior**, not evidence that a numeric/source verifier accepted tampering. The controlled-start failure was a test setup defect already corrected. Neither classification establishes the historical G0.3/G0.1 failures' original cause.

Current full-suite failures (all `call` phase; no setup errors):

| Exact node, relative to `backend/tests/` | Direct guard evidence / reached boundary |
|---|---|
| `test_investigation_coordinator.py::test_missing_conflicting_multicurrency_reversals_and_decimal_profiles[partial]` | DB second 1794696167 < floor 1794696168; epoch 2, regressed=true; expected successful assembly was safely denied |
| `test_investigation_coordinator.py::test_revocation_and_stale_input_block_publication[source]` | 1794696195 < 1794696196; epoch 2; assembly refused before source-revocation exercise |
| `test_investigation_coordinator.py::test_assigned_analyst_scope_then_reassignment_blocks_result` | 1794696223 < 1794696224; epoch 2; assembly refused before reassignment exercise |
| `test_investigation_drafts.py::test_immutable_history_update_delete_truncate[investigation_draft_runs]` | 1794696279 < 1794696281; epoch 2; context preparation refused before mutation assertions |

These cases remain **failed acceptance cases**. Their downstream assertions were not completed; correct denial is not substituted for a passing functional test. Other dedicated authorization, immutability and clock-revocation cases passed. No uncontrolled clock was frozen or guard reset to obtain a green full run.

## 2. Clock investigation and confirmed/unresolved causes

### Independent bounded measurement

The read-only probe ran outside pytest: no fixtures, injected clocks, fake-time preload or evidence service calls. A capability-dropped Linux container sampled Python realtime, libc `clock_gettime`, libc `gettimeofday`, adjusted/raw monotonic time and a read-only PostgreSQL connection. Windows exchanged 120 correlated pings. Protected evidence: `host-guest-clock-probe.json`, `guest-clock-probe.json`, `clock-rate-comparison.json`, `kernel-clock-discipline.json`.

| Measurement | Observed result |
|---|---|
| Platform | Docker Desktop; WSL 2.5.10.0; kernel `6.6.87.2-microsoft-standard-WSL2`, x86-64 |
| Probe | 120.297 s, 120 host samples; no sampler errors |
| Host backward adjustments detected | 0 during the measurement window; not proof of absolute UTC accuracy |
| Guest backward steps | **8**, seen consistently by Python and both libc reads; approximately −0.836 to −0.975 s |
| PostgreSQL backward samples | **6**, independently sampled at about 5 Hz |
| Sample-to-sample elapsed comparison | Windows wall 119.055439 s; guest raw monotonic 119.055377 s; adjusted monotonic 126.900489 s |
| Adjusted/raw monotonic ratio | **1.06589464**, approximately 6.59% faster adjusted time in this interval |
| Clocksource / namespace | `tsc`; zero monotonic/boottime namespace offsets |
| Kernel discipline query | Read-only `adjtimex`, modes 0: state 0, status 8192, tick 10608 μs, frequency 1.31395 ppm |
| Fake-time environment | No `LD_PRELOAD`, `FAKETIME` or fake-monotonic environment flag in the probe |

These independent results rule out the pytest clock mocks, a snapshot integer-comparison bug or Python alone as the explanation for the measured guest regressions. The kernel's disciplined/raw clock discrepancy and backward realtime steps implicate the environment's clock-discipline/synchronization path. **The specific controller issuing backward adjustments is not identified.** Do not assert that changing clocksource or a particular daemon would fix it.

Clock-discipline fields were interpreted using the [Linux 6.6 clock ABI](https://raw.githubusercontent.com/torvalds/linux/v6.6/include/uapi/linux/timex.h). A kernel state flag reporting OK is not proof that time remains nondecreasing; direct measurements demonstrate otherwise. A read-only scan found no specifically named chrony/NTP/time-sync process in the visible VM namespace; it does not prove that no external/hypervisor controller exists.

### Host health and measurement limits

- Windows Time was running with NTP enabled, but `w32tm /query /status` reported **Leap Indicator 3 (not synchronized), Stratum 0, last successful sync unspecified**. Thus “service running” is not a healthy-time signal.
- Time-Service event 158 reported unsupported `VMICTimeProvider`; this can occur without identifying the guest-clock controller and is **not** asserted as the sole cause. Peer addresses/event message contents were excluded from diagnostics.
- Windows Python 3.11 uses approximately 15.625 ms `GetTickCount64` resolution for monotonic time here. Many sub-2-ms ping RTT measurements therefore quantized to zero. They are **not** zero-latency results or clock-accuracy certification. Backstep conclusions rely on large, independently observed realtime deltas, not those RTT values.
- API bearer time remains Python UTC/PyJWT; evidence deadlines/floors remain PostgreSQL UTC; leases remain existing DB timestamps; elapsed budgets remain existing monotonic clocks. No time source, TTL, authentication grace or lease timeout was changed.

Read-only host commands included `Get-Service W32Time`, filtered `w32tm /query /status`, sanitized Time-Service event IDs/fields and `wsl --version`. No peer/server names or customer information were printed. No `Set-Date`, resync, kernel-clock adjustment, clocksource write, WSL shutdown or Docker Desktop restart was executed.

## 3. Changes and technical justification

| Files | Change / reason |
|---|---|
| `backend/app/core/release.py` | Compatible PostgreSQL readiness now calls the existing durable `SnapshotTime.observe()`; detected uncertainty returns not-ready and is retained across rollback/restart |
| `backend/tests/worker_handshake.py` | Test-only strict, nonce-bound, bounded pipe protocol; progress/error stage classification without raw child text or secrets |
| `backend/tests/test_investigation_coordinator.py` | Existing crash/recovery test uses that protocol; same authenticated retrieval milestone, process kill/recovery/one-packet assertions and **20 s** handshake timeout |
| `backend/tests/test_worker_handshake.py` | Actual Linux pipe tests for batched frames, EOF, timeout, malformed/oversized output, nonce mismatch and safe error categories |
| `backend/tests/test_worker_handshake_security.py` | Actual child processes prove clock rejection and invalid service-token rejection cannot masquerade as readiness |
| `backend/tests/test_clock_health.py` | Controlled readiness regression/recovery, expired-epoch denial, missing-state sanitization and incompatible-schema no-write tests |
| Ignored generated release identities | Updated matching source/build identity; no image deployment |

### Readiness semantics

- `/health` remains process liveness and keeps its existing response.
- `/ready` retains its status-only JSON shape; on clock uncertainty it returns **503**, `{"status":"not_ready"}`, header `X-Readiness-Code: snapshot_clock_unavailable`.
- Protected admin diagnostics include `dependencies.snapshot_clock = available / unavailable / not_checked`; no raw timestamps, customer fields, epoch or private artifacts are exposed.
- Time observation runs only after metadata/Python/schema compatibility succeeds. Incompatible releases cannot advance/reset time state through readiness.
- Readiness is deliberately a **durable security observation**, not a purely read-only ping. A detected regression advances the same epoch; when time catches up, old tokens still cannot revive. SQLite retains its existing basic/schema behavior; evidence-clock support remains PostgreSQL-only.
- This verifies relative clock safety at an observation point, **not external UTC synchronization**. Ready=200 does not waive host/guest clock-health requirements.

### Handshake semantics

- Child emits fixed-schema progress/error/retrieved frames correlated by a fresh nonce passed through stdin, alongside the existing private configuration/service token. It reports only bounded exception categories and phases, never exception messages, DSNs, credentials or evidence.
- Parent accepts retrieval only after successful authorized `get_transactions()` and correct nonce. Wrong token, clock refusal, early exit or malformed output cannot become readiness.
- One global 20-second deadline applies across progress frames; it is not restarted per message. Raw `os.read` framing avoids mixing OS readiness with `TextIOWrapper` prefetch when multiple frames arrive together. This is a justified harness improvement, **not proof that buffering caused the old one-frame failure**.
- Controlled bad-clock/invalid-token child tests use the real PostgreSQL/authentication services and assert zero packet publication. Explicit clock injection is test-only; uncontrolled full-suite cases continue to use actual environment time.

## 4. Verification results

| Run | Passed | Failed | Errors | Skipped | Status |
|---|---:|---:|---:|---:|---|
| Clock/snapshot/readiness/release focus | 54 | 0 | 0 | 0 | PASS |
| Handshake pipes/authenticated denial/crash-recovery focus | 12 | 0 | 0 | 0 | PASS |
| Handshake repeat, same 12 cases × 10 cycles | 120 | 0 | 0 | 0 | PASS; historical failure not reproduced |
| Full Linux/PostgreSQL, 949 collected | 945 | 4 | 0 | 0 | FAIL; four clock-health availability refusals |
| Pinned offline ML unit suite | 178 | 0 | 0 | 0 | PASS |
| Frontend build / lint / formatting | — | — | — | — | PASS, no frontend source change |
| Backend/migration lint; backend/test formatting; publication; diff whitespace | — | — | — | — | PASS; 125 Python files formatted, 303 publication candidates |

Frozen RF **4,000**, policy **12,000**, SHAP **4,000** comparisons passed with zero mismatches; original thresholds, feature contract, private assets and tolerances unchanged. RF maximum absolute error **0**; policy route/trace mismatches **0**, retained/reduction-count differences **0**, Coverage overrides **456**. SHAP model/reference encoded/grouped/base differences **0**; maximum reconstruction residual **3.1086244689504383e-15** (existing tolerance `1e-6`), including 87 missing-income and 22 observed-zero-income records.

Full-suite observer duration: **927.030808 adjusted-monotonic seconds**, with **62** detected wall-clock backsteps; do not interpret this as a calibrated performance benchmark given the measured monotonic-rate discrepancy. The 120-case repetition recorded four environmental backsteps but no handshake failure (76.283079 observer seconds). No timeout was raised, authentication bypassed or failing full suite retried until green. Original child exception remains unavailable; current recurrence diagnostics are now in place.

Security/recovery tests that passed include independent tampered totals/forged reference rejection, producer numeric-bug rejection, expired replay after rewind/rollback, cross-process epoch fencing, controlled role/source revocation, concurrent observers, guard lock timeout, authenticated child denial, real child kill/restart with exactly one packet, and the existing authentication/lease tests. PostgreSQL restart durability was demonstrated in G0.3.2; this task verifies the retained restarted schema and does **not** claim a new physical restart experiment.

Protected local evidence directory: `runtime/g0-3-3/92f795e70f064a1a91e70bbcb9987e0d/`. Reports include `full-acceptance.json`, `full-acceptance-diagnostics.json`, `full-failure-locations.json`, `handshake-120.json`, `ml-results.json`, `final-copy-preservation.json`, `final-preservation.json`, and `handover.json`. These files contain sanitized diagnostics and stay Git-ignored; 26 protected entries had zero unexpected allowed ACL principals. Test containers retained read-only source/model mounts, internal-only networking and bounded resources.

Commands from repository root, using the protected local isolated state and existing pinned images:

```powershell
.venv\Scripts\python.exe -B runtime/g0-3-3/measure_clocks.py
.venv\Scripts\python.exe -B scripts/build_release_manifest.py
.venv\Scripts\python.exe -B runtime/g0-3-3/run.py --mode clock --label focused-clock-readiness
.venv\Scripts\python.exe -B runtime/g0-3-3/run.py --mode handshake --label focused-handshake
.venv\Scripts\python.exe -B runtime/g0-3-3/run.py --mode handshake --cycles 10 --label handshake-120
.venv\Scripts\python.exe -B runtime/g0-3-3/run.py --mode full --label full-acceptance
.venv\Scripts\python.exe -B scripts/run_ml_verification.py --check tests
.venv\Scripts\python.exe -B scripts/run_ml_verification.py --check scoring
.venv\Scripts\python.exe -B scripts/run_ml_verification.py --check policy
.venv\Scripts\python.exe -B scripts/run_ml_verification.py --check shap
.venv\Scripts\python.exe -B -m ruff check backend/app backend/tests backend/alembic
.venv\Scripts\python.exe -B -m ruff format --check backend/app backend/tests
.venv\Scripts\python.exe -B scripts/check_publication.py
git diff --check
.venv\Scripts\python.exe -B runtime/g0-3-3/finalize.py
# From frontend:
npm.cmd run build
npm.cmd run lint
npm.cmd run format:check
```

PowerShell first blocked its `npm.ps1` shim; used the installed `npm.cmd` launcher without changing execution policy. The sandbox then blocked esbuild's ancestor metadata lookup; the approved same build outside that sandbox passed. These launcher failures were not application/build defects. No dependencies were installed or deployment performed.

Reproduction prerequisites: pre-existing pinned `trueflag-assessment-verify:phase2-5` Linux image, protected isolated PostgreSQL state/password, staged approved artifacts and existing `runtime/g0-2/g0_probe.py`. Local runners/measurements are ignored operational evidence, not a self-contained fresh CI installation. PostgreSQL identity/network/volume/source-exclusion guards run before use. Full suite ran against a new database cloned from the retained 0016 rehearsal copy, with per-test schemas; no migration of the running demo occurred.

## 5. Remaining security/reliability risks and required configuration

| Area | Required next operational verification / action |
|---|---|
| Windows time | Repair/validate the approved NTP/managed time policy; require synchronized status and recent successful sync. Do not blindly replace organizational peers |
| WSL2/Docker time | Validate guest/PostgreSQL nondecreasing UTC and clock rates under workload and idle/resume. If instability persists, provide the measured kernel/version/discipline evidence to the platform operator/vendor |
| Maintenance boundary | WSL shutdown, Docker restart, clocksource/discipline changes or host time correction can affect all live services; require a separately authorized maintenance/recovery window. None performed here |
| Acceptance environment | If current VM cannot establish trustworthy time, use a separately provisioned synchronized Linux runner. Do not use fake-time libraries, guard resets or expiry grace to claim healthy-environment acceptance |
| Snapshot integrity | Keep schema 0016, durable floor/epoch, strict 900 s TTL and independent source/numeric checks. An older backup restore still needs trusted-time/key/quarantine handling |
| Lease/auth/elapsed semantics | Existing mechanisms remain unchanged and also rely on healthy operating clocks. No platform-wide time-consensus or irreversible bearer-JWT expiry guarantee is claimed |

No unsupported financial claim is accepted merely to improve availability. Case authorization, revoked-source checks, tampered totals, forged references and stale-worker fencing remain acceptance requirements. Full-suite failures, if any, must be retained rather than relabeled as passing security tests.

## 6. G0.3 acceptance recommendation

**G0.3 remains OPEN / release acceptance FAIL.** Environmental regressions are independently confirmed; the exact clock-adjustment actor and the historical child exception remain unresolved. Fail-closed readiness and better diagnostics do not repair the VM clock. Require operator remediation or a verified synchronized Linux runner, then repeat the unchanged full suite and targeted clock/handshake checks. Do not close G0.3 or promote based solely on focused passes or a successful rerun. The four failed downstream functional exercises still need complete execution on a healthy runner.

## 7. G1 isolated development and preservation

**G1 not started.** Isolated synthetic-data design/development can be separately authorized with the snapshot guard enforced and the clock-health blocker explicitly carried. Reliable integration/release acceptance needs a verified healthy runner; current measurements do not certify this VM as healthy. No live LLM/regulatory source activation is implied.

Preservation/handover:

- Isolated 0016 public copy is byte-fingerprint/catalog identical to its pre-test copy: **59 tables, 111 foreign keys, 153 indexes, zero orphan rows/invalid indexes/constraints**; `fsync=on`, `synchronous_commit=on`. Test schemas cleaned; pre-existing legacy and G0.3.2 restart schemas retained.
- Live schema remains **0012_evidence_foundation**, catalog unchanged; only `operational_metrics` differs from the original retained backup. Other original row fingerprints and the known-good archive SHA-256 are unchanged.
- Of 330 pre-task file fingerprints: **325 unchanged**, four expected changes (release service, coordinator test, two ignored generated identities), one unexpected `.env` mismatch. No task script writes `.env`; it was left as found. This prevents claiming complete configuration preservation or attributing that change to a specific person/process. All frozen scientific assets and unrelated source fingerprints remain unchanged.
- Stopped only the verified isolated rehearsal PostgreSQL container. Its volume, internal network, databases and protected backups remain available. Five existing demo services remain running; no live restart, migration or deployment.
- Branch remains `codex/project-initialization`, HEAD `a3b2ba4`; no commit, push or G1 implementation. Generated source build identity: `3da28146c285742d1ee529f84f7f094f96bb1298d1cc1d55111c27143d72c9f0` (dirty source, not a deployed image).
