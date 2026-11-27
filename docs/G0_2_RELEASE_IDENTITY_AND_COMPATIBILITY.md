# G0.2 - release identity and compatibility

**Date:** November 14, 2026 (America/New_York). **Branch/base SHA:** `codex/project-initialization` / `a3b2ba49cd92c4aa0401842fa4999897fdc28713`. Candidate source is dirty; no commit, deployment, live migration, credential change or role change is part of this phase.

**Implementation acceptance: PASS in isolated environments. Live rollout/alignment: INCOMPLETE, deliberately not attempted.** The old running demo must not be represented as a verified deployment of this candidate.

## 1. Original compatibility gaps and running baseline

| Gap | Confirmed baseline / change |
|---|---|
| No common build identity | API health advertised 0.1.0, without a shared source/build identity. Added deployment-owned metadata and explicit unknown values |
| Readiness checked only one revision row | Added exact single-head checks, bounded probes, metadata/runtime checks and safe diagnostic reasons |
| Readiness did not prevent direct API/job operations | Added transaction-level compatibility gates to authenticated business requests, worker boundaries and background dispatch/cleanup |
| Worker release/schema mismatch | Added startup rejection and checks before claim, recovery, preparation, heartbeat and publication |
| No frontend build visibility | Added an admin-only footer detail; no redesign or analyst-facing infrastructure details |

Read-only live inspection: schema **`0012_evidence_foundation`**, while candidate requires **`0015_investigation_drafts`**. Candidate `release_report()` correctly returns `schema_incompatible`; the older running API is not replaced. Snapshot: 10 cases, 11 jobs, 11 assessments, 345 audits, zero typed evidence sources/transactions. No business writes were performed against the demo.

| Running component | Docker-reported image ID / repository digest | Declared source revision |
|---|---|---|
| Backend | `sha256:950cc5b5ef7602012d49ab1462b8c2bd1380b4e53328bbad497d581b0358aa34` | unknown |
| Frontend | `sha256:fbf9204ad80593ff06222159c7091b32c84c9c4f35b90829cb4d23c63119b807` | Label: `61141700fbe3bb03ee7379fd0a5cba5c9c5fc885` |
| Assessment worker | `sha256:e5733b34a61503ce1352c4952b4969e73c65effe8f53dcbe17d5f62fae20ec35` | unknown |
| Import worker | `sha256:c9428e3fc952c9d8d7317aa244f08d2922747a6132782c429a374f8ef239c63c` | unknown |
| PostgreSQL | `sha256:266d3c257594e195b309ae9d1805e54c788f1d7b375f56bf6c367aac6c917e7b` | not applicable |

These are Docker-reported identities, not signed source attestations. The frontend revision is a label declaration, not independently proven source provenance. Full local evidence: `runtime/g0-2/live-inventory.json`. None of these old image identities is assigned to the unbuilt candidate.

## 2. Files changed

| Files | Responsibility |
|---|---|
| `backend/app/core/release_metadata.py`, `scripts/build_release_manifest.py` | Strict metadata contract, deterministic public-source fingerprint, matching build IDs, generated metadata |
| `backend/app/core/release.py`, `backend/app/core/database.py`, `backend/app/main.py` | Schema/runtime guards, preserved health/readiness bodies, protected diagnostics and business-request fencing |
| `backend/app/services/{assessment_jobs,csv_imports,investigation_coordinator,batch_assessments,csv_staging}.py` | Guard existing worker/dispatcher/retention boundaries; existing algorithms remain unchanged |
| `backend/app/workers/{assessment_worker,csv_import_worker,investigation_worker,investigation_draft_worker}.py` | Startup checks and sanitized release identities/failure codes |
| `backend/tests/test_release_compatibility.py` | Metadata, readiness, API/privacy, locking, worker CLI and recovery acceptance |
| `frontend/src/release.tsx`, `frontend/src/release.test.tsx`, `frontend/src/App.tsx`, `frontend/vite.config.ts`, `frontend/e2e/workbench.spec.ts` | Minimal protected release display, compiled frontend identity and actual-browser role/accessibility/logout checks |
| `backend/Dockerfile`, `backend/Dockerfile.ml-worker`, `frontend/Dockerfile`, `backend/pyproject.toml` | OCI version/contract labels and package inclusion of generated metadata |
| `.gitignore`, `frontend/.prettierignore` | Generated deployment metadata excluded from Git/formatting |

`README.md`, Compose startup/port edits, existing branding/style/logo work and earlier audit documents are outside this phase's edits. The shared `App.tsx` receives only the release import/footer addition; branding changes are preserved.

## 3. Release manifest contract

Generate **before** building images; this command writes metadata only, not images/services/database state:

```powershell
.venv\Scripts\python.exe -B scripts/build_release_manifest.py
```

| Field | Contract |
|---|---|
| `contract` | `trueflag.release.v1` |
| `git_commit` | Full Git SHA or `unknown`; does not pretend dirty files were committed |
| `source_state` | `clean`, `dirty` or `unknown` |
| `source_sha256` | Sorted, path-bound public application/build-input byte fingerprint; excludes private assets, environment files and generated metadata |
| `build_id` | Deterministic SHA-256 of canonical identity fields except itself; not a random or invented release tag |
| `backend_version`, `frontend_version`, `worker_version` | Current compiled versions **0.1.0**; mismatches reject the supplied manifest |
| `expected_schema_revision` | `0015_investigation_drafts`; cannot override the code's expected revision |
| `image_digest` | `unknown` for the unbuilt candidate; no privileged Docker socket or environment dump is introduced |
| `metadata_status` | Server-computed `available`, `unknown` or `invalid`; not accepted as an uploaded field |

Backend file: ignored `backend/app/_release.json`, included by package data/Docker context when generated. Frontend file: ignored `frontend/release-build.json`; only frontend version, opaque build ID and source state enter browser code. Without Git metadata, unavailable values stay unknown. Without a metadata file, code-owned version/contract/schema remain known; Git/build/image provenance is unknown. Unknown provenance is **not** proof of aligned/signed images, but does not override a valid compiled contract and schema.

Strict parser rejects extra/duplicate keys, invalid types, oversized content, wrong versions/revision/contract and invalid digest formats/checksums. No runtime API accepts uploaded release metadata or models. Metadata is deployment-owned, self-reported and unsigned.

Verified candidate build ID: `7e75c5251457fadfbc077a15d53e2dd3fc4783662d411940b758b5bcc19c51d8`; public-source SHA: `b68bbbd720b8602c12593db2672a8a8d7ae0d366e64409876d4f1b708aa7879a`. Two consecutive generations were identical; frontend/backend IDs matched. Metadata writes use same-directory atomic replacement. Evidence: `runtime/g0-2/candidate-identity.json`.

## 4. Readiness and dependency behavior

| Interface / condition | Result |
|---|---|
| `/health` | Existing `{status: ok, service: trueflag-ai, version: 0.1.0}`; process liveness only |
| `/ready`, compatible | Existing `{status: ready}`, HTTP 200; `X-Readiness-Code: compatible` |
| `/ready`, incompatible/unavailable | Existing `{status: not_ready}`, HTTP 503; sanitized reason header only |
| `GET /api/v1/internal/release` | Current active **admin** only; release/schema/dependency/ML-identity details; no credentials/configuration/customer features |
| Wrong/multiple/missing schema heads | `schema_incompatible` / `schema_missing`; no automatic migration |
| Database inaccessible | `database_unavailable`; no raw exception or connection string |
| Schema lock/probe timeout | `schema_unavailable`; database reachable but compatibility unconfirmed |
| Malformed/wrong release metadata | `release_metadata_invalid` / `release_contract_incompatible` |
| Unsupported Python | `python_incompatible` |

Standalone probes use transaction-local 1 s lock / 2 s statement limits. PostgreSQL is required for API readiness. Assessment workers are asynchronous: temporary worker downtime does not prevent durable queue admission. Storage checks remain enforced on use; backend readiness does not falsely certify every optional capability, ML runtime, approved corpus or provider.

Authenticated business sessions enforce compatibility before operations. Authentication/identity and admin diagnostics remain reachable for troubleshooting when their existing user schema is usable. Normal public response bodies and assessment/CSV contracts are preserved. No new public inference endpoint.

## 5. Worker enforcement and durable-state safety

- Assessment/import/evidence-investigation/fake-draft CLIs reject incompatible startup before job processing; errors contain fixed codes, not stack traces or secrets.
- Existing worker service boundaries recheck metadata/Python/schema before claiming/recovering/preparing/renewing/publishing. Incompatible workers cannot write a failure/result merely to clear a lease.
- PostgreSQL `FOR SHARE` holds the revision row for short guarded transactions, preventing a concurrent revision update before those writes commit. Long RF/SHAP computation is not locked; subsequent heartbeat/publication checks fence an incompatible execution.
- Pending/running jobs remain durable. On compatible restoration, normal expiry recovery/fencing prevents stale-worker publication and duplicate assessments. No job deletions, automatic case closure, dismissal or SAR action.
- Assessment CLI preflight reuses original SHA/runtime/policy checks, **without deserializing** a model; successful worker output identifies `sha256_and_dependencies_verified_not_deserialized`. Original fitted loader/scoring/SHAP verification still runs when processing.
- API ML status is explicitly `not_checked_in_api_process`; an expected hash is not labeled as a loaded/verified model.

Read-only inspection also verified the existing running worker's approved bundle SHA, model `20261018_183648_RF`, model SHA `ea0806d579345d7085c00d26c188805e74de574028bda4a4573222b06e739917`, and pinned dependency metadata. This did not execute scoring or deserialize the live model. Evidence: `runtime/g0-2/live-scientific-identity.json`.

## 6. Frontend identity

- Admin workspace footer: native accessible **Release** detail with frontend build/version/state and backend build/readiness; unequal known IDs display **Builds differ**.
- No login-screen/analyst identity panel, raw schema/image digest/model assets in browser metadata, mock risk scores or redesign.
- Authenticated fetch is aborted on unmount/logout. HTTP 401/403 invokes existing permission cleanup. Older backends without the endpoint display **unavailable** rather than breaking casework.
- Vite rejects malformed supplied build metadata; missing build metadata is explicitly unknown. The old running frontend remains unchanged.

## 7. Verification commands and results

Tests use the existing recovery clone, fresh disposable schemas, pinned Linux images and synthetic records. Actual-model references remain private/read-only. Temporary sanitized G0 diagnostic launchers/reports are ignored under `runtime/g0-2/`.

```powershell
.venv\Scripts\python.exe -B runtime/g0-2/run.py --label focused
.venv\Scripts\python.exe -B runtime/g0-2/run.py --label focused-final
.venv\Scripts\python.exe -B runtime/g0-2/run.py --full --label full
.venv\Scripts\python.exe -B -m ruff check backend scripts
.venv\Scripts\python.exe -B -m ruff format --check backend scripts
.venv\Scripts\python.exe -B scripts/run_frontend_e2e.py
.venv\Scripts\python.exe -B scripts/run_ml_verification.py --check tests
.venv\Scripts\python.exe -B scripts/run_ml_verification.py --check scoring
.venv\Scripts\python.exe -B scripts/run_ml_verification.py --check policy
.venv\Scripts\python.exe -B scripts/run_ml_verification.py --check shap
```

```text
# frontend directory
npm.cmd run format:check
npm.cmd run lint
npm.cmd test -- --reporter=dot
npm.cmd run build
```

| Run | Actual outcome |
|---|---|
| Initial focused Linux/PostgreSQL | 26 passed / 0 failed / 0 errors / 0 skipped |
| Focused with revision-transaction fence | 27 passed / 0 failed / 0 errors / 0 skipped |
| Full Linux/PostgreSQL | **911 passed / 0 failed / 0 errors / 0 skipped**; 856.172 s; `runtime/g0-2/full-1.json` |
| Native Windows/SQLite initial release + foundation subset | 32 passed / 0 failed / 7 PostgreSQL-dependent skips; 1 existing TestClient deprecation warning |
| Native Windows/SQLite final release + foundation subset | **34 passed / 0 failed / 10 skipped**; 15.42 s; skipped tests require PostgreSQL/Linux workers; 1 existing TestClient deprecation warning |
| React | 54 passed / 0 failed / 0 skipped |
| Frontend lint/build | Passed |
| Formatting | Initial generated-JSON/new-test formatting warnings corrected; final frontend format check passed; Python lint/format passed |
| Chromium actual API/import/ML workflow | **11 passed / 0 failed / 0 skipped**, 1.8 min after explicit release visibility/accessibility/logout assertions; initial 11-test run also passed |
| Pinned Linux ML unit tests | **178 passed / 0 failed / 0 skipped** |
| Frozen scientific replays | **4,000 scores / 12,000 routes / 4,000 SHAP explanations matched**, zero processing failures/mismatches; `runtime/g0-2/ml-verification.json` |

The Windows subset executed `.venv\Scripts\python.exe -B -m pytest backend/tests/test_release_compatibility.py backend/tests/test_foundation.py -q --tb=short -p no:cacheprovider --basetemp runtime/g0-2/sqlite-final-<unique-id>`, with `PYTHONPATH=backend`, PostgreSQL/real-assessment opt-ins unset, a process-only ephemeral signing secret and fixture-owned SQLite databases. It is not Windows SHAP or a separate complete Windows/PostgreSQL suite.

Chromium's `DATABASE_URL` was supplied privately in process memory for the validated recovery clone; ports 18010/15173 and worker services were temporary. No fixture credentials are included here. Existing test-only JWT `iat` backdating for Docker clock drift remains unchanged; browser acceptance does not certify strict production-clock login behavior. Node color-environment and TestClient deprecation warnings are environmental limitations, not hidden test failures.

RF maximum score error was **0** (`atol=1e-12`, `rtol=0`); policy routes/traces/totals had exact parity. SHAP encoded/grouped/base reference differences and model-score difference were **0**, reconstruction residual at most **3.1086244689504383e-15**, below the original `1e-6` tolerance. Missing-income 87 versus observed-zero 22 remained distinct. No retraining or reference adjustment; existing tiny synthetic-tree unit fixtures are separate from the frozen RF.

Acceptance covers wrong/missing/multiple revisions, malformed/missing metadata, current-role access, unavailable DB, bounded locks, transactional revision fencing, all four real Linux CLI rejection paths, actual approved-asset preflight and lease recovery with one completed assessment.

## 8. Limitations and acceptance boundary

- **No deployment:** currently running images remain old; live schema 0012 is incompatible with candidate 0015. Live alignment is incomplete and cannot be claimed from isolated acceptance.
- No schema-content attestation beyond exact Alembic head; a forged version row is not a proven physical schema. No signatures/SBOM/source-to-image cryptographic supply-chain attestation.
- No distributed deployment registry: compatible compiled contract/schema is enforced, not an exact Git-SHA equality handshake with every peer. Footer exposes known build mismatch; unknown peers remain unknown.
- Generate metadata before builds; all components must receive the same intended snapshot. New candidate image digests remain unknown until images are actually built/recorded in a separately authorized phase.
- Revision row locking requires appropriate PostgreSQL row-lock privileges. No grant/role changes are made here; least-privilege deployment acceptance remains G0.4.
- Readiness/CLI probes are bounded; guarded business transactions retain their existing query/deployment timeout policies. Controlled maintenance/draining and final role/timeout acceptance remain separate rollout work.
- Existing Compose still contains its explicit one-shot migration dependency. This phase did not run `compose up`, rebuild images or invoke that service; do not treat an unreviewed restart against the live DB as a safe migration plan.
- Readiness is bounded dependency/schema compatibility, not production security/HA/capacity certification.

Preservation check: all changed existing files are within the 20 approved G0.2 paths; no unrelated-file differences. Removing only the new `App.tsx` import/footer reproduces its pre-task hash, proving the branding edits were preserved. Private `.env` and 25 baseline-manifest artifacts matched their original hashes. Publication checks passed for 289 source candidates; generated metadata remains ignored, and the built frontend contains the matching final build ID without embedding the model artifact identity. Changes remain uncommitted.

## 9. G0.1 risk retained

The original 880-pass/3-failure/1-setup-error run remains evidence. G0.1 subsequently passed 884/884 and repeated cases without identifying the original causes. Observed small clock backsteps do not establish causality. This phase does not change JWT leeway, original test barriers or assert that instability is fixed. Any current recurrence must be reported separately.

The current full run passed all 911 tests while the observer recorded 57 small clock-backstep events and only the two intentional expired/future-token rejections. No claim of clock synchronization or resolution follows. Historical reports were preserved.

## 10. Recommendation for G0.3

Prepare a recoverable backup/restore and schema-upgrade rehearsal on a copy, carrying exact candidate/source/image identities and compatibility results. Do not automatically apply 0013-0015 to the demo, promote images, change runtime roles or begin evidence/LLM/RAG work. G0.3 was not started.
