# Persistent upload workspaces

## User behavior

- Cases shows only successfully imported cases in the selected upload session. Both created and legitimately reused case receipts qualify; invalid/conflicting rows do not.
- The first workspace adopts the current administrator's existing uploads. It never infers provenance from a source-ID prefix, fixture name, synthetic classification or model label.
- Seeded/direct-ingestion cases remain retained outside the uploaded-case list. Uploaded synthetic data remains visible. No canonical alerts, cases, assessments, evidence, jobs or audits are deleted.
- **Add CSV to this session** supports multiple files, including split CSV parts. It does not create a new workspace.
- **Start new upload session** requires confirmation. The previous workspace becomes history; its jobs continue and results remain stored. Starting a session never triggers import, assessment, investigation or external-provider execution.
- **Session history** restores previous sessions and recent upload receipts. Opening Imports resumes the latest nonexpired receipt. Authorized saved import/upload links resolve their owning session before display.
- Selection is stored per authenticated account in PostgreSQL. Refresh, browser restart, logout/login and API restart do not erase it. Logout still clears protected browser state and requires valid authentication on return.
- These are user workspaces, not a new enterprise tenant/organization boundary. Existing case assignment/RBAC checks remain mandatory.

## Persistence and migration

| Table | Responsibility |
|---|---|
| `upload_sessions` | Owner, creation timestamp and unique hashed creation key; creation-version binding rejects conflicting retries. |
| `upload_session_items` | A staged upload belongs to exactly one session. Existing `csv_imports` and `csv_import_rows` supply case membership. |
| `upload_workspaces` | Current selection and optimistic version per user. |

- Migration `0019_upload_sessions` is additive. Empty tables support rollback to `0018_human_casework`; rollback refuses retained session history.
- Historical upload adoption is an audited, transactional first-use initialization. Upload-to-session binding shares the existing staging transaction and actor row lock.
- Selection is a view change, not a case reassignment or security grant. Another administrator cannot enumerate another owner's upload sessions. Analysts/supervisors discover only sessions containing cases they are currently permitted to read; their counts include only permitted cases, and raw upload receipts remain withheld.
- Active selection is revalidated on access. Revocation removes unavailable selections/results. Case-list predicates run in SQL before count, ordering and pagination; frontend filtering cannot broaden them.
- Actor row locks serialize create/select/upload operations. Version conflicts return 409. Duplicate creation keys return current workspace state without reactivating a session superseded by a later action.
- Stale explicit upload-session headers and attempts to move a duplicate upload into another session fail atomically. Successful upload replay preserves original membership.

## API additions

| Contract | Behavior |
|---|---|
| `GET /api/v1/upload-sessions?limit=20&offset=0` | Authorized active session plus paginated session history; limit 1–50, offset 0–10000. Active metadata includes at most 20 recent resume receipts. |
| `POST /api/v1/upload-sessions` | Admin only; strict `{version: integer}` and `Idempotency-Key`. Creates/selects a new empty session; 201, or sanitized 403/409/503. |
| `PUT /api/v1/upload-sessions/{id}/selection` | Strict `{version: integer}`; current access and stale-version checks. |
| `GET /api/v1/upload-sessions/lookup/{upload\|import}/{id}` | Owner/admin-only lookup of the associated session; read-only, no implicit selection. Unknown/other-owner references are opaque 404. |
| `POST /api/v1/batch-uploads` | Optional `X-Upload-Session-ID` binds the upload to the active owned session. Existing callers omitting it retain compatibility and bind to the current session. |
| `GET /api/v1/cases` and `GET /api/v1/case-queue` | Additive `upload_session_id` and `origin=uploaded` filters; all existing assignment, queue, search and sorting predicates still apply. |

Existing unscoped case APIs retain their legacy authorized behavior for direct-ingestion integrations. The application Cases screen always supplies the selected session. This feature hides seeded records from the normal upload workspace; it is not a destructive database purge.

## Retention and limitations

- Canonical imported records and completed results remain subject to existing retention controls; no browser-only storage or automatic session reset was added.
- Raw staged CSVs keep the existing expiration policy. Session persistence does not extend their lifetime. An expired, unimported file must be uploaded again; a completed import remains resumable after its raw file expires.
- Browsers cannot restore an unsubmitted local File object after a full restart. After server staging, saved upload/validation/import identifiers support recovery. In-memory file selection is scoped to its session and survives same-session component remounts.
- Current history lists recent 20 uploads per session; older uploads remain accessible through their authorized saved links/IDs. Session history itself is paginated.
- Case-level URLs remain authorized historical records. A new session does not revoke access to previously authorized case history.
- No regulatory publication, Luminal activation, scientific changes, automated case disposition or source fabrication.

## Verification

- `backend/tests/test_upload_sessions.py`: persistence, uploaded-only SQL filtering, legacy adoption, migration upgrade/rollback/history refusal, input validation, authorization, revocation, owner-only lookup, stale requests, rollback, concurrent idempotency and actual durable imports.
- `frontend/src/upload-workspace.test.tsx`: restoration, explicit confirmation/cancel, safe empty states, revocation and collapsed history.
- `frontend/src/batch.test.tsx`: selected-file recovery across same-session remounts.
- `frontend/e2e/batch.spec.ts`: actual Linux/PostgreSQL CSV→RF/policy/SHAP→persisted results/export, worker downtime, revocation, API restart and upload-session restoration after refresh/login.
- Targeted Linux/PostgreSQL backend run: **181 passed, 0 failed, 0 skipped**; original staging/case/import run: **148 passed** (overlapping tests; do not sum as unique coverage).
- Pinned Linux ML suite: **178 passed**, 88 subtests passed; frozen 4,000 RF / 12,000 policy / 4,000 SHAP acceptance checks retained.
- React: **138 passed**; Chromium: **6 passed**, followed by a passing focused replay that also verifies an old saved import URL reselects its original session after a new session starts.
- Native Windows/SQLite workspace/foundation checks: **32 passed, 2 skipped** (PostgreSQL-only concurrency/import acceptance covered in Linux).
- Ruff, ESLint, Prettier, TypeScript/Vite build, private-publication boundaries and whitespace checks passed. No production-capacity or accessibility certification is inferred.

### Local migration rehearsal

- A protected PostgreSQL custom-format backup was restored into a separate database on the identity-verified isolated cluster.
- Upgrade→rollback→upgrade preserved 4,026 cases, 4,026 alerts, 4,028 assessments, 4,028 assessment jobs, 12 uploads, 6 imports and 4 investigation runs. The original demonstration cluster was excluded by identity checks.
- No backup contents, credentials or customer feature values belong in Git or this document.

### Running local application

- Following the successful rehearsal and acceptance tests, a fresh protected backup was taken and revision 0019 applied to the owned isolated application database. Existing canonical table counts were unchanged across migration. The original demo cluster was not migrated or modified.
- The API, database and existing Linux workers were restarted using the owned application setup; frontend `http://127.0.0.1:5173`, API `http://127.0.0.1:8010`.
- Real Chromium verified **4,000 uploaded cases visible, 26 non-imported cases excluded**, active selection restored after refresh, actual existing batch results resumed, and protected state cleared on logout. No sample cases, model scores or import records were added to the running application by this check.
- Desktop/mobile screenshots passed bounded page-width and automated WCAG-tagged Axe checks in the examined states (zero findings). Artifacts: ignored `runtime/upload-workspace-review/`.
- Protected backup/rehearsal journal: ignored `runtime/local-app/<owned-run>/upload-session-migration.json`; it records archive hashes and the retained rehearsal database without copying private configuration into documentation.
- No commit, push, provider request, model retraining or regulatory publication.

### Reproduction commands

Run from the repository root; the ignored local runner first verifies the isolated database/container identity and uses disposable schemas. Credentials remain inside the protected runtime configuration.

```powershell
.venv\Scripts\python.exe runtime/local-app/test_upload_sessions.py backend/tests/test_upload_sessions.py backend/tests/test_batch_assessments.py backend/tests/test_batch_export.py backend/tests/test_assessment_jobs.py backend/tests/test_security_foundation.py backend/tests/test_foundation.py backend/tests/test_browser_session.py backend/tests/test_remembered_login.py backend/tests/test_release_compatibility.py
.venv\Scripts\python.exe runtime/local-app/test_upload_sessions.py backend/ml_tests
.venv\Scripts\python.exe runtime/local-app/ux_e2e.py --suite batch
node runtime/local-app/verify-upload-workspace.mjs
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run format:check
npm.cmd --prefix frontend run build
.venv\Scripts\python.exe scripts/check_publication.py
git -c core.safecrlf=false diff --check
```
