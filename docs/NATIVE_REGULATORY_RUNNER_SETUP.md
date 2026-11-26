# Native Linux runner dependency and isolated setup

November 22, 2026. **No runner is currently available. These steps were prepared, not executed.** The owner confirmed that no independent target exists. No VM/cloud resource was provisioned, SSH connection attempted, credential transferred or CI job started.

For the complete portable application package, secure source export, native acceptance, migration, account bootstrap, existing workers, synthetic case links and start/stop commands, use [Final live demo execution](FINAL_LIVE_DEMO_EXECUTION.md). The commands below remain the standalone PostgreSQL acceptance alternative; do not execute both procedures against the same target.

## 1. Discovery and prerequisites

| Candidate | Verified finding |
|---|---|
| Local Docker | Both contexts use local Windows named pipes; Docker Desktop kernel is `6.6.87.2-microsoft-standard-WSL2` |
| Ubuntu / docker-desktop | Both are WSL2; neither is an independent clock domain |
| SSH | One configured host, no identified TrueFlag alias or authorization; not contacted |
| Dedicated VM tools | No QEMU/VirtualBox/Multipass/VMware CLI on PATH; this does not prove no machine exists elsewhere |
| GitHub | Connected app has pull access, not push/admin. Remote workflow blob `329a5c4580819914170db34d0e4145434a3ccd0e` is push/PR-only and older than the uncommitted candidate. No current-candidate execution session or runner clock evidence was established |

**External dependency:** an owner-supplied, authorized native Linux host/VM outside the current WSL kernel, with confirmed cost permission, secure administrator access and synchronized UTC. A hosted label, VM name or NTP status alone is insufficient clock evidence.

Install Docker Engine using the [official Ubuntu instructions](https://docs.docker.com/engine/install/ubuntu/) if absent. Follow the host distribution's [time synchronization guidance](https://ubuntu.com/server/docs/how-to/networking/timedatectl-and-timesyncd/) and its managed NTP policy; do not copy Windows/WSL clock workarounds to the new host. Operator maintenance remains separate from application approval.

Securely transfer the **current reviewed source**, not just the old GitHub branch. Do not upload `.env`, private models, datasets or archives to the public repository. Do not transfer any credential/private archive before the target is identified and authorized. The offline acceptance below needs source plus synthetic fixtures, not a real Claude key or original demonstration database.

## 2. Create a new, isolated test database

Run on that native Linux host, from the reviewed repository root. Commands are Bash. They intentionally fail if the work directory/network already exists, preventing silent reuse. Docker installation and downloads require the operator's normal infrastructure permission.

```bash
set -eu
uname -r
# Stop if the kernel identifies Microsoft/WSL.
TF_ACCEPTANCE_DIR="$PWD/runtime/native-regulatory"
mkdir -p "$PWD/runtime"
mkdir -m 700 "$TF_ACCEPTANCE_DIR"
TF_NATIVE_PROJECT="tfacceptance-$(date -u +%Y%m%d%H%M%S)"
export TF_ACCEPTANCE_DIR TF_NATIVE_PROJECT

# Generate NEW disposable-database credentials; no .env or provider key is read.
python3 - <<'PY'
import os, secrets
from pathlib import Path
from urllib.parse import quote
p = Path(os.environ['TF_ACCEPTANCE_DIR'])
password = secrets.token_urlsafe(32)
for name, value in {
    'postgres-password': password,
    'database-url': 'postgresql+psycopg://tf_acceptance:' + quote(password, safe='') + '@db:5432/tf_acceptance_rag',
}.items():
    with (p / name).open('x') as f:
        f.write(value)
    (p / name).chmod(0o600)
PY

docker network create --internal "$TF_NATIVE_PROJECT"
docker volume create "$TF_NATIVE_PROJECT-data"
docker run -d --name "$TF_NATIVE_PROJECT-db" \
  --label "io.trueflag.acceptance=$TF_NATIVE_PROJECT" \
  --network "$TF_NATIVE_PROJECT" --network-alias db \
  -e POSTGRES_USER=tf_acceptance -e POSTGRES_DB=tf_acceptance_rag \
  -e POSTGRES_PASSWORD_FILE=/run/secrets/postgres-password \
  -v "$TF_ACCEPTANCE_DIR/postgres-password:/run/secrets/postgres-password:ro" \
  -v "$TF_NATIVE_PROJECT-data:/var/lib/postgresql/data" postgres:17-alpine

docker exec "$TF_NATIVE_PROJECT-db" pg_isready -U tf_acceptance -d tf_acceptance_rag
# Continue only when ready; do not redirect this setup at an existing database.
docker exec "$TF_NATIVE_PROJECT-db" psql -U tf_acceptance -d tf_acceptance_rag -Atc \
  'SELECT system_identifier FROM pg_control_system()' > "$TF_ACCEPTANCE_DIR/cluster-id"
docker image inspect postgres:17-alpine --format '{{.Id}}' > "$TF_ACCEPTANCE_DIR/postgres-image-id"
docker build -f backend/Dockerfile.ml-worker -t "$TF_NATIVE_PROJECT-worker" backend
```

PostgreSQL initialization creates only this new disposable cluster/account. It does not alter existing database roles. No database port is published. The [official PostgreSQL image](https://hub.docker.com/_/postgres) supports file-based password input; the user-defined [Docker network](https://docs.docker.com/engine/network/drivers/bridge/) is marked internal. Record the actual image IDs; mutable tags are not a production release pin.

## 3. Clock observation and real PostgreSQL tests

Capture synchronization evidence **after** the image build so it remains fresh. Review the actual source/offset/last-sync information; do not manufacture the status file.

```bash
timedatectl status > "$TF_ACCEPTANCE_DIR/host-time-status.txt"
timedatectl show -p NTPSynchronized --value > "$TF_ACCEPTANCE_DIR/ntp-status"
test "$(cat "$TF_ACCEPTANCE_DIR/ntp-status")" = yes

docker run --rm --network "$TF_NATIVE_PROJECT" \
  --read-only --cap-drop ALL --security-opt no-new-privileges \
  --memory 3g --cpus 2 --pids-limit 128 \
  --tmpfs /tmp:rw,nosuid,nodev,size=512m \
  --user "$(id -u):$(id -g)" \
  -v "$PWD/backend:/src/backend:ro" \
  -v "$PWD/scripts:/src/scripts:ro" \
  -v "$PWD/contracts:/src/contracts:ro" \
  -v "$TF_ACCEPTANCE_DIR:/acceptance:rw" \
  -w /src "$TF_NATIVE_PROJECT-worker" \
  python -B scripts/native_regulatory_acceptance.py \
    --database-url-file /acceptance/database-url \
    --expected-cluster-file /acceptance/cluster-id \
    --synchronization-evidence-file /acceptance/ntp-status \
    --output /acceptance/results

timedatectl status > "$TF_ACCEPTANCE_DIR/host-time-status-after.txt"
```

The helper:

- Refuses Windows/WSL and non-Python-3.11 execution before opening credentials.
- Requires a private URL file, fresh operator NTP evidence, an explicit cluster identity and a new database named `tf_acceptance_*`.
- Samples host realtime/raw-monotonic and PostgreSQL time at approximately 5 Hz across two 60-second preflight windows and continuously through tests. Backsteps, database readings outside the host round-trip bracket or sampler failures reject the run. Inspect retained clock-rate evidence as well; operator NTP status is not independently authenticated UTC or continuous stability proof.
- Copies public backend/scripts/contracts to a temporary test tree. Existing migrations plus candidate **0023** are installed only in that copy; parent/child processes share matching **explicitly unknown test-build metadata**. No running application metadata is rewritten.
- Runs real PostgreSQL authorization/snapshot, deferred binding, revocation, rollback and recovery tests using generated synthetic fixtures. Test-only approvals and simulated provider responses do not approve official law or validate Claude.
- Does not inherit provider credentials, read `.env`, activate inference, restore private/customer data or publish sources. The internal network excludes provider transport. Logs redact the disposable DB credential.

Results are `results/evidence.json` and `results/pytest.txt`. Preserve them. A nonzero exit or skipped required PostgreSQL case is a failed gate. A passing bounded run remains necessary evidence, **not** legal approval, live compatibility, production security certification or permission to dispatch.

Stop only the newly created test database when finished; retain its volume and evidence for review:

```bash
docker stop "$TF_NATIVE_PROJECT-db"
```

## 4. Subsequent application/Claude preparation — separate gates

Only after native clock and PostgreSQL acceptance:

1. Prepare a separate candidate API/packet-worker/draft-worker instance against its own new development database using the rehearsed candidate migration chain and matching release metadata. Do not migrate the existing `0019` application or original demo. Candidate 0023 has not yet passed a real upgrade/rollback rehearsal here.
2. Reproduce approved synthetic fixtures through existing services, or restore a verified **private synthetic probe** backup into the new database with no owner/privilege restoration. Preserve snapshot floors/epochs, immutable attempt/receipt history and actual provenance; never restore the original demo into this acceptance target. Verify archive hash and historical projections before/after. Do not reset cumulative spending/attempt records by presenting an empty ledger as the old account history.
3. Supply real qualified regulatory approval/publication/grant records through existing G5 governance. The current metadata-only research boundary cannot send unapproved passages to Claude.
4. Prepare and show the **new grounded payload**, exact digest, schema, model/endpoint, limits and source references. The retained v2 evidence-only approval is not reusable. Obtain explicit one-attempt approval and satisfy the existing provider controls without enabling general analyst inference prematurely.
5. Mount the provider credential server-side only after that authorization. Record one actual response/error and independent verification, then test the real React journey and refresh/history/human review. No fake response counts toward that gate.

No command above provisions paid infrastructure, contacts an unknown SSH host, commits, pushes or deploys the application. Section 4 is intentionally gated work, not a claim that API/worker/browser acceptance has been completed on an unavailable target.
