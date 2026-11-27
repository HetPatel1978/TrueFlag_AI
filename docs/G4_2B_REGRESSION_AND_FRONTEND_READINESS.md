# G4.2B — Regression investigation and frontend readiness

## Browser revocation investigation

- Prior G3.1 G4.3A browser failure stopped **before** source revocation: the Generate Summary control detached and the UI reported time verification unavailable. Earlier reports also retain unrelated, unconfirmed analytics 503 history. This task does not claim to establish that historical root cause or fix host/WSL clock synchronization.
- No demonstrated application authorization defect justified a production change. Strengthened `frontend/e2e/drafts.spec.ts` with explicit phase checkpoints, real pending-job read before revocation and real protected result read afterward. Auth is captured only from the already-authorized browser request in memory; never printed/persisted. HTTP 503/429 cannot satisfy the expected invalidation assertion.
- `scripts/run_investigation_e2e.py --suite provider` routes to the existing simulation browser suite in the G4.2B isolated fixture. Its live-provider flag remains false; this is not a live-provider launcher.
- Focused `--grep 'source revocation'`: **1 passed / 0 failed / 0 skipped**, 8.1 seconds. Complete suite: **5 passed / 0 failed / 0 skipped**, 29.4 seconds. Both genuinely exercised revocation; this is not a passing pre-revocation substitute.

Exact persisted checkpoint sequence:

1. Verified parent ready.
2. Durable draft requested.
3. Protected API confirms **Pending**.
4. Source revocation acknowledged by fixture after the real evidence service commits it.
5. Protected API confirms **Invalidated**, draft absent.
6. UI shows source-specific denial and no Financial Observations.

`revocation-checkpoints.json` and actual browser/screenshot artifacts are retained privately beneath the directory identified by `runtime/g4-2b/current.json`. Full-suite success is local regression evidence, not stable-runner release acceptance.

## Tests — actual per-invocation results

Use `.venv/Scripts/python.exe -B` from repository root. All PostgreSQL runs use disposable schemas after verifying owned/forbidden cluster identities. No original-demo target, real key or external transport is available to the offline test containers.

| Command/suite | Passed | Failed | Skipped |
| --- | ---: | ---: | ---: |
| `runtime/g4-2b/run.py --mode unit --label provider-offline-contracts` | **68** | **0** | **0** |
| `runtime/g4-2b/run.py --mode materialize --label provider-postgres-integration` | **87** | **2** | **0** |
| `runtime/g4-2b/run.py --mode regression --label coordinator-clock-security` | **111** | **1** | **0** |
| `scripts/run_investigation_e2e.py --suite provider --grep 'source revocation'` | **1** | **0** | **0** |
| `scripts/run_investigation_e2e.py --suite provider` | **5** | **0** | **0** |
| `frontend/`: `npm.cmd test` | **111** | **0** | **0** |
| `scripts/run_ml_verification.py --check tests` | **178** | **0** | **0** |

Focused browser test is a subset; do not aggregate it as unique coverage. These are relevant suites, **not the complete backend suite**.

| Retained failed test | Sanitized observed clock evidence |
| --- | --- |
| `test_clock_health_denial_prevents_mock_dispatch` | now **1794862942** < floor **1794862943**, epoch 2, regressed true; real clock denial before the intended mock-dispatch check completes. |
| `test_supervisor_role_revocation_prevents_resolution` | now **1794862970** < floor **1794862971**, epoch 2, regressed true; workflow setup/read denied before its intended final assertions. |
| `test_postgres_immutable_history[investigation_runs]` | now **1794863139** < floor **1794863140**, epoch 2, regressed true; expected-success preparation blocked. |

Failures remain failures. Controlled backward/forward/expired-replay tests produce additional deliberate guard observations; those are separated from the three unexpected environmental denials above. No snapshot, authorization or financial-verification assertion was relaxed.

## Security coverage and scientific parity

- Offline adapter tests cover invalid credentials, unsupported HTTP/model/schema envelopes, redirects, timeout, rate limits, malformed/oversized responses, usage/number/type errors, forged references, attempted tool/claim injection, cancellation and Linux child termination. They use mock transport, not real-provider security claims.
- Real PostgreSQL tests exercise durable attempts, conservative grant-wide spend reservations, duplicate intent handling, no ambiguous paid redispatch, worker recovery, provider withdrawal, source revocation, audit/result rollback and human casework separation. Two clock-blocked cases above remain incomplete in this run.
- Evaluation materialization independently checks all 36 sources/scenarios and canonical numeric references. Four lifecycle denials remain no-egress security outcomes. No independent semantic labels are fabricated.
- Frozen checks: RF **4,000** matched, max absolute error **0**; policy **12,000** routes, trace/retained/reduction differences **0**; SHAP **4,000** verified, **0** mismatches. Maximum reconstruction residual `3.1086244689504383e-15` versus `1e-6` tolerance; encoded/grouped/base/model-score differences zero. Missing income 87 / observed zero 22 preserved. Pinned 178-test runtime completed in 10.488 seconds.

## Frontend provenance contract

| Intended label | Required persisted evidence | Current behavior |
| --- | --- | --- |
| Offline Simulation | Existing fake-provider mode, simulation true/live false, exact immutable parent and verified source/numeric projection. | Implemented and exercised. |
| Live AI — Awaiting Evaluation | Genuine candidate attempt/result identity and live provenance, current case/source authorization, independent verification; no quality approval implied. | Existing internal candidate storage only; public simulation gateway intentionally rejects it. No live result exists. |
| Evaluated Live AI Findings | Above plus an independently approved, version-matched evaluation/adjudication record with adequate coverage and approved thresholds. | No such approval/read model exists; label and live-generation control remain unavailable. |
| Human-Reviewed Findings | Exact finding/version-bound human decision/rationale, current source authority and separate review history; preserve original simulation/live provenance. | G3 casework stores/displays those decisions separately. It does not upgrade simulated results to real AI or independently evaluated quality. |

No new unsupported badges, sample live findings or placeholder generation buttons were introduced. Existing Apple-inspired UI, logout cleanup, source-linked views and bounded polling are preserved. Current backend cannot justify evaluated-live status; future G4.3B needs a reviewed persistence/projection contract and separate activation authorization.

## Environment and preservation

- Initial baseline **449** files; G3.1/G4.3A and unrelated uncommitted changes preserved. Candidate expected schema remains **0018_human_casework**. No new migration.
- Original demo database remains stopped and unmodified; current live schema not SQL-verified (last known `0012_evidence_foundation`). Existing assessment/import workers were observed, not reconfigured or restarted. No credentials/roles/`.env` edits.
- No live calls, regulatory publication, automatic resolution, SAR action, model training, commit, push or deployment.

### Final checks

| Check | Actual result |
| --- | --- |
| Preservation | `runtime/g4-2b/finalize.py --stop`: **449** baseline files compared. Only four intended existing paths changed: browser test, its guarded launcher and two ignored release metadata files. New preflight module/script/three tests and four reports are additional files. All G3.1/G4.3A implementation, unrelated work, `.env`, scientific/regulatory assets and original backup hashes unchanged. |
| Database isolation | Original G1 template and G2 clone match their pre-run state. All temporary schemas cleaned. Retained copy: **111** foreign keys checked, **0** orphan rows, **0** invalid constraints/indexes. No persistent candidate migration. |
| Original demo | Container/image identity unchanged; still stopped. Current live schema **not verified**. No startup, repair, migration, role/credential change or demo write. |
| Cleanup | Stopped only the identity-verified owned rehearsal PostgreSQL cluster. Temporary browser API/worker/frontend fixtures cleaned by launcher; volumes, backups and original records retained. Pre-existing demo assessment/import workers left unchanged. |
| Static/build checks | Ruff check and format passed (**239 files**). Frontend lint, Prettier, TypeScript and Vite production build passed (**49 modules**). `git diff --check` passed. |
| Publication | `scripts/check_publication.py`: **PASS, 416 source candidates**, private/secret ignore boundaries verified. Sandbox global Git-ignore read warnings did not change configuration or permissions. No document/source publication action. |
| Release identity | Source SHA-256 `fd09900f8243da0edd11bbd3fd12084f4e43c83b252a631e6a4a1e83cff4cfa5`; build ID `62d0f4af9a1697a02086f103f524c1fbd7012e2dffafffddb070b87f182006c8`. Expected schema stays 0018. Final build uses matching ignored metadata. |
| Git | `codex/project-initialization`, HEAD `a3b2ba49cd92c4aa0401842fa4999897fdc28713`, unchanged and uncommitted. No push/deployment. |

Preparation evidence is complete for the authorized scope. **Three retained PostgreSQL clock failures remain release blockers; 0 live calls means no authenticated compatibility or model-quality conclusion.** Passing browser revocation proves this local scenario exercised denial; it does not repair the host clock or establish stable-runner acceptance.

**G4.3B recommendation: DO NOT ACTIVATE.** Resolve explicit provider/privacy/transfer/budget approval, expected secret binding, first-probe authorization/contract bootstrap, global call/expiry enforcement, stable-runner acceptance and independent semantic review first.
