# G0.3 — database recovery and migration rehearsal

**Date:** November 14, 2026 (America/New_York). **Branch/base:** `codex/project-initialization` / `a3b2ba49cd92c4aa0401842fa4999897fdc28713`, with the pre-existing dirty candidate preserved.

**Status: INCOMPLETE — database backup/restore/migration/recovery checks passed; full application acceptance is not green (910 passed, 1 failed).** No live migration, deployment, live restart, credential/role change, regulatory publication or external-provider activation is authorized by this report.

## 1. Original database and schema state

| Item | Observed state |
|---|---|
| Source | Local Compose project `trueflag-ai`, service `db`, database `trueflag`, `127.0.0.1:5432` |
| PostgreSQL / application revision | 17.11 / `0012_evidence_foundation` |
| Source image | `sha256:266d3c257594e195b309ae9d1805e54c788f1d7b375f56bf6c367aac6c917e7b` |
| Source cluster system identifier | `7702662951311646754` |
| Public schema | 37 tables including Alembic; 72 foreign keys, 209 constraints, 101 indexes, 58 user triggers, 26 functions |
| Additional existing schema | `tf_ingestion_test_098279ce76e04c76839b899b074f13ea`: 37 tables, three total rows; preserved, not deleted or upgraded |
| Public history | 10 alerts/cases, 11 assessment jobs/assessments/explanations, 345 audit events |
| Typed evidence | Zero sources, transactions, links and bindings; nonempty evidence preservation requires a separate synthetic probe |
| Live services | Existing backend, frontend, assessment worker, CSV-import worker and PostgreSQL; no restart/rebuild requested |

Reviewed [audit](CURRENT_SYSTEM_AUDIT.md), [roadmap](REMAINING_IMPLEMENTATION_ROADMAP.md), [G0.1](G0_1_TEST_STABILITY_REPORT.md), [G0.2](G0_2_RELEASE_IDENTITY_AND_COMPATIBILITY.md), Compose, `backend/alembic/env.py`, migrations 0012–0015, `core/{schema,release,release_metadata}.py`, existing recovery/verification scripts and model checks. The candidate requires **0015**, while the older running demo remains at **0012**. An old deployment's healthy response is not candidate compatibility evidence.

## 2. Backup metadata and integrity

| Property | Result |
|---|---|
| Protected recovery directory | `runtime/g0-3/674bf460c1f147fab6dfc9530dd96ed2/` — ignored by Git, owner-only Windows directory ACL |
| Archive | `source.pgcustom`, PostgreSQL custom format, **407,296 bytes** |
| SHA-256 | `7c224bb4f8864c05518ab66dddae389006e98f99aca4913d97e7b25515d9dbdf` |
| Snapshot timestamp, server-reported UTC | `2026-11-14 17:51:19.704650+00:00` |
| Consistency | Read-only REPEATABLE READ transaction; exported snapshot `0000003D-00000A04-1` shared by `pg_dump` and all source row/catalog checks |
| Completion / TOC | Exit 0; **663 TOC entries**; public tables and table-data entries present; both non-system schemas included |
| Backup/check duration | **1.187 s** locally, including read-only inventory/integrity work; not a production recovery SLA |
| Confidentiality | Raw records, dumps, TOC, fingerprints and generated isolated password remain in protected ignored storage; no globals/role-password dump |

Every domain table is streamed in deterministic JSON-row order; SHA-256 incorporates each row's byte length and bytes. Counts, IDs, feature snapshots, outputs, timestamps and provenance are therefore compared together without printing records. Alembic's revision is checked separately because upgrades intentionally change it. The additional schema's Alembic row and all other rows are also preserved.

Core commands executed by [rehearsal utility](../scripts/rehearse_database_recovery.py), with actual IDs/names in protected `state.json`:

```text
docker exec <verified-source-container> pg_dump -U <existing-source-user> -d trueflag -Fc --snapshot 0000003D-00000A04-1 --lock-wait-timeout=5s
docker exec -i <verified-source-container> pg_restore --list
```

The snapshot ID is valid only while its exporting transaction is open. Do not reuse it for a later backup. Backup contents contain private application data; Git exclusion and checksums are not encryption or an off-host backup strategy.

## 3. Isolated environment and restore verification

- Dedicated PostgreSQL container, internal Docker network and named data volume carry label `trueflag.g0-3.run=674bf460c1f147fab6dfc9530dd96ed2`. No published ports or connection to the live Compose network.
- The exact PostgreSQL image matches the source. **Target system identifier `7708086368135385128` differs from source.** Container ID, labels, image, network and volume are checked before controlled operations; Linux code checks the cluster identifier before database work.
- New bootstrap credentials belong only to the new isolated cluster. Existing application credentials, SQL roles and grants are unchanged.
- Resource limits: PostgreSQL 2 CPUs/1 GiB/256 PIDs; Linux verification 2 CPUs/3 GiB/128 PIDs, read-only application/assets, 512 MiB temporary filesystem, capabilities dropped. Internal networking prevents external-provider egress.
- Six independent restores (`primary`, `repeat`, `failure`, `interrupt`, `synthetic`, `rollback`) matched all source rows, both schemas and revision 0012 before use. A seventh, `invalid`, exercised truncated-archive failure followed by known-good recovery.
- After verification, only the owned recovery container was stopped. Its named volume, internal network and protected backups are retained; all five live services remain running. Restarting this recovery container for inspection requires its recorded isolated identity, not a Compose-wide command.

```text
docker exec <isolated-container> createdb -U rehearsal -T template0 tf_g0_3_<purpose>_674bf460c1f147fab6dfc9530dd96ed2
docker exec -i <isolated-container> pg_restore -U rehearsal -d <verified-disposable-db> --single-transaction --exit-on-error --no-owner --no-acl
```

Restore intentionally **does not restore SQL object ownership/ACLs or global roles**. Those require a separately reviewed privilege plan in G0.4. No `--create`, `--clean`, live restore, forced Alembic stamp or trigger disabling was used.

**Catalog comparison limitation:** PostgreSQL reparsed 20 public CHECK expressions from `ARRAY[varchar literals]::text[]` into equivalent per-literal `::text` casts. Original definitions remain recorded. The comparator normalizes only that exact literal-array form; all other definitions remain exact comparisons. Row fingerprints already matched before this normalization. This was a verifier false alarm, not a migration repair.

## 4. Migration-by-migration results

Application migration scope is **public**, through real Alembic commands. The extra pre-existing test schema remains untouched at its original revision.

| Revision reached | Tables incl. Alembic | FKs checked | Constraints | Indexes | Triggers / functions | Upgrade + integrity-check time | Result |
|---|---:|---:|---:|---:|---:|---:|---|
| 0012 baseline | 37 | 72 | 209 | 101 | 58 / 26 | — | PASS |
| `0013_reference_corpus` | 47 | 92 | 265 | 123 | 79 / 29 | 0.583 s | PASS |
| `0014_investigation_foundation` | 52 | 101 | 293 | 136 | 92 / 33 | 0.430 s | PASS |
| `0015_investigation_drafts` | 58 | 111 | 329 | 152 | 108 / 38 | 0.417 s | PASS |

- 0013 adds ten regulatory/corpus tables, lexical GIN index and immutable/reference-envelope guards.
- 0014 adds five worker/run/request/job/packet tables and publication/envelope guards.
- 0015 adds six simulated-draft run/request/job/attempt/receipt/result tables and budget/envelope/publication guards.
- These upgrades create tables/indexes/functions/triggers; they do not transform historical application rows. All original definitions remain present, all original row fingerprints match after **each** stage, and all checks find zero orphan rows/invalid constraints/invalid indexes.
- Final `alembic check` passed: no model/schema drift detected. All regulatory tables on the upgraded historical copy remain empty; no source approval/publication occurred.
- Times are **combined upgrade and integrity verification**, not pure DDL durations or large-dataset capacity measurements.

## 5. Pre/post record integrity comparisons

| Public history group | Before | After each upgrade / isolated restart |
|---|---:|---|
| Alerts / ingestion receipts / cases | 10 / 10 / 10 | Same counts and complete-row SHA-256 |
| Assessments / SHAP explanations / jobs | 11 / 11 / 11 | Same counts and complete-row SHA-256 |
| Stored model scores / policy decisions | 11 / 11 | Same counts, values and provenance |
| Audit events | 345 | Same count and complete-row SHA-256 |
| CSV uploads / validations / imports / row outcomes | 4 / 3 / 2 / 7 | Identical |
| Batch assessments / items / requests | 1 / 2 / 2 | Identical |
| Public typed evidence | 0 | Still zero; not retroactively fabricated |
| Additional existing schema | 37 tables / 3 rows | Identical, including its revision |

All **36 original public domain tables** are fingerprinted, not only the selected groups above. Operational metrics, workers, users and throttles are included in restored-copy comparisons.

Separate 0012 synthetic copy: existing `EvidenceService` and generator created **six new source-bound cases** (`normal`, `partial`, `missing_income`, `zero_income`, `multi_currency`, `inconsistent_kyc`). It contains 6 sources/versions/bindings/grants, 7 customer versions, 12 accounts, 6 relationships, **64 transaction versions**, 89 identities/record versions/case links, and 16 total cases. Every seeded row remained identical through all three upgrades. These records are isolated synthetic test evidence, **not added histories for the ten live legacy cases**. Actual application tests independently exercise citation/numeric/immutability/provenance constraints.

## 6. API/worker compatibility and verification ledger

| Check | Result |
|---|---|
| Candidate compatibility against restored 0012 | `schema_incompatible`; `require_compatible()` rejects before job writes |
| Candidate against upgraded 0015 | `release_report().status=ready`; compatibility guard accepts |
| Read-only HTTP probes on upgraded copy | `/health` 200 and `/ready` 200; no lifespan/background services started on retained records |
| Preserved source files | 321 pre-existing files unchanged, including `.env`, generated release identities and private scientific inputs; good archive SHA-256 unchanged |
| Live preservation check | Still 0012; all business-table fingerprints unchanged. `operational_metrics` changes from the running demo are recorded separately |
| Backup ACL check | 23 directory/file entries checked; protected root ACL; zero unexpected allowed readers |
| Worker artifact preflight | `sha256_and_dependencies_verified_not_deserialized`; approved dependencies/artifacts/policy verified |
| Full pinned Linux/PostgreSQL backend suite | **910 passed / 1 failed / 0 errors / 0 skipped**, 881.363482 s; fresh per-test schemas inside isolated cluster, never live schemas |
| Focused tamper rerun | Nine parameter cases × ten cycles: **90 passed / 0 failed / 0 errors / 0 skipped**, 109.357985 s; does not override full-suite failure |
| Post-test restored-copy check | All 0015 rows/catalog unchanged, extra schema preserved, fixture schemas cleaned; regulatory GIN index verified; zero invalid indexes/constraints/orphan rows |
| Tool checks | Ruff/format pass; seven SQL-comparator edge/negative checks pass; publication boundary check passes (291 candidates); expected duplicate-backup refusal preserves archive |
| Pinned offline Linux ML unit suite | **178 passed / 0 failed / 0 skipped**, 11.079 s unittest duration |
| RF | 4,000 matched, 0 failures/mismatches, maximum absolute error **0**, atol 1e-12 / rtol 0 |
| Policy | 12,000 routes, 0 route/trace mismatches; retained/candidate totals exactly match all policies |
| SHAP | 4,000 verified; 0 unavailable/mismatches; encoded/grouped/base/score reference differences **0** |
| SHAP reconstruction | Maximum residual **3.1086244689504383e-15**, original tolerance 1e-6; grouping/score tolerance 1e-12, rtol 0 |
| Income semantics | All 87 missing-income and 22 observed-zero reference records verified without contract changes |

Exact host commands, from the repository root (Docker access and existing pinned images required):

```powershell
$env:PYTHONPATH='backend'
.venv\Scripts\python.exe -B scripts/rehearse_database_recovery.py --step backup
.venv\Scripts\python.exe -B scripts/rehearse_database_recovery.py --step provision
.venv\Scripts\python.exe -B scripts/rehearse_database_recovery.py --step rehearse
.venv\Scripts\python.exe -B scripts/rehearse_database_recovery.py --step restart
.venv\Scripts\python.exe -B scripts/rehearse_database_recovery.py --step recover
.venv\Scripts\python.exe -B scripts/rehearse_database_recovery.py --step tests
.venv\Scripts\python.exe -B scripts/run_ml_verification.py --check tests
.venv\Scripts\python.exe -B scripts/run_ml_verification.py --check scoring
.venv\Scripts\python.exe -B scripts/run_ml_verification.py --check policy
.venv\Scripts\python.exe -B scripts/run_ml_verification.py --check shap
.venv\Scripts\python.exe -B -m ruff check scripts/rehearse_database_recovery.py
.venv\Scripts\python.exe -B -m ruff format --check scripts/rehearse_database_recovery.py
.venv\Scripts\python.exe -B scripts/rehearse_database_recovery.py --step finalize
```

The marker `runtime/g0-3/current.json` binds commands to this run; a second `backup` deliberately refuses to overwrite an existing run. `rehearse` requires original restored-copy state and is not an arbitrary resume/reset tool. Backups and volumes are retained; no automated destructive cleanup. The full-suite command uses the existing ignored G0 diagnostics plugin `runtime/g0-2/g0_probe.py` for sanitized counts/clock observations. A fresh checkout needs that local diagnostic prerequisite or an independently reviewed equivalent runner; it is not a self-contained production recovery package. Inside Linux the actual test selection is `pytest backend/tests -q --tb=short -p no:cacheprovider -p g0_probe --basetemp /tmp/g03-tests` with `TRUEFLAG_TEST_REAL_ASSESSMENT=1`.

Detailed local evidence: `source-{records,catalog,integrity,extra-schemas}.json`, `source.toc.txt`, `restore-commands.json`, `rehearsal.json`, `synthetic-before.json`, `post-upgrade.json`, `restart.json`, `known-good-recovery.json`, `backend-tests.json`, `targeted-backend-tests.json`, `token-rejection-observations.json`, `failure-locations.json`, `post-tests-preservation.json`, `resource-handover.json`, `ml-{tests,scoring,policy,shap}.txt`, `ml-results.json`, `original-files.json`, `preservation.json`. Do not publish those private diagnostics.

### Full-suite application failure — retained as a blocker

- `backend/tests/test_investigation_coordinator.py::test_independent_validation_rejects_tampered_worker_output[total]` failed at line 236 while calling `assemble()`, **before** altering/verifying a packet total. The path reaches `EvidenceReadService._decode()` and rejects the evidence snapshot. This is not a recorded SQL migration/restore failure or successful tampered publication.
- The value-free observer recorded two clock backsteps during that same test: wall deltas **−0.844808 s** and **−1.072382 s**, with monotonic intervals 0.020181 s / 0.020543 s. Failure occurred 0.460339 s after the second observation.
- `_decode()` rejects expired evidence tokens and tokens whose expiry exceeds database time plus 900 s. **Clock correlation is observed; the exact rejected predicate was not captured in the original failure. Do not call that root cause proven.**
- A separate ten-cycle rerun of all nine tamper cases passed **90/90** with eight clock-backstep observations and no token rejection. The observer inspected only expiry-minus-database-time and rejection flags on failure; none occurred. The failure was not reproduced and the exact root cause remains unconfirmed. No token-validity check, test assertion or production clock setting was weakened.
- Focused runner: ignored `focused.py` in the protected recovery directory, inside the same verified cluster and pinned image; `G0_TEST_CYCLES=10` and selection `backend/tests/test_investigation_coordinator.py::test_independent_validation_rejects_tampered_worker_output`. Its wrapper delegates to the original `_decode()` unchanged and records only safe temporal diagnostics if it raises.

## 7. Failure and recovery findings

| Scenario — disposable targets only | Injection / observation | Result |
|---|---|---|
| Migration exception | RuntimeError immediately after first 0013 CREATE TABLE | Whole transaction rolled back; revision/catalog/rows identical to 0012; normal retry reached 0015 |
| Interrupted migration | Verified target database/PID, then `pg_terminate_backend()` after first DDL | OperationalError; transaction rolled back completely; normal retry reached 0015 |
| Database restart | Exact owned G0.3 container ID, normal Docker restart with 10 s grace, named volume retained | Primary 0015 catalog and all row hashes identical; API compatibility ready |
| Incompatible revision | Candidate guard on restored 0012 | Rejected without consuming or rewriting jobs |
| Invalid/incomplete archive | Separate archive truncated to half length; original never modified | `pg_restore` failed; single-transaction restore left no application tables |
| Known-good recovery after failed restore | Restore original checksum-verified archive into that empty disposable target | Exact 0012 rows/catalog, both schemas, constraints and FKs recovered |
| Empty-table downgrade | Dedicated copy, 0015 →0014 →0013 →0012 | Exact original public schema/rows recovered; no newer history existed |
| Retained-history downgrade | Dedicated synthetic audit marker for each migration family | All three guards refused; revision/catalog/rows unchanged |

Three preparatory verifier failures were investigated rather than hidden: an additional source schema stopped the initial preflight; SQL cast text differences stopped initial restore comparison; a missing isolated JWT setting stopped Alembic before migration. The verifier now preserves the extra schema, narrowly handles the equivalent cast form and generates an ephemeral isolated JWT secret. **No migration or application defect was repaired or claimed fixed. The Windows host diagnostic error path was also restricted to the Linux `--inside` runtime after an attempted `/recovery/last-error.json` write was denied; no outside-workspace file was written. A duplicate-backup negative check now returns a sanitized expected refusal without overwriting the archive.**

An intermediate finalization attempt correctly reported an extra fixture schema while the focused runner was still active. Finalization was repeated after that runner exited: schema cleanup, all original and upgraded-copy fingerprints, GIN/index/FK integrity and release readiness passed. This was a sequencing precondition, not a retained schema leak.

## 8. Rollback and restore strategy

- **0013:** downgrade refuses any retained regulatory table row or `evidence.reference.%` audit history.
- **0014:** refuses retained coordinator/worker/job/packet/request rows or `evidence.investigation.%` audits.
- **0015:** refuses retained draft rows or `evidence.investigation.draft.%` audits. 0012 likewise protects retained evidence if anyone proposes an older target.
- Tested empty downgrade is a narrow development result. Once any newer history exists, **restore a verified backup into a new database**, compare hashes/constraints and pair it with the matching older release; never delete history, disable triggers or force a revision to make downgrade work.
- Before any future live promotion: separately approve a maintenance window; pause admissions/workers, drain or record active leases, capture final database and required file backups, run verified migrations with migration-owner authority, deploy aligned images, run read-only smoke checks, then explicitly resume workers.
- A pre-upgrade restore loses writes accepted after its snapshot. Choose/approve RPO and reconcile durable jobs/audit/exports before a cutover. Do not replace the live database with this rehearsal snapshot automatically.

## 9. Remaining risks and limitations

- Database-only logical recovery does **not** include staged CSV bytes, model assets, worker token files, application secrets, Docker volume provisioning or external backups. Preserve/verify those separately for full application recovery; historical pending file-import jobs were not resumed against missing staging files.
- New runtime and migration roles are not separated yet. Restore uses a privileged isolated bootstrap user; this does not certify least privilege. Source SQL ownership/grants remain unchanged and are not verified by `--no-owner --no-acl` restore.
- Only local PG 17.11, a small current dataset and six generated evidence scenarios were tested. No large-volume recovery SLA, standby failover, WAL/PITR, storage loss, hard power failure, encrypted/off-host restore or cross-major-version upgrade was tested.
- The additional pre-existing test schema remains on the live source; cleanup needs a separate ownership/retention decision, not an automatic deletion.
- G0.1 historical intermittent failures retain their documented uncertainty. A fresh passing run cannot establish that the original clock/scheduling condition was fixed.
- Regulatory human approval/independent labeling and external-provider permission remain blocked. Isolated tests may create explicitly synthetic test-fixture corpus contexts; no official candidate or live corpus is approved/published.
- Candidate release metadata is unsigned; this rehearsal does not deploy/attest the older running images. A future final backup must be taken at the actual promotion boundary.

## 10. Live migration readiness recommendation

**NOT AUTHORIZED / NOT READY FOR AUTOMATIC PROMOTION.** Technical database results support 0012 →0015 on the tested snapshot, but **the complete G0.3 gate remains incomplete because the full application suite failed**. Live migration requires that failure resolved or explicitly risk-reviewed, G0.4 authority separation, aligned reviewed images, protected file/secret recovery arrangements, an approved maintenance/cutover/restore plan and a fresh backup. No live SQL migration or service restart was performed.

## 11. G0.4 recommendation

First resolve/reproduce the evidence snapshot/clock failure and obtain a green application acceptance run; do not interpret passing database tests as release approval. The next separately authorized G0.4 task is to design and verify a migration-owner/runtime-role permission matrix on an isolated clone, including denied DDL, trigger/ownership bypass and cross-role writes. Prepare credential references/rotation and ownership/ACL-aware restore procedures before applying any role/grant change to the live demo. **G0.4 has not begun.**
