# Native Windows runtime and acceptance

November 22, 2026. The isolated Windows application runs without WSL, Linux containers or a cloud VM. **Real Claude + official Regulatory RAG is not approved or independently verified. Paid requests in this task: 0.**

## 1. Current application

| Component | Native implementation / status |
|---|---|
| React | Existing Vite/React application; `http://127.0.0.1:54464` |
| FastAPI | Existing services and protected APIs; `http://127.0.0.1:54463`; readiness verified |
| PostgreSQL | EDB PostgreSQL 17.12, Windows x64/MSVC; new loopback-only cluster, SCRAM authentication, UTC session timezone; no Windows service installed |
| Assessment worker | Actual fitted RF → frozen policy → exact TreeSHAP → atomic immutable assessment/audit persistence |
| Import worker | Existing durable CSV service, native file paths and existing Windows staging ACL checks |
| Evidence worker | Existing coordinator/analytics/verifier; real source-backed packets generated through HTTP 202 jobs |
| Provider subprocess | Windows containment implemented; existing Claude adapter/schema/authorization/verifier reused; paid activation remains disabled |
| Regulatory retrieval | Native PostgreSQL service tested with controlled synthetic corpus fixtures. Actual application has no approved official corpus; unavailable/empty guidance verified |

These URLs identify the currently running native instance, not the old `5173/8010` application. Later newly initialized instances choose their own unused ports; use `Status` rather than guessing.

## 2. Compatibility audit and changes

| Actual paths | Finding and correction |
|---|---|
| `backend/app/workers/assessment_worker.py` | Windows cannot select anonymous pipes as Linux does. Added bounded threaded pipe IPC with the same heartbeat/deadline/fenced-publication behavior |
| `backend/app/workers/process_control.py` | New Windows Job Object adapter: create suspended, assign limits before first instruction, resume primary thread, verify exact job membership, CPU/committed-memory/process bounds, kill-on-close and bounded stdout. No credentials sent before containment succeeds |
| `backend/app/workers/assessment_child.py` | POSIX `prctl`/`resource` remain on Linux. Windows validates its owning Job Object before reading credentials. Windows venv adds a launcher parent; job membership/lifetime replaces the immediate-parent-PID assumption |
| `backend/app/services/live_provider_runner.py`, `investigation_provider_runner.py` | Added native Windows transport to the same subprocess path. Existing endpoint/model/approval/ledger checks remain before invocation; response parsing and independent verification retained |
| `backend/app/workers/live_provider_process.py`, `investigation_provider_process.py` | Conditional POSIX limits; Windows requires verified containment. No `.env`, arbitrary tools or uploaded model loading in provider children |
| `backend/app/workers/investigation_worker.py`, `investigation_draft_worker.py`, `csv_import_worker.py` | Linux/Windows platform admission; original service execution, tokens, transactions, leases and retries retained |
| `scripts/windows_runtime.py` | Owned native cluster/source snapshot; existing services/fixtures; exact loopback origins; existing local browser-cookie mode; owner/SYSTEM ACLs; process creation identities prevent stale PID adoption |
| `scripts/start_trueflag_windows.ps1` | Start/status/stop/restart, hidden supervisor, bounded readiness checks, idempotent healthy start; graceful worker cancellation and optional database shutdown |
| Existing CSV code | Already contains native Windows private-directory/ACL handling; reused |
| Existing RF/scoring/SHAP modules | Scientific code and artifacts unchanged. Earlier historical DLL failure did not recur in the fresh pinned Windows environment |

Additional Linux-only assumptions **outside this launch path** remain in historical Docker/recovery harnesses (`rehearse_database_recovery.py`, `setup_connected_scenarios.py`, `run_assessment_verification.py`, `verify_assessment_persistence.py`), Linux pipe-handshake tests, and `resource`/cgroup benchmark scripts (`benchmark_operations.py`, `benchmark_batch.py`). They are not called by the native launcher. Windows verification uses the explicit native helpers below; this is not a claim that every historical Linux diagnostic script was ported.

Windows Job Objects are process/resource containment, not a complete OS sandbox. POSIX `RLIMIT_NOFILE`/file-size controls have no identical Windows implementation here; trusted fixed children instead have bounded process/memory/CPU lifetimes and pipe output. No arbitrary code/tool interface was added. Do not claim production sandbox equivalence or security certification.

## 3. Installation requirements

| Requirement | Verified here |
|---|---|
| Windows | Native Windows 11 x64; ordinary owner account, no WSL dependency |
| Python | 3.11.14; separate `.venv-windows`, original backend + ML requirement files |
| Node | 24.14.0 / npm 11.9.0; existing frontend lockfile/dependencies; project requires Node ≥22.12 |
| PostgreSQL | Portable EDB 17.12-1 Windows x64 runtime; `postgres.exe` Authenticode status **Valid**, EnterpriseDB Corporation |
| Private assets | Existing approved `assets/local/baseline` and original `assets/local/explanation_reference`; no replacement/retraining |
| Browser tests | Existing Playwright/Chromium installation |

First-time dependency setup from the project root:

```powershell
.venv\Scripts\python.exe -m venv .venv-windows
.venv-windows\Scripts\python.exe -m pip install -r backend/requirements.lock -r backend/ml-requirements.txt
Push-Location frontend
npm.cmd ci
Pop-Location
```

The already installed portable binaries are at `runtime/windows-postgresql-17.12-1/pgsql/bin`. PostgreSQL's [Windows download page](https://www.postgresql.org/download/windows/) identifies EDB as its installer/binary distributor. The [EDB archive page](https://www.enterprisedb.com/download-postgresql-binaries) provides portable binaries. Acquisition in this task:

```text
https://get.enterprisedb.com/postgresql/postgresql-17.12-1-windows-x64-binaries.zip
386263884 bytes
SHA-256 a2cd8a774389347b70be7748ac4a37ef43cb6ee539c5fc3e85ae264b15e4a04c
```

That SHA is an observed local acquisition identity, not an independently published vendor checksum. The executable's publisher signature was checked separately. Only archive `pgsql/bin`, `pgsql/lib` and `pgsql/share` runtime entries were extracted, with size/path checks. No installer, host service, database role changes outside the new cluster, application-control bypass or machine-clock change occurred. If a future DLL is blocked, stop and diagnose the supported runtime rather than disabling Windows security or changing scientific pins.

## 4. Start, status, restart and stop

For this already initialized instance:

```powershell
.\scripts\start_trueflag_windows.ps1 -Action Start
.\scripts\start_trueflag_windows.ps1 -Action Status
.\scripts\start_trueflag_windows.ps1 -Action Restart
.\scripts\start_trueflag_windows.ps1 -Action Stop
```

For a **new** installation only, initialize once before Start:

```powershell
.\scripts\start_trueflag_windows.ps1 -Action Initialize -PostgresBin .\runtime\windows-postgresql-17.12-1\pgsql\bin
.venv-windows\Scripts\python.exe scripts/windows_runtime.py fixtures
.\scripts\start_trueflag_windows.ps1 -Action Start
```

Initialize refuses to overwrite the current runtime. It copies current public source into a private candidate snapshot, stages existing candidate migrations through **0023**, measures matching frontend/backend/worker build metadata, initializes new application/test databases and creates explicit local demo accounts. Original application source schema head and original demo databases are untouched. Private model/reference and dependency directories are linked through junctions; the application reads original bytes and verifies original hashes. No original asset permissions or scientific content are changed.

Native roles are `windowsadmin`, `windowsanalyst`, `windowssupervisor`. Each has a random generated password. `Status` supplies the owner-restricted `login.json` path; open it **locally**, never print/share it or paste it into chat. The existing `.env` remains unchanged and is not loaded by this runtime. `ANTHROPIC_API_KEY` is present in the original configuration, but is deliberately absent from this launch scope until approved activation. The frontend process receives no backend JWT/database credentials or provider key. Browser credentials stay in the existing HttpOnly/SameSite session workflow, with a 60-minute token; no immortal login was introduced.

`Stop`/`Restart` affect application processes and preserve PostgreSQL, so independent acceptance sessions are not interrupted. To explicitly stop the new cluster after all application/test clients close:

```powershell
.\scripts\start_trueflag_windows.ps1 -Action Stop -StopDatabase
```

This refuses shutdown while other database clients remain. Do not stop the database during acceptance. Runtime data, SQL history, credentials, prior source snapshots and old initialization diagnostics remain preserved. A stale supervisor record is removed only after kernel process-creation identity proves it stale; unrelated/reused PIDs are never terminated. Model children are assigned suspended to prevent venv-launcher descendant escape.

## 5. Native clock evidence

- Existing Windows Time configuration was **read**, not changed: synchronized source reported, stratum 5; last successful sync and measured uncertainty retained as observations, not UTC certification.
- First 300-sample monitor used Python 3.11's coarser `GetSystemTimeAsFileTime`: zero backsteps/epoch changes, but 293 strict sub-millisecond host-bracket violations. Measured DB-minus-host midpoint was approximately 0.087–1.293 ms. That was a monitoring precision mismatch, not evidence authorizing weakened expiry.
- Diagnostic comparison against Windows' documented precise UTC API produced zero violations in 100 observations. Two subsequent separate 300-sample runs passed with **zero host/PG backsteps, bracket violations and epoch changes**, including observations after recovery.
- The observation helper now uses `GetSystemTimePreciseAsFileTime`; security services still use the original database clock/floor/epoch rules. No timestamps, floors, epochs or 900-second deadlines were edited. See [Python time semantics](https://docs.python.org/3/library/time.html#time.time) and [Microsoft precise UTC API](https://learn.microsoft.com/en-us/windows/win32/api/sysinfoapi/nf-sysinfoapi-getsystemtimepreciseasfiletime).
- Controlled native PostgreSQL clock/replay tests passed, including a fresh-interpreter cross-process test. Source/numeric/reference authorization remains independent of clock validity. Bounded local observations do not establish permanent clock stability or external UTC accuracy.

## 6. Actual verification and corrections

| Check | Actual result |
|---|---|
| Windows containment + existing Claude HTTP/schema tests | **40 passed**; no real provider transport |
| Focused native PostgreSQL/security/real-ML/durable-handoff suite | **202 passed, 1 Linux-only cross-process skip**; that skipped path subsequently ran natively in the clock supplement |
| Native clock-policy supplement | **12 passed, 0 skipped**, including fresh-process floor/epoch/replay checks |
| Pinned Windows ML suite with original reference directory | **178 passed, 0 skipped**; 88 subtests passed |
| Frozen scores | **4,000 matched; max absolute error 0; 0 mismatches/failures** |
| Frozen policies | **12,000 routes; 0 route/trace mismatches; retained/dismissed totals unchanged** |
| Frozen explanations | **4,000 verified; 0 mismatches/unavailable**; encoded/grouped/base/score differences 0; maximum reconstruction residual `3.1086244689504383e-15` |
| Actual connected cases | Three original synthetic profiles admitted through existing services; three real worker assessments and verified explanations persisted |
| Actual in-flight recovery | Supervisor terminated while a fourth/new synthetic RF job was running; Job Objects killed owned children; supported startup recovered the expired lease, succeeded on **attempt 2**, persisted **one** assessment; idempotent replay reused it; case stayed open; PostgreSQL uptime unchanged |
| Actual Chromium | Login, assignment, assessment/27 grouped contributions, source packet HTTP 202/verification, unavailable unapproved guidance, case/session refresh, human note/history refresh and logout denial passed; desktop/tablet screenshots retained privately |
| React | **160 passed**, 17 files |
| Frontend | Production build and ESLint passed |
| Final full native backend suite | **1,439 passed / 0 failed / 0 errors / 124 skipped**, 1 warning, **1060.36 s (17m 40s)** |
| Official-candidate RAG supplement with staged original text | **21 passed / 0 failed / 0 errors / 0 skipped**; disposable schemas, no official approval/publication |
| Actual native provider child supplement | Offline adapter abstention and Claude disabled-activation rejection passed; application simulation/live provider remained off |
| Real Claude + official grounded result | **Not executed / not verified** |

All test data is synthetic. PostgreSQL tests use unique disposable schemas in a separate native test database. Model/policy/SHAP behavior, original artifacts and reference outputs were not adjusted to pass.

Confirmed portability/harness corrections:

1. `pg_ctl` and background PowerShell starts cannot use captured pipes that detached descendants inherit: the parent can wait indefinitely for EOF after the command exits. Use private log files. Initial failed initialization remains preserved/stopped; the corrected initialization and migration succeeded.
2. A Windows venv has an extra launcher process. Job active-process bounds allow the launcher + interpreter, and creation is suspended before assignment. `QueryInformationJobObject(NULL)` inspected an outer job here; children now query and validate their exact parent-created named job. Job-close may return exit code zero; tests verify actual process termination rather than treating exit code as proof.
3. Exact native frontend origins and existing `APP_ENV=local` HTTP-cookie semantics were needed. No foreign origin, insecure production cookie exception or authorization bypass was added.
4. Initial candidate tests assumed exact 0020/0022 heads and omitted the binding table from their inventory. Tests now assert the actual candidate revision/schema without relaxing service compatibility. A pre-existing `g1_demo_priority` profile lacked its independent expected transaction-count entry; added the existing 12-observation expectation.
5. New-cluster UTC timezone removes insert-versus-reread serialization offset differences while preserving absolute timestamptz values. It was reloaded only in this isolated cluster.
6. A legacy exact-probe preparation test requires explicit legacy isolation settings; absence is now an explained opt-in skip, not a KeyError or a fabricated replacement cluster.
7. Browser human-note submission succeeded initially, but the test queried hidden history during React reload. It now waits for persisted content, expands the existing history and verifies it after refresh. Driver-specific logout convenience access was replaced with an actual browser fetch.

The first broad pre-correction run was **1336 passed / 12 failed / 161 skipped / 55 setup errors**. It used the earlier source/configuration and was also interrupted by the then-coupled PostgreSQL/application restart. Preserve that report; it is not final acceptance. Later focused checks verify the corrected paths. No passing rerun is substituted for the recorded causes or remaining limitations.

The final complete native suite receipt is `backend-verification-aae177a76aef4ba6a9e697d27450c9ff/` under the private runtime, containing JUnit, sanitized pytest output and `summary.json`. Its 124 skips comprise **53 Linux-specific process/worker checks, 59 separately authorized isolation/rehearsal/evaluation checks, 5 unavailable legacy probe-package checks and 7 unstaged official-source fixture checks**. The separate 21-pass regulatory supplement supplies the original official candidate/research fixtures in another private source copy; results overlap existing tests and must not be added to the full-suite count. Its candidate labels are engineering diagnostics, not independent ground truth. Native RF/SHAP and Job Object/recovery checks are reported separately; do not claim every Linux process assertion was ported.

An intermediate full-run directory (`backend-verification-31bf73a81fb04f65a9587b4cc87dfdf6`) had no final JUnit receipt and no running test process when work resumed. No result or cause is inferred for that incomplete attempt. The final full test command was rerun without restarting PostgreSQL or the application. Current `.env`, original Claude request/approval packages and frozen regulatory contracts passed the seven-file preservation comparison. Final publication-boundary check: **550 source candidates passed**; targeted Ruff lint/format checks passed. The Starlette/httpx deprecation is the full suite's one warning; dependency pins were not changed to suppress it.

Reproducible acceptance commands:

```powershell
.venv-windows\Scripts\python.exe scripts/verify_windows_runtime.py clock
.venv-windows\Scripts\python.exe scripts/verify_windows_runtime.py backend
.venv-windows\Scripts\python.exe scripts/verify_windows_runtime.py ml
.venv-windows\Scripts\python.exe scripts/verify_windows_runtime.py parity
.venv-windows\Scripts\python.exe scripts/verify_windows_recovery.py
node scripts/verify_windows_browser.cjs 64b8876f-5527-404d-b0de-dab49a475b4d
```

The recovery command deliberately interrupts only the identity-verified native supervisor and creates one new synthetic alert; run it only as an explicit acceptance exercise. The browser command targets the actual current velocity case, assigns the existing analyst if needed and creates a marked acceptance note; it is not a read-only smoke test. Fresh installations have different case IDs, printed by `fixtures`.

Private receipts live under the directory in `runtime/windows-native/current.json`: `*-verification-*`, `recovery-*.json`, `browser-*/report.json` and screenshots. Logs/reports never contain a printed API key or plaintext password. Existing TestClient/httpx deprecation remains a dependency warning.

## 7. Regulatory and Claude activation gates

**APPROVAL RECORD MISSING.** Current source-review directory/registry has no accepted qualified approval. The native development mode does not authorize unapproved source passages: the existing research API is metadata-only and `RegulatoryInvestigationService._origin` still requires official curated, human-reviewed source versions outside tests.

Required human actions remain the exact [source approval checklist](PHASE3_4_SOURCE_APPROVAL_CHECKLIST.md) and [G5 source governance](G5_1_SOURCE_REVIEW_AND_GOVERNANCE.md): qualified hash/scope/applicability/date/provenance/rights/exception review, independent version approval with dossier hash and a distinct approver account, explicit release approval/publication, reader grants/context, independently reviewed retrieval benchmark. FinCEN sources with unresolved validity remain excluded. No approval, signature, reviewer identity or benchmark label was fabricated.

After those gates: construct a **new** native case/evidence/regulatory-bound Claude request through the existing adapter. Show full payload, schema, SHA-256, model/endpoint, bounded tokens/deadline, one-attempt/no-retry authority and applicable spending controls for explicit owner review. The unchanged pending evidence-only v2 request is not this payload. Preserve historical approvals/attempt ledgers; a new database is not a reset of prior authorization or spending history.

Native provider execution is implemented/offline-tested, but its live key/configuration and general analyst generation are intentionally not activated. No live Claude compatibility/evaluation result or official grounded browser demonstration is claimed. Original `.env`, demo databases, frozen assets and regulatory approvals remain unchanged. No commit, push or deployment occurred.

## 8. Recording navigation available now

1. Open `http://127.0.0.1:54464`, sign in with the private native login, and open the velocity case: `/#/cases/64b8876f-5527-404d-b0de-dab49a475b4d`.
2. Show **Assess Alert → Review Evidence**: actual score/policy/key drivers and linked synthetic financial records. The analyst assignment used by browser acceptance is `windowsanalyst`.
3. Show **AI Investigation** as honestly unavailable until approval; existing evidence-only summaries and history remain usable. Unapproved regulatory passages remain withheld.
4. Show **Human Decision → Casework history → Activity History** and refresh. Acceptance notes are explicitly marked; no model closed a case.

This records the functioning native foundation, not the still-blocked live Claude + official RAG feature. Default case lists remain upload-session scoped; connected fixture cases use their authorized direct links. Uploading predictors alone does not invent transaction history or arbitrary document extraction.

For the latest genuine reviewer dependency, exact source handoff, Claude approval sequence and short video runbook, see [Windows live investigation gate](WINDOWS_LIVE_INVESTIGATION_GATE.md). The owner confirmed that a qualified reviewer still needs to be appointed. Live requests in this follow-up: **0**.
