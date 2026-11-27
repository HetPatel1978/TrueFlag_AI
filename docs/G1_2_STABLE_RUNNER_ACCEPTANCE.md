# G1.2 - stable runner acceptance

**Date:** November 15, 2026, America/New_York (client date).

**Decision: BLOCKED at runner discovery.** No independently clock-stable, authorized and usable Linux acceptance target was established. Stopped before environment preparation, clock acceptance, cohort processing or test execution, as requested. This does not claim that no suitable machine exists anywhere.

## 1. Runner identity and availability

| Candidate | Current inspection | Acceptance suitability |
|---|---|---|
| Local Docker | Two local `npipe` contexts; Docker Desktop, Linux kernel `6.6.87.2-microsoft-standard-WSL2` | WSL2-backed; not an independently verified Linux clock |
| Ubuntu / docker-desktop | Both currently running WSL version 2 | Neither establishes an independent stable runner; no new clock-stability claim |
| GitHub Actions | Local and remote Foundation checks configure `ubuntu-latest` | Configured CI target exists; no suitable current-candidate execution session or clock evidence established |
| SSH | One configured host, unidentified as a project runner; no connection attempted | Authorization, OS, clock health and cost status unverified; target confirmation requested |
| Dedicated VM / other remote | No project runner endpoint found in inspected CI/Compose/development configuration; none supplied | Not provisioned, assumed available or contacted |

- Repository tools and `gh` availability were checked; Docker and SSH clients exist, GitHub CLI was not found on PATH. The connected GitHub app successfully performed read-only repository/branch/workflow-file lookups.
- SSH discovery inspected configuration structure only. Hostname, username, port values, key paths and private keys were not printed. No unidentified host was treated as implicitly approved infrastructure.
- No cloud account/resource inventory was scanned, resource provisioned, remote job started or charge incurred by this task.

## 2. Why configured CI cannot currently complete this task

- Branch/base: `codex/project-initialization`, local HEAD `a3b2ba49cd92c4aa0401842fa4999897fdc28713`; the current G0/G1 candidate includes uncommitted/untracked work.
- The fetched [remote CI workflow](https://github.com/HetPatel1978/TrueFlag_AI/blob/codex/project-initialization/.github/workflows/ci.yml), blob `329a5c4580819914170db34d0e4145434a3ccd0e`, triggers only on **push / pull_request**, with no manual-dispatch interface.
- Remote CI is older than the local candidate: it does not include the local explicit PostgreSQL integration opt-in or pinned ML verification steps. The remote G1 implementation report lookup returned **404**. Running the old workflow would not prove acceptance of these local changes.
- Approved fitted model, dictionary, frozen references and retained cohort/backup are local, Git-ignored assets. The existing workflow has no acceptance-specific private staging/restore procedure, continuous clock observer or retained-cohort execution path.
- Connected repository metadata reports pull access, without push/admin access. This describes this connector, not the owner's account generally; Actions execution permissions and billing approval were not established.
- The available commit-workflow lookup returned zero PR-triggered runs for local HEAD. That lookup is first-page/PR-filtered, **not** an inventory of all Actions runs, available capacity or registered self-hosted runners. No broader absence is inferred.
- No workflow rerun was triggered: it would use remote source, not this uncommitted candidate. No commit, push, public asset upload, workflow modification or paid runner provisioning was used to bypass the task constraints.

## 3. Clock synchronization evidence

| Evidence | Status |
|---|---|
| New independent runner identity / UTC / synchronization / clocksource | Not available; not verified |
| New host/PostgreSQL/API/worker clock comparison on that runner | Not performed; runner prerequisite failed |
| Prior G1.1 local observations | Two approximately 60-second windows recorded 10 guest and 9 PostgreSQL backsteps; Ubuntu also regressed despite its synchronization flag |
| Current discovery | Confirms Docker remains WSL2-backed; does **not** rerun or recertify historical clock measurements |

- A configured Ubuntu CI label, green historical job or container boundary is insufficient clock evidence. A real approved target must be inspected and monitored before and during acceptance.
- Snapshot floor/epoch controls, strict 900-second expiry, authorization and numeric verification remain unchanged. No system time, synchronization service, clocksource, host setting or readiness behavior was changed.

## 4. Environment isolation and cohort results

- No new environment/database was created or restored. No database connection or live demo API call was made during discovery.
- Existing isolated rehearsal container identity/image/network/volume guards were inspected read-only. It remains **stopped**, with the source/live container excluded.
- Last verified G1.1 cohort baseline, **not a new database recount**:

| Cases | Completed assessments | Pending assessments | Stored packets |
|---:|---:|---:|---:|
| 16 | 6 | 10 | 4 |

- No jobs were recovered/resumed, statuses changed, predictions manufactured, packets created or case actions taken. Current packet acceptance is not inferred from stored packet counts.
- Original recovery backup and protected isolated-cohort backup SHA-256 were rechecked successfully. Cohort backup remains `4c434d36ebd5a8a316be2e4b40d6ea893b4d58883b86725ddd85dc8da4034c79`, 959,871 bytes; not transferred or restored. Prior archive listing is not a successful restore rehearsal.
- Discovery ledger: `runtime/g1-2/92265fe8f5744e7bb01e41ae8a863a04/`; protected file-hash baseline and backup/container checks. No credentials or private feature records are included in this report.

## 5. Tests, security verification and scientific parity

| Requested G1.2 check | Current result |
|---|---|
| Full Linux/PostgreSQL / G1 focused / investigation and snapshot acceptance | **NOT RUN**: no suitable runner established |
| Cohort financial facts, RF/Policy/SHAP, expected abstentions, retries/idempotency | **NOT RUN**: no cohort processing |
| Case/assignment isolation, forged references/totals, revocation, expiry, worker recovery/concurrency | **NOT RUN**: no new security acceptance result claimed |
| Pinned ML and frozen 4,000 RF / 12,000 policy / 4,000 SHAP comparisons | **NOT RERUN**: previous G1.1 zero-mismatch evidence remains historical |
| Frontend/Chromium, application lint/format/build | **NOT RUN** after the discovery stop; no implementation changes |
| Documentation/publication and preservation checks | Recorded in final handover below; not application acceptance |

No zero pass/fail counts are substituted for checks that did not execute. Previous successful diagnostics or scientific parity cannot clear the runner/clock gate.

Read-only discovery commands included:

```powershell
git branch --show-current
git rev-parse --short HEAD
git remote -v
rg -n -i 'runs-on|workflow_dispatch|self-hosted|runner|ssh' .github docker-compose.yml README.md docs
docker context ls --format json
docker info --format '{{json .}}'
wsl --list --verbose
```

Docker output was reduced in-process to endpoint schemes, OS/kernel and stopped-state checks; connection details and raw configuration were not logged. GitHub reads used the connected app; no workflow execution or repository mutation was requested.

## 6. Remaining blockers and required next input

1. **Approved target:** identify an existing native Linux runner/VM outside this WSL2 clock environment, provide its authorized SSH alias or existing CI execution path, and confirm execution will not incur unauthorized charges. One unidentified SSH entry is insufficient authorization.
2. **Candidate and assets:** establish a secure execution path for the exact local candidate plus SHA-approved private ML assets and a copy of the protected cohort backup. The current public, push-triggered workflow is not that path. Do not publish private assets to Git or silently override the no-commit/no-push constraint.
3. **Clock and isolation gate:** verify trusted synchronization, UTC/clocksource, independently repeated idle/workload observations, PostgreSQL/API/worker agreement and continuing regression detection; establish a disposable target distinct from the live demonstration database before restoring or processing anything.
4. **Then acceptance:** resume through existing services, preserve original history, require catalog-appropriate packets or abstention, and run the full requested backend/security/scientific/frontend verification. Do not force every scenario to a successful packet or change frozen outputs.

## 7. Acceptance decision and G2 readiness

- **G1.2 discovery completed; G1 acceptance remains BLOCKED.** No stable-runner or connected-cohort acceptance is claimed.
- **G2/G3/G4/G5 not started.** Supply/confirm the target before further execution; no cloud provisioning, host clock maintenance or deployment was inferred from this request.
- No automatic dismissal, SAR action, external LLM call, regulatory publication, database-role/credential change, live migration, commit or push.

## 8. Final preservation and handover

- All **345 pre-existing file fingerprints unchanged**, including `.env`, frozen scientific assets, generated release metadata and existing uncommitted source/documentation. Only this new report and ignored discovery bookkeeping were written.
- Existing source and cohort backup hashes verified; no restore, transfer, database start or live demo connection.
- Discovery directory: **5 owner-protected entries**, protected root ACL and zero unexpected allowed principals.
- Publication check: **PASS, 314 source candidates**; private/secret ignore boundaries intact. Report UTF-8/placeholder checks passed. These checks are documentation/preservation validation, not application tests.
- Branch remains `codex/project-initialization`, HEAD `a3b2ba4`. No commit, push, deployment, runner provisioning or CI job execution.
- Target confirmation was requested for the unidentified SSH entry; no authorization or alias was supplied before this discovery stop. This is a pending prerequisite, not an inferred refusal or permission to connect.
