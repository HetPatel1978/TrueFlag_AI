# G1.1 - cohort acceptance and clock remediation

**Decision: BLOCKED.** A clock-stable runner was not established. No retained cohort job was resumed, no new cohort assessment/packet was created, and G2 was not started. Host/WSL clock settings, live demo, credentials, SQL roles and scientific artifacts were not changed.

## 1. Clock-health findings and environment changes

| Environment / observation | Current evidence |
|---|---|
| Windows Time | W32Time running/manual; leap indicator 3 (unsynchronized), stratum 0, Local CMOS Clock, last successful sync unspecified |
| Docker/WSL probe 1 | 60.355773 s on Windows QPC; 60 correlated samples, 4 guest backsteps, 4 PostgreSQL backsteps, 300 read-only DB samples, 0 sampler errors |
| Docker/WSL probe 2, after CSV fixture workload | 60.391901 s on Windows QPC; 60 correlated samples, 6 guest backsteps, 5 PostgreSQL backsteps, 299 read-only DB samples, 0 sampler errors |
| Windows backsteps observed | 0 in both bounded windows; absolute UTC accuracy is not established |
| Guest negative realtime deltas | Approximately -0.717 to -0.949 s; independently seen by Python/libc and PostgreSQL sampling |
| Adjusted/raw monotonic ratios | 1.06020916 and 1.06037719; approximately 6.02% / 6.04% faster adjusted clocks in these windows, not calibrated performance baselines |
| Existing Ubuntu distribution | Already running WSL2, kernel 6.6.87.2-microsoft-standard-WSL2, tsc; systemd-timesyncd active, NTPSynchronized=yes; direct sampling nevertheless observed 2 realtime backsteps |
| Ubuntu sample timing | 35.007769 adjusted-monotonic seconds; 33.025215 raw-monotonic seconds; this discrepancy precludes treating its synchronization flag as clock-stability proof |
| Available Docker contexts | Two local npipe endpoints; no independently synchronized native Linux/remote runner was supplied |

- Re-read G0.3.1/3.2/3.3 and G1 reports; inspected current snapshot creation/expiry, floor/epoch, readiness, worker lease and CSV claim code.
- Restarted only the positively identified retained rehearsal PostgreSQL container. Internal-only network, no published DB ports, expected image/volume/ownership label; isolated cluster system ID differs from the live source. Reused the G1 database, schema 0016; no migration or role changes.
- Probes are read-only, outside pytest, capability-dropped; no fake-time preload. Clock reads include realtime, libc, adjusted/raw monotonic and PostgreSQL clock_timestamp(). Sampling establishes actual backsteps, not just test correlation. Counts are observations, not an exhaustive event count.
- The specific adjustment controller remains unproven. Finding an active Ubuntu timesyncd is new diagnostic evidence, not proof it caused the jumps. No daemon was stopped, traced, reconfigured or installed; no clocksource write, resync, Set-Date, WSL shutdown or Docker Desktop restart.
- Source readiness still observes the durable floor/epoch and returns 503 during detected uncertainty. A 200 between backsteps is not environment certification. The strict 900-second limit and independently committed epoch fencing remain unchanged. These source guards are not claimed as newly deployed to the unchanged schema-0012 demo.

## 2. CSV claim investigation and correction

- Original node: `backend/tests/test_csv_imports.py::test_distinct_admin_imports_share_source_constraints`; retained G1 interrupted-run exception: ImportLeaseLost at `csv_imports.py::process_chunk`, entry type fence, before upload/source/evidence-reference verification.
- Historical diagnostic did not record the actual claim value or eligibility/lock state. The exact original trigger remains **unconfirmed**; do not relabel it as a proven source-integrity, authorization or clock defect.
- Confirmed queue contract: `claim()` returns ImportClaim or None. Pending rows require `available_at <= now`; `FOR UPDATE SKIP LOCKED` may legitimately find no available row. The production CSVImportWorker already treats None as an idle poll.
- Two new controlled PostgreSQL regressions reproduce None from (a) a CSV-service test-local two-second rewind before availability and (b) an explicitly held row lock. Passing that None to process_chunk reproduces the same entry exception. Neither mechanism reads/accepts forged source records.
- Both regressions verify zero canonical writes/attempts on an empty poll, durable pending state, correct eventual processing after test-clock restoration/lock release, and no duplicate case on another worker poll.
- Unmodified original test plus both regressions, five independent fixture cycles: **15 passed / 0 failed**. Natural historical failure was not reproduced.
- Narrow correction: original uniqueness-race fixture now explicitly establishes a shared eligible CSV-service time (`max(available_at)+1 second`) after both approvals, checks both returned values are distinct ImportClaim instances, then races ingestion. This isolates the intended source-uniqueness invariant from unrelated wall-clock eligibility. Only this fixture clock is injected; host/PostgreSQL clocks, snapshot guards, authorization, source hashes, token checks and real elapsed processing deadlines remain intact.
- Corrected original plus both regressions, five cycles: **15 passed / 0 failed**. This is a corrected fixture precondition with regression coverage, **not proof of the historical trigger or clock remediation**.

| Changed file | Scope |
|---|---|
| `backend/tests/test_csv_imports.py` | 12 insertions/1 deletion: explicit eligibility and typed/distinct claims in one existing test |
| `backend/tests/test_csv_claim_safety.py` | Real Linux/PostgreSQL empty-poll, fail-closed entry fence and recovery regression cases |
| `backend/tests/test_multicurrency_packet_integrity.py` | Standalone evidence-only, later-currency ordering/reference/total checks without inventing a model assessment |

No application, scientific, queue, worker, authorization or source-verification implementation was changed.

## 3. Final state of all 16 scenarios

Read-only inspection verified catalog seed 1701/source identities, all admitted release manifests and typed rows, original case/alert feature bindings, current active admin/source access, assessment/job provenance and stored result hashes. This is static integrity verification, **not time-valid publication acceptance**.

| Scenario | Assessment | Stored packet outcome | Expected eventual handling / boundary |
|---|---|---|---|
| `ordinary` | succeeded | packet_ready | packet_ready_with_limits |
| `velocity` | succeeded | packet_ready | packet_ready_with_limits |
| `related_transfers` | succeeded | packet_ready | packet_ready_with_limits |
| `concentration` | succeeded | packet_ready | packet_ready_with_limits |
| `flow_change` | succeeded | none | packet_ready_with_limits |
| `high_kyc` | succeeded | none | packet_ready_with_limits |
| `partial_customer` | pending | none | packet_ready_with_limits |
| `missing_income` | pending | none | packet_ready_with_limits |
| `zero_income` | pending | none | packet_ready_with_limits |
| `corrections` | pending | none | packet_ready_with_limits |
| `conflicting_kyc` | pending | none | abstained |
| `incomplete_history` | pending | none | abstained |
| `source_revision` | pending | none | v2 evidence; immutable v1 model inputs; old snapshot rejects |
| `source_revocation` | pending | none | with active access: limited packet; after explicit revocation: deny |
| `multi_currency` | pending | none | packet_ready_with_limits |
| `unknown_time` | pending | none | abstained |

- Assessments: **6 succeeded, 10 pending, 0 failed/running**; stored packets: **4 packet_ready**, no new packets. Pending is not classified as failed, rejected or abstained.
- Conflicting KYC, incomplete history and unknown event time should eventually produce the catalog's limitations/behavioral abstention. That is a valid expected outcome, not a requirement to force a successful criminal-risk conclusion.
- Source-revocation scenario remains intentionally active until its separate explicit exercise; setup does not automatically revoke/regrant it. All cases remain open with no human disposition, dismissal, closure or SAR action.
- Every release was reconstructed through the existing verify_release() logic. Six immutable assessment/SHAP/audit bundles passed stored-content validation; four stored packet/manifest hashes matched. Current packet publication/retrieval validation remains gated; a matching stored hash does not prove current authorization/time-validity.
- **59 tables, 111 foreign keys, 153 indexes, zero orphan rows / invalid constraints / invalid indexes.** Inspection left the complete cohort fingerprint unchanged.

## 4. Security, provenance and recovery checks

| Check | Evidence this subphase |
|---|---|
| Empty CSV claims, worker permissions, revocation, source approval/tampering, lease fencing, rollback/recovery | Relevant real PostgreSQL CSV/evidence safety suite passed |
| Wrong-user/cross-case access, forged account references, source revocation and stale revisions, duplicate/concurrent setup | Six G1 non-inference security cases included in that suite |
| Forged packet references and financial totals | Existing tamper matrix included; standalone multi-currency case additionally rejected a forged ID, valid USD IDs substituted into a CAD fact, and a changed CAD total; every failed completion persisted zero packets |
| Multi-currency correctness | Original valid evidence-only packet then published with four independently verified facts (USD/CAD count/totals + concentration), explicit no-assessment selection; no fake RF score |
| Expired replay / forward-backward clocks / authorization restoration / epoch fencing / readiness | 54 controlled clock, snapshot and release checks passed |
| Worker crash/restart, authorization, sanitized child diagnostics | 12 worker security/recovery checks passed |
| Production time policy | Unchanged; fixture-local simulation does not establish host clock health |

## 5. Test results and exact commands

| Current G1.1 run | Passed | Failed | Errors | Skipped / excluded |
|---|---:|---:|---:|---|
| CSV original + two counterexamples, before correction, five cycles | 15 | 0 | 0 | 0 |
| Corrected CSV + counterexamples, five cycles | 15 | 0 | 0 | 0 |
| CSV/evidence/G1 security and tamper fixtures | 51 | 0 | 0 | 0 skipped; 16 actual G1 inference pipelines deliberately deselected |
| Clock/snapshot/readiness/release focus | 54 | 0 | 0 | 0 |
| Worker security / crash recovery | 12 | 0 | 0 | 0 |
| Standalone multi-currency packet integrity | 1 | 0 | 0 | 0 |
| Pinned offline ML | 178 | 0 | 0 | 0 |
| Full G1 inference/cohort acceptance | ? | ? | ? | NOT RUN: stable-clock prerequisite failed |
| Full Linux/PostgreSQL on a stable runner | ? | ? | ? | NOT RUN: no stable runner established |

Counts are separate runs with overlap, not a single combined pass total. The earlier G1 full result (997 passed/5 failed) and G1 focus (46 passed/1 failed) are historical baselines, not rerun results here.

- Current frozen comparisons: **4,000 RF scores**, max absolute error **0**; **12,000 policy routes**, route/trace mismatches **0**; **4,000 SHAP explanations**, reference/model/group/base differences **0**, maximum reconstruction residual **3.1086244689504383e-15** within unchanged 1e-6 tolerance. No model/reference/policy changes.
- Stateless model parity ran with external networking disabled. Passing it is not a clock-health or stateful application acceptance result.
- Lint and formatting: `backend scripts` passed, 192 formatted files. Final publication check passed for 313 candidates, with private/secret ignore boundaries intact. Runtime/API/worker/frontend code and dependencies unchanged; no new application/frontend image build or deployment was needed. Pytest imports/execution verified the changed test modules.

```powershell
.venv\Scripts\python.exe -B runtime/g1-1/measure_clocks.py --label observation-1
.venv\Scripts\python.exe -B runtime/g1-1/run.py --mode csv --cycles 5 --label csv-before-fix
.venv\Scripts\python.exe -B runtime/g1-1/measure_clocks.py --label observation-2
.venv\Scripts\python.exe -B runtime/g1-1/run.py --mode csv --cycles 5 --label csv-after-fix
.venv\Scripts\python.exe -B runtime/g1-1/run.py --mode clock --label clock-security
.venv\Scripts\python.exe -B runtime/g1-1/run.py --mode handshake --label worker-security-recovery
.venv\Scripts\python.exe -B runtime/g1-1/run.py --mode safety --label csv-evidence-safety
.venv\Scripts\python.exe -B runtime/g1-1/run.py --mode multisafety --label multi-currency-security
.venv\Scripts\python.exe -B scripts/run_ml_verification.py --check tests
.venv\Scripts\python.exe -B scripts/run_ml_verification.py --check scoring
.venv\Scripts\python.exe -B scripts/run_ml_verification.py --check policy
.venv\Scripts\python.exe -B scripts/run_ml_verification.py --check shap
.venv\Scripts\python.exe -B -m ruff check backend scripts
.venv\Scripts\python.exe -B -m ruff format --check backend scripts
.venv\Scripts\python.exe -B scripts/check_publication.py
git diff --check
```

Read-only platform commands included Get-Service W32Time, w32tm /query /status, wsl --list --verbose, docker context ls, and existing Ubuntu timedatectl/systemctl status queries. Peer addresses, credentials, feature values and raw source records were excluded from logs.

Protected evidence: `runtime/g1-1/4b3f2aa3b7c844129e7506fcd4a6b909/`. JSON reports contain clock samples/summaries, current test results, exact scenario/case/source IDs and static-integrity results. Existing ignored local runners/pinned images/private approved assets are prerequisites; this is not a self-contained public CI acceptance claim.

## 6. Prepared recovery artifact

- New isolated-cohort custom-format pg_dump: **959,871 bytes**, SHA-256 **4c434d36ebd5a8a316be2e4b40d6ea893b4d58883b86725ddd85dc8da4034c79**. pg_restore --list parsed **1,403 archive entries** successfully.
- Owner-protected/Git-ignored; no upload, transfer or restore. Listing and digest verification are **not a successful restore rehearsal**. Existing source backup/recovery artifacts remain retained.
- A separately approved runner can restore a copy with existing approved roles, then verify all 16 identities and preserved history before processing. Do not overwrite a database, create roles or stage private scientific assets externally without an explicitly approved target.

## 7. Required remedy and approval boundary

| Option | Required action / limitation | Current status |
|---|---|---|
| Independent synchronized native Linux runner | Supply an approved runner outside this failing Windows/WSL clock environment; securely stage SHA-approved artifacts; restore a copy of this cohort, enforce target isolation and repeat health observations before executing jobs | Preferred route to isolated acceptance; no such runner supplied or provisioned |
| Authorized Windows/WSL maintenance | Review existing trusted Windows time-source policy/connectivity and Ubuntu/hypervisor time discipline; correct under an explicit maintenance authorization; then repeat host/guest/PG observations | Not authorized/executed; may affect live services and token deadlines |
| More containers / another current WSL distribution | Does not establish an independent stable clock; both available environments directly exhibited backsteps | Rejected as evidence of remediation |
| Guard reset, clock clamping, expiry extension, blanket fake time | Would hide uncertainty or weaken integrity | Rejected |

- [Microsoft Windows Time tooling](https://learn.microsoft.com/en-us/windows-server/networking/windows-time-service/windows-time-service-tools-and-settings) documents status/configuration and resynchronization operations. After authorization and verification of the existing policy, an operator may consider `w32tm /resync /rediscover`; it changes time and was **not executed**. Do not replace trusted peers, stop timesyncd or assume a resync alone fixes the unknown WSL adjustment controller.
- [Linux time-namespace documentation](https://man7.org/linux/man-pages/man7/time_namespaces.7.html) states that CLOCK_REALTIME is not virtualized by time namespaces. Changing a container boundary is not sufficient evidence of UTC isolation or stability.
- Required future evidence: synchronized trusted-time health, multiple independent idle/workload observations with no observed regressions and consistent clock rates, continuing observation during the unchanged acceptance suite, and retained restart/expiry/epoch/authorization negative tests. Finite passing observations do not prove perpetual clock stability or certify production time accuracy.

## 8. Acceptance and G2 recommendation

- **G1.1 / G1 integrated acceptance remains BLOCKED** by directly measured host/guest time-health failures and absence of an independently stable runner. Do not resume the 10 retained pending jobs or mark the four stored packets currently approved on this basis.
- CSV fixture preconditions and diagnostics are improved; the exact historical trigger remains unconfirmed. Preserve it as a remaining uncertainty rather than declaring a production queue defect fixed.
- After a stable target is approved: restore/verify a copy, resume pending jobs with existing services, obtain catalog-appropriate packets/abstentions, verify idempotency/provenance/financial facts and then execute complete G1/full backend acceptance with clock observers. No model or expected output changes.
- **G2 not started and not recommended for integrated acceptance yet.** No live LLM/RAG, automatic case action, commit, push or deployment.

## 9. Final preservation and service handover

- Final cohort/catalog/row fingerprints are identical to the pre-inspection snapshot; test-schema cleanup passed. No retained assessment, packet, case, source/access revision or snapshot-floor state was changed.
- Checked **342 pre-existing file fingerprints**: only the intended `backend/tests/test_csv_imports.py` changed; all other pre-existing files, `.env`, scientific assets, generated release identities and original backup remain unchanged. Two new regression-test files and this report are the only new publishable files.
- Private diagnostics/backup: **36 owner-protected entries**, protected root ACL, zero unexpected allowed principals. See `final-preservation.json` for the machine-readable handover checks.
- Read-only live identity/revision verification used only the existing container-local configuration, not project dotenv values. Live schema remains **0012_evidence_foundation**; all five existing live demo services remain running. No live restart or migration.
- Stopped only the verified isolated rehearsal PostgreSQL container; all cohort records, databases, volumes, internal network and old/new backups retained. No user/credential/SQL-role/time-setting change or provider activation.
- Branch `codex/project-initialization`, HEAD `a3b2ba4`, existing dirty work retained. **No commit, push or deployment.** G1.1 ends at the clock-health blocker; G2 was not started.
