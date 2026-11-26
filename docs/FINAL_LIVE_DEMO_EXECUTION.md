# Final live demonstration: executable operator runbook

November 22, 2026. **Prepared, not deployed. No authorized independent Linux host has been supplied. Live Claude requests in this task: 0.** Do not run acceptance on the existing WSL/Docker clock. These commands launch only a new isolated candidate on a separately authorized native Ubuntu host.

## 1. Export the current source on Windows

From the project directory, after reviewing the current work:

```powershell
.venv\Scripts\python.exe scripts/prepare_native_demo.py --export-only --output runtime/native-source-transfer
tar -czf runtime/trueflag-native-source.tgz -C runtime/native-source-transfer .
Get-FileHash -Algorithm SHA256 runtime/trueflag-native-source.tgz
```

The export copies current backend/frontend/scripts/contracts, including uncommitted source. It excludes `.env*`, runtime history, private assets/model files, database files, key files, caches and old build identities. `source-manifest.json` binds exported files. No account/provider credentials are transferred. Existing output paths are rejected. Do not replace this export with a clone of the older remote branch.

Only after an actual host/SSH identity and transfer permission are provided, securely transfer this archive. Verify its recorded SHA-256 on that host before extraction into a new owner-restricted source directory. No host alias is implied by this runbook. The approved private baseline must be separately available on that authorized host; do not copy customer data or the original demo database. The baseline needs the existing `model/`, `contracts/` and `reference/research/src/trueflag/` trees. Its fitted model and hashes are not changed.

## 2. Prepare on native Ubuntu

Prerequisites: Python 3, a working Docker Engine + Compose plugin, an authorized nonroot operator, sufficient local disk/memory for the existing images, and synchronized host time. Follow [Docker's Ubuntu installation instructions](https://docs.docker.com/engine/install/ubuntu/) if needed. Do not install software or change host time automatically. Inspect `timedatectl status` and the host's actual synchronization source/offset; an NTP status bit alone does not establish clock stability.

Run from the exported source root, using the real authorized baseline location:

```bash
set -eu
umask 077
uname -r
timedatectl status
# STOP on Microsoft/WSL kernels or unhealthy synchronization.
TF_DEMO="$PWD/runtime/native-launch"
TF_BASELINE=/secure/trueflag-baseline
python3 scripts/prepare_native_demo.py --output "$TF_DEMO" --baseline "$TF_BASELINE"
dc() { docker compose --env-file /dev/null -f "$TF_DEMO/compose.json" "$@"; }
dc --profile acceptance --profile operator --profile assessment --profile gated-ai config --quiet
dc --profile acceptance --profile operator --profile assessment --profile gated-ai build
```

`TF_BASELINE` is a path to operator-approved existing assets, not a downloaded substitute. Omit `--baseline` only for a package that intentionally cannot demonstrate RF scoring/evidence admission; the complete demonstration requires it. The generator refuses Windows/WSL, root execution and existing destinations. It does not start Docker, alter the source application or touch any database.

The private launch directory contains fresh PostgreSQL/JWT/worker credentials in mode-0600 files, a source copy with candidate 0020–0023 migrations, matching measured build metadata and `compose.json`. No `.env` is read or written. Git/image identity remains explicitly unknown where not established; source/build hashes describe this candidate, not a certified release.

## 3. Native PostgreSQL/clock acceptance first

```bash
dc --profile acceptance up -d --wait --wait-timeout 90 testdb
dc exec -T testdb psql -U tf_acceptance -d tf_acceptance_rag -Atc \
  'SELECT system_identifier FROM pg_control_system()' \
  > "$TF_DEMO/control/acceptance/cluster-id"
timedatectl status > "$TF_DEMO/control/acceptance/host-time-before.txt"
timedatectl show -p NTPSynchronized --value > "$TF_DEMO/control/acceptance/ntp-status"
test "$(cat "$TF_DEMO/control/acceptance/ntp-status")" = yes
dc --profile acceptance run --rm --no-deps -T acceptance
timedatectl status > "$TF_DEMO/control/acceptance/host-time-after.txt"
python3 -m json.tool "$TF_DEMO/control/acceptance/results/evidence.json"
```

Required: no backsteps, no database time outside the host request bracket, no sampler errors, zero required skips/failures/errors, expected revision 0023 and matching candidate build identity. Inspect the retained realtime/raw-monotonic clock-rate observations and synchronization evidence. The helper performs two 60-second preflight windows and continuous sampling through the tests. A failure stops the sequence; retain evidence rather than resetting clocks/floors/epochs or editing receipts. The application wrapper refuses a failed, absent or different-build acceptance receipt.

This target is a **separate disposable test cluster**, not the application database. Native acceptance exercises authorized synthetic regulatory fixtures and deterministic provider responses; it does not approve official sources or validate Claude. The helper includes deferred binding/idempotency/revocation/rollback/recovery tests. Real results are recorded only when the authorized host executes them.

## 4. Start the isolated application and existing workers

Continue only after section 3 passes and its evidence has been reviewed:

```bash
dc up -d --wait --wait-timeout 90 db
TF_DATABASE=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["database"])' \
  "$TF_DEMO/control/control.json")
dc exec -T db psql -U tf_native -d "$TF_DATABASE" -Atc \
  'SELECT system_identifier FROM pg_control_system()' > "$TF_DEMO/control/cluster-id"
dc --profile operator run --rm --no-deps -T operator operator migrate

# Existing interactive account bootstrap: enter passwords privately; nothing is preseeded.
dc --profile operator run --rm --no-deps operator operator bootstrap nativeadmin admin
dc --profile operator run --rm --no-deps operator operator bootstrap nativeanalyst analyst
dc --profile operator run --rm --no-deps operator operator bootstrap nativesupervisor supervisor
dc --profile operator run --rm --no-deps -T operator operator register-workers nativeadmin

# Original SHA/dependency verification; no alternate model, training or fabricated scores.
dc --profile assessment run --rm --no-deps --entrypoint python assessment-worker -B -c \
  'from app.core.release import verify_worker_artifacts; print(verify_worker_artifacts())'
dc --profile operator run --rm --no-deps -T operator operator fixtures nativeadmin \
  > "$TF_DEMO/control/synthetic-cases.jsonl"

dc --profile assessment up -d --wait --wait-timeout 90 \
  backend frontend import-worker evidence-worker assessment-worker
dc --profile operator run --rm --no-deps -T operator operator status
curl --fail --silent --show-error http://127.0.0.1:8010/ready
curl --fail --silent --show-error http://127.0.0.1:8088/health
dc ps
```

Only the generated application database is migrated. Its name and newly captured cluster identity must match before any operation. No command restores or connects to the original Windows demo. Database roles are newly initialized inside these two new clusters; existing roles are untouched. This remains an isolated development setup, not production SQL least privilege.

The fixture command uses existing `scenario_bundle` → `EvidenceService` admission/case creation → authorized snapshot → assessment enqueue. It prepares three deterministic **ordinary, velocity, incomplete-history** scenarios. It does not assign SAR labels, invent scores, insert completed jobs or grant regulatory approval. Repeated fixture requests use original source identities and assessment idempotency; revoked evidence still denies access. Worker registration reuses only exact active matching identities and never rotates/reactivates them.

`synthetic-cases.jsonl` includes scenario/case/source/job IDs and browser paths. These connected cases are distinct from CSV rows without transaction evidence. Use their direct authorized links; do not claim an uploaded predictor CSV created transaction histories. The dashboard may remain scoped to the active upload session.

All networks are internal; PostgreSQL has no published port. Frontend/API bind only to host loopback. Secrets are private read-only file mounts, not build arguments or Compose environment interpolation. See [Docker secret guidance](https://docs.docker.com/compose/how-tos/use-secrets/) and [bridge networking](https://docs.docker.com/engine/network/drivers/bridge/). Containers drop capabilities and workers have resource bounds. Docker administrator access still grants access to local secrets.

For remote recording, use an explicitly authorized SSH alias on your workstation:

```bash
ssh -N -L 8088:127.0.0.1:8088 -L 8010:127.0.0.1:8010 YOUR_AUTHORIZED_SSH_ALIAS
```

Browser: `http://127.0.0.1:8088`. API: `http://127.0.0.1:8010`. These are **prepared host bindings**, not currently verified running URLs. Do not publish them to the internet as HTTP or expose the Docker socket.

## 5. Exact regulatory eligibility gate

**APPROVAL RECORD MISSING.** Current review directory `assets/local/regulatory/reviews/` is absent; `contracts/regulatory_reviewer_registry_v1.json` is unapproved with zero members. The previous identity-verified isolated database inventory found zero official-version approvals. No new host/database approval is inferred from source text or a verbal instruction.

| Required record / action | Exact contract |
|---|---|
| Source-version review dossier | Qualified independent human identity/qualifications/conflicts, actual review time, exact original/extracted/section/version-manifest hashes, historical scope, applicability, rights, full provisions/exceptions, amendment/date evidence and explicit publication/AI-grounding permission |
| Historical source identity | eCFR 31 CFR 1020.210 and 1020.320, as-of 2026-11-02 / cutoff 2026-11-04; original XML SHA `2588950c5c16efb45a2a78369e08bda2174bf9a8be5afd634235a406f51924bb`. Exact sections/proposals are in `contracts/regulatory_source_proposals.json` |
| Provenance gap | Original precise HTTP fetch timestamps are absent. Reviewer must accept a separately evidenced curation event with its true meaning, or require a new version. Do not supply test timestamps as history |
| Genuine version approval | Existing `ReferenceService.approve_version`: approved version manifest; `review_kind=human`; mandated attestation; actual dossier `review_reference_sha256`; approver account must differ from `admitted_by` |
| Release/context/access | Curator obtains `proposed_release` digest; separate explicit matching release approval → `publish`; then `grant` each authorized reader. Configure the actual returned context ID. Preserve real publication/audit events |
| Retrieval benchmark | Qualified private reviewer registry, independently labeled/adjudicated current 31-case v2 packet, reviewed acceptance criteria and reproducible evaluation. The older 19-case packet and engineering hints are not independent truth |

FinCEN HTML remains excluded while historical validity is unverified; the research PDF is not supported by the production parser. Detailed source questions: [source checklist](PHASE3_4_SOURCE_APPROVAL_CHECKLIST.md) and [G5 governance](G5_1_SOURCE_REVIEW_AND_GOVERNANCE.md).

The existing research route is **metadata only**, with `eligible_for_ai_grounding=false`. Outside test environments, `RegulatoryInvestigationService._origin` requires `official_curated` and `review_kind=human`. There is **no permitted unapproved-text-to-Claude research exception**. Keep it blocked; changing `APP_ENV` to `test`, using test approvals or relabeling research is not a remedy.

Prepare the actual independent review intake using the existing CLI (creates blanks, not approval):

```bash
# Run where the existing backend dependencies are installed, from the project root.
python scripts/regulatory_review_workflow.py prepare \
  --output runtime/regulatory-human-review/review-packet.json
```

Then the designated reviewers submit their own records through the documented `record/status/evaluate` workflow. No command in this launch package manufactures those records or publishes a source. A curator must execute the existing approval/release/grant services only after validating genuine reviewer evidence.

## 6. Controlled Claude request: stop until separately authorized

The package contains **no provider key**, provider egress, simulation activation or live activation. The draft-worker service is under the `gated-ai` profile and is intentionally not started by section 4. It is not a functioning live-AI demonstration yet.

After stable native acceptance and eligible source context exist, prepare the new grounded request through the existing coordinator/G5/Claude adapter. Bind minimized synthetic packet, evidence/source/access revisions, selected passages and version/citation hashes, exact schema, intended `claude-sonnet-5-5` model, plain `https://api.anthropic.com/v1/messages` endpoint, byte count/SHA-256, bounded output/deadline, immutable ledger and one-attempt/no-retry scope. Show the **full exact payload** for owner approval. Do not reuse the pending evidence-only v2 request or consumed historical approvals.

A reviewed runtime activation/egress configuration is still required after the applicable provider evaluation and operating approval. The preparation wrapper rejects activation settings; do not edit receipts, disable its guards or add a public network/key to make section 4 look live. Existing provider/ledger services remain the sole paid transport path. Historical attempt/usage ledgers must be preserved when moving from an existing probe environment; a fresh empty launch database does not reset previous authority or spending history.

No grounded request or live dispatch was prepared/executed in this task because those prerequisites are absent.

## 7. Recording navigation and recovery acceptance

Only after genuine grounded response verification and operating authorization:

1. Sign in as `nativeadmin` using the privately entered password; open the **velocity** case URL from `synthetic-cases.jsonl`. Show completed **Alert Risk Assessment**, **Review Recommendation** and **Key Risk Drivers** from the real worker.
2. Assign `nativeanalyst` through the existing authorized assignment control. Sign in as that analyst; open **Review Evidence**. Show authorized customer/account/transaction records, currencies, source references and observed coverage.
3. Open **AI Investigation → Generate AI Investigation**. Confirm actual Claude identity; capture genuine backend states and result. Inspect **Financial Observations**, evidence-linked findings and **Regulatory Guidance** citations against approved historical passages. No research-only or simulated result may be represented as approved/live.
4. Refresh the browser; reopen stored findings/history. Show **Human Decision**, note/rationale/escalation and an appropriately separate supervisor review. Show **Activity History**. No automatic closure or SAR action occurs.

Before the paid attempt, exercise worker interruption only on the non-provider evidence/assessment flow, preserve leases and wait for supported recovery; do not replay an ambiguous paid request. Example targeted evidence worker restart:

```bash
dc kill -s SIGKILL evidence-worker
dc up -d evidence-worker
dc logs --tail 30 evidence-worker
```

Record actual job IDs/status transitions, one published result, refresh persistence and authorization denials. Native tests alone do not prove the browser journey. No screenshots or success claims exist until this sequence runs against the actual services.

## 8. Restart, stop and actual results

```bash
# In a fresh shell, from the same source root:
TF_DEMO="$PWD/runtime/native-launch"
dc() { docker compose --env-file /dev/null -f "$TF_DEMO/compose.json" "$@"; }
dc up -d --wait --wait-timeout 90 db
dc --profile assessment up -d --wait --wait-timeout 90 backend frontend import-worker evidence-worker assessment-worker
dc --profile '*' stop
```

Stop retains both volumes, private configuration, source identities, evidence and history. Do not use `down -v`, delete control files or recreate the project as a substitute for recovery.

| Actual local verification | Result |
|---|---|
| Offline setup + existing deferred/Claude contract/provider/approval tests | 110 passed, 0 failed, 10 native PostgreSQL tests skipped |
| Generated Compose schema, all profiles | `docker compose ... config --quiet` passed; no daemon operation or deployment |
| Official review inventory | Directory absent, zero registry members, unapproved; no approval imported |
| Native build/migrations/clock/worker/browser acceptance | Not executed: no authorized independent host |
| Claude/official-grounded findings | Not executed: native/source/exact-request approval gates absent |

The new launch scripts are operational glue, not new application features. Frozen RF/policy/SHAP, original database, `.env` and saved v2 approval remain unchanged. No commit, push, deployment or paid request occurred.
