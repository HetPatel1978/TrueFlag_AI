# G0.3.1 — snapshot integrity and intermittent failure investigation

**Date:** November 14, 2026 (America/New_York). **Branch/base:** `codex/project-initialization` / `a3b2ba49cd92c4aa0401842fa4999897fdc28713`; existing dirty work preserved.

**Status: INVESTIGATION COMPLETE — historical root cause UNCONFIRMED; no application fix claimed.** Final Linux/PostgreSQL verification passed **923/923**. Controlled probes establish clock-sensitive behavior and an expiry limitation, not historical causality. **Recommendation: keep G0.3 application acceptance open pending time-authority/residual-risk review; G0.4 not started.**

## 1. Original failing assertion and available diagnostics

Evidence: [G0.3 report](G0_3_DATABASE_RECOVERY_AND_MIGRATION.md), protected `runtime/g0-3/674bf460c1f147fab6dfc9530dd96ed2/{backend-tests,failure-locations}.json`.

| Item | Confirmed observation |
|---|---|
| Failed case | `backend/tests/test_investigation_coordinator.py::test_independent_validation_rejects_tampered_worker_output[total]` |
| Intended assertion | Alter `facts[0].result.observed_total` to Decimal(1), require `VerificationFailed` or `EvidenceUnavailable` from `complete()`, then require zero persisted packets |
| Actual failure location | Line 236: `body = service.assemble(token, claim)`; before altering any total or reaching either assertion |
| Observed result | Evidence snapshot rejection through `investigation_packets.assemble()` → `reader.get_model_assessment()` → `_context()` → `_decode()` → `ReadInvalid` |
| Expected result at that point | Assemble a valid authorized packet; numeric tamper rejection is tested afterward |
| Original expected/actual totals | **Unavailable: numeric verification was not reached.** Do not invent monetary values or claim the original test accepted a wrong total |
| Historical full suite | 910 passed / 1 failed / 0 errors / 0 skipped, 881.363482 s |
| Historical subsequent rerun | All nine tamper cases × ten cycles: 90 passed, 0 failures; not proof of a fix |

Original clock observer: two backsteps during the failed case, wall deltas −0.844808 s / −1.072382 s while monotonic advanced 0.020181 s / 0.020543 s. The rejected predicate/DB-time delta was not captured then. This is correlation, not historical causal proof. No test-contamination or unsupported-publication event was recorded.

## 2. Reproduction strategy and isolation

- Reused only the positively identified G0.3 disposable PG 17.11 cluster: system ID `7708086368135385128`, distinct from live `7702662951311646754`; internal network, no published ports, same pinned PostgreSQL image.
- Created a dedicated G0.3.1 database from the already-upgraded isolated copy. Tests create fresh `tf_ingestion_test_<uuid>` schemas; no live migration, production connection, role/grant change or credential rotation.
- Linux verification uses existing `trueflag-assessment-verify:phase2-5`, read-only application/model/reference mounts, 2 CPUs/3 GiB/128 PIDs, 512 MiB temporary filesystem; no provider credentials or external network route.
- Diagnostics delegate to original functions without changing clocks, claims, return values or exceptions. They retain pseudonymous snapshot/case/source-version handles, revision counters, transaction state, expiry-minus-DB-time, monotonic/realtime samples and exception classes. No bearer/snapshot tokens, raw predictors, private artifact bytes or source records are printed.
- Existing G0 observer records PostgreSQL SQLSTATEs, time-validator failures and clock events. Failed-case history is retained; reruns never remove a failed result.
- Exact original 911-test collection/order ran with unchanged application/existing tests; affected cases, neighboring authorization/revision/recovery tests and new clock probes ran separately. Final full collection included the twelve new probes.
- Existing tests were checked for `freeze_time`, global time/monotonic replacement and system-clock administration. Existing CSV/throttle patches replace local module helpers and fixture job timestamps; no existing test was found changing `time.time_ns()` or the PostgreSQL/host clock. This does not rule out all environmental or teardown conditions.

Local runner commands (repository root; guarded state and owner-only diagnostics under ignored `runtime/g0-3-1/`):

```powershell
.venv\Scripts\python.exe -B runtime/g0-3-1/run.py --mode baseline --label original-order-baseline
.venv\Scripts\python.exe -B runtime/g0-3-1/run.py --mode clock --label controlled-clock-final
.venv\Scripts\python.exe -B runtime/g0-3-1/run.py --mode affected --cycles 10 --label affected-90
.venv\Scripts\python.exe -B runtime/g0-3-1/run.py --mode focused --label neighboring-integrity
.venv\Scripts\python.exe -B runtime/g0-3-1/run.py --mode full --label final-full
```

The full selection inside the pinned image is `pytest backend/tests -q --tb=short -p no:cacheprovider -p g0_probe -p snapshot_probe --basetemp /tmp/g031-tests`, with `TRUEFLAG_TEST_REAL_ASSESSMENT=1`. `affected` explicitly repeats collected items ten times, with ordinary function-fixture teardown; pytest's percentage display reuses duplicate node IDs, so counts come from the result ledger. Diagnostic wrapper overhead and bounded concurrent auxiliary probes mean elapsed scheduling is not an identical replay of historical host load.

## 3. Clock and transaction investigation

| Path / evidence | Time source / semantics | Finding |
|---|---|---|
| `services/evidence_read.py::_context` | PostgreSQL `clock_timestamp()`, whole-second UTC expiry = DB now + 900 | Signed ephemeral expiry is not part of evidence/source revision identity |
| `EvidenceReadService._decode` | Fresh PostgreSQL clock on each call; no JWT-library exp/iat/nbf claim delegation for this custom contract | Signature/issuer/audience, exact claim keys/kind/scope, `now < expires <= now + 900` enforced |
| `_context`, `verify_release` | Current user/case locks, visible authorized membership, source versions, content hashes and case/evidence/access revisions | Current scope is independently recomputed after token validation; a valid time does not grant authority |
| `investigation_coordinator::_now`, `claim`, `_leased`, `recover` | PostgreSQL UTC timestamps; 60 s lease, 45 s deadline; random lease token per attempt | Persisted/restart-safe timestamps preserved; token identity also fences old attempts |
| `assemble` | `time.monotonic()` elapsed budget (45 s), maximum 32 steps | Clock movement does not extend the in-process elapsed limit; it can affect wall-clock lease/recovery eligibility |
| `security/auth.py::create_token`, `current_user` | Python aware UTC issue/expiry and normal PyJWT verification, zero added leeway | HTTP bearer validity is a separate path from custom evidence snapshot expiry; the old G0.1 401 cases are not assumed to have this cause |
| `workers/investigation_worker.py` | Fresh process-private snapshot signing secret; durable worker authentication remains separate | Snapshot signatures are created/used inside execution; an old process's token is not a persisted investigation manifest |
| `evidence.py::atomic` | New SQLAlchemy session/transaction per operation; PG lock 2 s, statement 5 s, idle transaction 15 s limits | Errors roll back; no packet/audit success can survive a failed atomic publication |
| `investigation_verifier.py::verify_packet` | Raw transaction/event timestamps and explicit requested window, Decimal precision 50 | Financial totals, ordering, citations and source identity are independently recomputed; wall time is not substituted for transaction dates |
| Evidence access/link metadata | Python aware UTC `datetime.now(timezone.utc)` for changed-at audit metadata | Authority changes are also revision-fenced; changed-at timestamps alone do not authorize results |

### Controlled observations

Clock faults replace only `SELECT clock_timestamp()` results on a **single synthetic fixture engine**, through a bound `timestamptz` parameter. They do not change PostgreSQL/Windows/Docker clocks, persistent timestamp types, model dates, signing rules or expiration bounds. Event hooks are removed in `finally`.

1. **Two-second backward step:** a genuinely signed snapshot issued at `T` expires at `T+900`. At the original failure's `get_model_assessment` step, returning database time `T−2` gives `expires−now=902`. Diagnostics confirm valid keys/kind/scope, active transaction, `expired=false`, `too_future=true`. The existing guard rejects it with `ReadInvalid`, reproducing the original call path before tampering. No packet is persisted and the snapshot/source revisions remain unchanged.
2. **Time restored:** the same authorized evidence can assemble at `T`. An independent SQL SUM over raw synthetic USD transactions matches the packet total. Replacing it with **that total + Decimal(1)** is rejected by the untouched verifier; packet count remains zero and the failed publication adds no audit rows.
3. **Exact boundaries:** age 0 / 899 seconds accepted; 900 / 901 rejected. Pagination cursor retains the original expiry, proving reads do not silently refresh the snapshot TTL.
4. **Trusted-time limitation:** after rejecting an unchanged snapshot at `T+900`, returning DB time `T+899` makes it time-valid again. The current stateless contract has no durable memory that a token was previously expired. This does not bypass current source/role/revision checks, but **irreversible real-elapsed-time expiry across clock rollback is not provided**.
5. **Recovery:** normal `run_once()` converts the injected rejection into a pending bounded retry with `processing_unavailable` and human review required; after clock restoration, attempt 2 publishes exactly one packet. A recovered/reclaimed job cannot be completed with its old lease token even when clock time moves backward.

## 4. Root-cause classification

| Question | Conclusion |
|---|---|
| Can clock movement cause this exact rejection path? | **Confirmed by controlled fault:** 902 > 900, original assembly call path, unchanged evidence identity |
| Did this exact predicate cause the historical G0.3 failure? | **Unconfirmed**; original-order 911, 90 tamper repetitions, neighboring 129 and final full 923 did not naturally reproduce it. Timing correlation and a matching controlled path are insufficient proof |
| Did original numeric verification accept a forged total? | No recorded acceptance; the failed test never reached numeric verification |
| Is cross-test contamination established? | No; fresh schemas/fixtures isolate authority and data. Passing repetitions cannot exclude all scheduling/shared-state conditions |
| Is strict future-expiry rejection itself an application defect? | It is the current fail-closed rule. Removing it or adding grace would change security policy without proving a safe fix |
| Is expiry independent of clock rollback? | No; confirmed trusted-time limitation. A nondecreasing time authority or separately designed durable expiry policy is needed before claiming that guarantee |

No RF/policy/SHAP, financial verifier, source hash, scope/revision check, authorization guard or expiry rule is changed to manufacture a green result. Historical causality remains explicitly separate from confirmed controlled behavior.

## 5. Changes

- Added [test_snapshot_clock_integrity.py](../backend/tests/test_snapshot_clock_integrity.py): twelve real-PG clock/fencing/integrity probes; existing tests and assertions unchanged.
- Added this report. Diagnostics/launchers/results remain ignored; no production code, migrations, deployment configuration, `.env`, scientific contract or artifact changes.
- The first new boundary-probe run had **8 passes / 2 test-authoring failures** because it looked for a snapshot token on a transaction-page DTO. Corrected the new test to inspect the actual paginated cursor and its unchanged expiry. The corrected ten-case run passed, followed by twelve passed after adding worker recovery/fencing cases. This was a test API-assumption correction, not an application fix or relaxed assertion.
- The post-test read-only checker initially could not start its Docker container (exit 125: relative bind path interpreted as an invalid volume name). Using its required absolute mount path resolved this harness issue; final data/schema/live preservation checks passed. No database command ran in those failed checker launches.

## 6. Negative security and recovery matrix

| Scenario | Verification | Current result |
|---|---|---|
| Tampered total | Raw SQL SUM oracle, packet total +1, independent `complete()` rejection, no packet/audit partial commit | PASS (new controlled probe) |
| Forged evidence record UUID | Membership/reference validation rejects; no packet | PASS (new probe; original tamper matrix also selected) |
| Expired / over-future signed token | Exact 900 s boundary and signed +1 s expiry rejected | PASS |
| Backward clock step | Fail-closed before publication; revision identity unchanged | PASS; availability limitation confirmed |
| Expired token after clock rewind | Time-valid again within original interval if all authority remains current | **LIMITATION CONFIRMED**, not an irreversible-expiry guarantee |
| Source/role revocation after clock restoration | Old snapshot still denied; no packet | PASS (new parameterized probes) |
| Source correction / stale snapshot / cross-case actor | Existing evidence-read/foundation/coordinator tests | PASS in the 129-test neighboring suite |
| Concurrent evidence/access revision | Existing serialized revoke/read and revoke/publication tests | PASS in neighboring suite |
| Worker exception/retry and stale-token fencing | New real-PG probes | PASS |
| Actual worker process death / DB disconnection | Existing coordinator subprocess and transactional failure tests | PASS in neighboring suite |

## 7. Verification results

| Run | Passed | Failed | Errors | Skipped | Status / evidence |
|---|---:|---:|---:|---:|---|
| Historical G0.3 full | 910 | 1 | 0 | 0 | Preserved original failure, not a new run |
| Unchanged original-order Linux/PG | 911 | 0 | 0 | 0 | PASS; 896.301359 s |
| Controlled clock probes, final | 12 | 0 | 0 | 0 | PASS; 14.432727 s |
| Original tamper matrix ×10 | 90 | 0 | 0 | 0 | PASS; 117.964046 s |
| Neighboring source/integrity/worker modules | 129 | 0 | 0 | 0 | PASS; 156.671379 s |
| Final full Linux/PG including twelve probes | 923 | 0 | 0 | 0 | PASS; 882.373623 s |
| Pinned offline ML unit tests | 178 | 0 | 0 | 0 | PASS; raw output retained privately |

The passing original-order run recorded 59 realtime/monotonic backstep observations and two snapshot rejections in expected-negative tests; none in the historical failing tamper case. The 90 tamper repetitions recorded eight backsteps and zero snapshot rejections. Neighboring tests recorded ten backsteps and two expected-negative snapshot rejections. Backsteps alone are therefore not a sufficient failure classifier. These are overlapping test selections, not additive counts of unique tests. Backend Ruff and formatting checks passed for all 118 current files; publication boundaries passed for 293 source candidates.

The final full run recorded **57** backstep observations and ten snapshot rejections: two existing expected-negative cases (forged/expired) plus eight intentional clock-probe rejections. No unexpected natural rejection occurred. The observer captured six synthetic-fixture numeric comparisons, including three mismatched totals rejected by the unchanged verifier; monetary values remain only in the owner-only diagnostics. Both full runs' two bearer-JWT time rejections were the expected expired/future-issued negative tests, not an explanation of the G0.3 snapshot failure.

Frozen replays: **4,000 RF scores, 12,000 policy routes, 4,000 SHAP explanations** passed with zero mismatches. RF maximum error 0; SHAP reference/grouped/base/score differences 0, reconstruction residual `3.1086244689504383e-15`; original tolerances unchanged. Missing-income 87 / observed-zero 22 preserved. All ML runs use `--network none`, read-only assets, no retraining:

```powershell
.venv\Scripts\python.exe -B scripts/run_ml_verification.py --check tests
.venv\Scripts\python.exe -B scripts/run_ml_verification.py --check scoring
.venv\Scripts\python.exe -B scripts/run_ml_verification.py --check policy
.venv\Scripts\python.exe -B scripts/run_ml_verification.py --check shap
.venv\Scripts\python.exe -B -m ruff check backend/tests/test_snapshot_clock_integrity.py
.venv\Scripts\python.exe -B -m ruff format --check backend/tests/test_snapshot_clock_integrity.py
```

Private evidence: labeled `*.json` summaries/diagnostics, `ml-*.txt`, `ml-results.json`, protected state and original-file hashes. Do not publish those directories. Local runner prerequisites include the existing ignored `runtime/g0-2/g0_probe.py` and pinned images; commands are not a self-contained fresh-checkout CI package.

## 8. Residual risks

- Trusted DB/guest wall time remains required for stateless expiry and durable leases. Backsteps can cause availability rejection, defer recovery or revalidate an otherwise current token inside its original time window. No unsupported financial claim, unauthorized case read or stale fenced-worker publication is thereby established.
- Do not replace durable UTC timestamps with monotonic readings: they do not provide portable persisted UTC deadlines across hosts/boots. Any stronger time-authority or irreversible-expiry design needs explicit semantics and cross-process/recovery tests.
- No evidence yet isolates historical rejection to a single predicate; do not label the old failure fixed solely because later runs pass. Diagnostic wrapping and small local workloads do not establish production stability/security certification.
- For a natural recurrence, retain sanitized reject category (signature/claim-shape/expired/future-expiry/clock-read failure), expiry-minus-fresh-DB-time, pseudonymous snapshot/revision handles, SQLSTATE and transaction state alongside wall/monotonic discontinuities. Review host/guest/database time synchronization without silently adding expiry grace. Current observations are local diagnostic instrumentation, not a new deployed monitoring feature.
- Existing G0.1 clock/JWT uncertainty, unapproved regulatory sources/providers, privileged demo SQL role and database-only backup limitations remain as recorded. No live activation or privilege remediation is part of G0.3.1.

## 9. G0.3 acceptance recommendation

**Do not close G0.3 as a resolved historical failure.** Database recovery remains independently verified and the latest application suite is green. However, historical causality is unconfirmed and strict expiry demonstrably relies on trusted database time. Keep the application acceptance gate open until the operating time-authority assumptions/residual risk are explicitly reviewed or a natural recurrence yields a confirmed, remediated cause. This report does not grant that risk acceptance.

## 10. G0.4 recommendation and preservation

**G0.4 not started.** Do not authorize live migration/role changes from this investigation alone. The next decision is the time-authority/fail-closed operating boundary and whether its residual risk permits closing the application gate; runtime least-privilege design remains a separately authorized task.

Isolated least-privilege **design/testing can be separately authorized** while carrying this open risk; it does not authorize live promotion or imply the historical failure was fixed. No G0.4 SQL privileges, roles, credentials or application changes were implemented here.

Final preservation:

- **323 pre-existing source/configuration/private-input files unchanged**, including `.env`, both release identities, original G0.3 utility/report and scientific artifacts. Original archive SHA-256 unchanged.
- Read-only live checks: original cluster identity and schema/catalog unchanged at **0012**; all business-table fingerprints match the original backup. Only the running demo's `operational_metrics` changed. All five live services remain running; backend/DB healthy. No live restart/migration/role or credential change.
- Dedicated test copy: all retained 0015 rows/catalog identical to the pre-test manifest, all temporary fixture schemas removed, regulatory GIN/FK/index integrity valid. No corpus publication, unsupported packet or automatic case action introduced.
- Only the owned disposable PostgreSQL container stopped; original/new copy databases, named volume, internal network and original backup retained. Diagnostics root ACL protected; 30 directory/file entries checked, zero unexpected allowed readers.
- Final evidence additionally includes `final-preservation.json`, `post-tests-preservation.json`, `resource-handover.json`, `source-preservation.json` in the protected ignored run directory.
- New unignored files: this report and the twelve-case test module only. Branch remains `codex/project-initialization`, base `a3b2ba4`; **no commit, push or deployment**.
