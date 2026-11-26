# Claude clock-health review — November 22, 2026

## 1. Decision

**BLOCKED: the environment is not clock-stable. Live API requests executed: 0.**

Current independent measurements reproduce backward Linux/PostgreSQL time movement. A previously latched regression cleared through the normal observer, but a subsequent observation window reproduced seven fail-closed denials. No application correction is justified by these findings. No host clock settings, services, application source, expiry rules or stored floor values were manually changed.

## 2. Exact failure and classification

`backend/app/services/snapshot_clock.py:57` raises `ClockUnavailable` after committing containment when `int(clock_timestamp().timestamp()) < snapshot_clock.high_water`. The database time is sampled **after** locking the guard row; the floor is committed independently of the caller's transaction.

| Condition | Current evidence |
|---|---|
| Actual database-clock regression | Confirmed: at `13:13:53.625978 UTC`, DB second `1795353233` was below floor `1795353234` (`13:13:54 UTC`), by one integer second |
| Durable containment | The next observer denied access and advanced epoch 2→3; the seven denials were all `ClockUnavailable` at line 57 |
| Previously retained regression flag | Initially true, epoch 2, floor `12:35:41 UTC`; current DB time `13:12:04.859342 UTC` was 2,183 seconds above it. The ordinary observer cleared the flag without resetting the epoch |
| Snapshot expiry | Original parent was created November 20 at `13:41:54.192587 UTC`; its old tokens cannot be reused. Fresh tokens were generated through the authorized evidence service with the unchanged 900-second limit |
| Stale authorization | Not the reproduced cause: active actor, source grants, 17 linked references and release integrity verified in a read-only transaction; successful fresh snapshots retained evidence revision 1 / access revision 2 |
| Lock/storage/application defect | Not demonstrated. This incident follows the explicit regression branch, rather than the SQL-error branch |

All timestamps in this report are UTC observations, not certification against an external trusted time source.

## 3. Measured environment

The existing recovery container/network/system identifier were checked against the isolated recovery state. SQL touched only the isolated recovery cluster, private Claude schema or disposable test schemas. The original demo database was not accessed. Measurement containers had an internal-only network, no provider credentials, no new network attachment, read-only application mounts and no clock-setting capabilities.

| Measurement | Result |
|---|---|
| Windows Time | Service **Stopped**, start type Manual; `w32tm /query /status /verbose` returned `0x80070426` (service not started) |
| WSL/kernel | WSL 2.5.10.0; Linux 6.6.87.2-1; Docker guest clocksource `tsc` |
| Guest namespace / fake-time checks | Monotonic and boottime offsets zero; `LD_PRELOAD` and `FAKETIME` absent |
| Independent sampling | 120.283 host-QPC seconds; 120 host exchanges, 604 PostgreSQL time reads; no sampler errors |
| Windows backward events | 0 in this bounded window; 119.039949 wall seconds versus 119.041614 QPC seconds between first/last exchanges |
| Linux backward events | 8; sampled Python realtime deltas −0.699 to −1.030 seconds; libc realtime/gettimeofday sampled independently in the same guest |
| PostgreSQL backward steps | 6; sampled deltas −0.541 to −1.526 seconds |
| Guest-minus-Windows offset envelopes | −1,039.124 to +733.573 ms over the window; median host QPC round trip 1.420 ms. These are bounded observations, not a fixed correction |
| Guest adjusted/raw monotonic rate | Ratio 1.061313 (approximately 6.13% difference) |
| Read-only kernel time status | `adjtimex(modes=0)` returned 0; that status alone did not predict the observed backward steps |
| Separate default-WSL check | Windows bracket `13:14:55.325477–13:14:55.405484`; WSL `13:14:54.680107722`, approximately 645–725 ms behind; QPC round trip 80.162 ms |

**Confirmed origin boundary:** real guest/kernel realtime instability propagates to PostgreSQL. **Unresolved:** which host/virtualization/time-discipline component causes the adjustments. The stopped Windows service is a separate confirmed health defect; this investigation does not establish that it alone causes guest backsteps. Existing API/worker Python wall clocks share this guest time domain; running application processes were not queried as if they supplied independent clocks.

## 4. Recovery and repeat observations

1. Used the existing `SnapshotTime.observe()` recovery path once database time exceeded the retained floor. No backdating, floor reset, epoch reset or expiry extension.
2. Generated and read 30 fresh authorized snapshots at approximately one-second intervals: **30 passed / 0 denied**. The first expired at `13:27:04 UTC`, exactly 900 seconds after its `13:12:04` observation.
3. Ran a separate 200-iteration, 0.2-second scheduled observation window, including actual authorized snapshot and transaction retrieval: **193 passed / 7 denied**, over approximately 48.38 observed database seconds including query overhead. Reproduction advanced epoch to 3. Later catch-up cleared the flag normally but did not restore epoch-2 authority.

Passing samples therefore **do not** establish sustained readiness. Repeated sampling was diagnostic only; it did not retry a provider request or search for a green window to dispatch.

No service restart was performed. Restarting PostgreSQL cannot repair its shared kernel clock. WSL shutdown, Docker restart or Windows synchronization changes could affect workloads beyond the isolated probe and require a separately authorized maintenance window, as already documented in `G0_3_3_CLOCK_HEALTH_AND_ACCEPTANCE.md`.

## 5. Verification

| Actual execution | Passed | Failed | Skipped |
|---|---:|---:|---:|
| Linux/PostgreSQL controlled snapshot-integrity, durable-clock policy, readiness and worker-handshake/security tests | 38 | 0 | 0 |
| Claude development PostgreSQL integration tests, offline provider transport | 5 | 0 | 0 |

The controlled tests cover exact expiry boundaries, expired replay after rewind, epoch persistence across processes, lock failure, tampered totals, forged references, revoked authority, worker fencing/recovery and authenticated handshake failures. Simulated time is restricted to disposable fixture connections; system clocks were not altered. A database restart was not performed in this task.

Commands from the repository root:

```powershell
python runtime/claude-demo-20261120/development-v2/clock-review-20261122/measure.py sample
python runtime/claude-demo-20261120/development-v2/clock-review-20261122/measure.py authority
python runtime/claude-demo-20261120/development-v2/clock-review-20261122/measure_fast.py authority
python runtime/claude-demo-20261120/development-v2/clock-review-20261122/measure_provenance.py authority
python runtime/claude-demo-20261120/development-v2/clock-review-20261122/tests.py --security
python scripts/run_g5_3_tests.py --development
```

The local test harness reuses `scripts/run_g5_3_tests.py` and its candidate overlays; it selects the five clock/worker test modules instead of Claude schema tests. An initial harness import-path error occurred before pytest and was fixed only in the ignored diagnostic wrapper. These commands require the existing pinned Linux image and protected isolated recovery state; they are not fresh-install CI instructions. No full backend/ML suite was claimed or required for this diagnostic-only change.

Private measurements and sanitized source/ledger receipts are retained under `runtime/claude-demo-20261120/development-v2/clock-review-20261122/`. They contain no customer features, bearer tokens or provider credentials.

## 6. Approval and payload preservation

- Approval ID: `claude-development-review-2026-11-22-v2`; decision remains **pending**.
- Exact request: **11,540 bytes**, SHA-256 `45cf3308e79f6bb86c932dba0e528cdba6b47b1c6b6f5c06d50c0880dcf935a9`.
- Intended model/endpoint remain `claude-sonnet-5-5` / `https://api.anthropic.com/v1/messages`.
- No payload/schema regeneration, approval consumption, paid attempt, compatibility promotion or general analyst activation.
- Before/after ledger: eight historical attempts; **zero v2 attempts**, zero outstanding provider attempts. Historical reservations remain intact.
- The request, owner-approval records, saved preflight and `.env` are checked byte-for-byte against the diagnostic baseline. Source, ML/scientific assets, backups and regulatory approvals were not edited.

## 7. Remaining action

**Stable authorization checks: FAIL. Ready for controlled dispatch: NO.**

An operator must establish synchronized Windows/guest time in an approved maintenance window, or provide an independently synchronized native Linux environment. Then repeat independent wall/QPC/raw/database observations and authorized snapshot checks under idle and workload conditions, with no backsteps or guard denials. Fresh snapshots must use the retained epoch and current grants. Passing one rerun is insufficient.

Only after that evidence is satisfactory should the unchanged exact request be presented for explicit owner approval. Recheck its bytes, source permissions, clock/epoch, snapshot freshness and immutable ledger immediately before any separately authorized one-attempt dispatch. This report does not authorize that request.
