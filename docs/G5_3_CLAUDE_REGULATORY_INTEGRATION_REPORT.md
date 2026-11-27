# G5.3 — Durable regulatory binding and Claude integration

Date: 21 November 2026. Branch: `codex/project-initialization`; HEAD inspected: `a3b2ba4`.

**Decision: PARTIAL IMPLEMENTATION / FUNCTIONAL ACCEPTANCE NOT ACHIEVED.**
One genuine, explicitly scoped synthetic Claude request occurred in this task. It returned HTTP 400, not independently verified findings. Official regulatory approvals are absent. Broader worker, clock and browser acceptance has unresolved failures. Do not present this milestone as a live Claude/RAG demonstration.

## Implementation inventory

| Existing component | G5.3 change / responsibility |
| --- | --- |
| `services/regulatory_investigation.py` | Reuses packet verification and approved-source selection; adds packet-row identity, frozen query/snapshot, grant revision, clock epoch and a 900-second context lifetime. |
| `models/regulatory_drafts.py` | Immutable, run/actor/case/parent/manifest-bound context record; original regulatory citations, source/version/release/reviewer metadata remain in the existing typed governance envelope. No parallel source registry. |
| `services/investigation_drafts.py` | Atomically stores binding with intent/job/audit; revalidates at preparation, dispatch, completion and protected result reads; uses existing leases, attempt ledger, recovery and independent verifier. |
| `schemas/provider_live.py`, `schemas/regulatory_investigation.py` | Opt-in typed grounded configs/proposals/results preserve ordinary ungrounded contracts and configuration hashes. |
| Existing simulation/Claude workers | Receive typed bounded grounded input and use existing process isolation. No second provider adapter or queue. |
| `services/draft_api.py`, `api/investigation_drafts.py` | Protected server-owned provider selection; additive capabilities and atomic-start APIs; verified Claude projections and citation-aware results. Evidence-only requests do not require regulatory approvals. |
| `frontend/src/drafts.tsx`, `investigation.tsx`, `regulatory-guidance.tsx` | Existing workbench distinguishes verified Claude results, simulation and unavailable states; optional bounded regulatory query; authorized source resolution; no visual redesign. |

All backend paths above are relative to `backend/app/`. Existing independent Decimal calculations, source verification, model assessments, RF/policy/SHAP artifacts and human decisions remain unchanged.

## Durable workflow and schema

Candidate `backend/alembic/candidates/0021_regulatory_draft_bindings.py`, after candidate `0020_claude_provider`, adds one table and PostgreSQL integrity triggers. It is **not installed in the running application**; the existing migration head and local app remain `0019_upload_sessions`.

- Composite actor/run/manifest foreign key and parent/case identities bind the stored context to the admitted request. Update/delete/truncate are rejected. A deferred run-envelope trigger requires its matching binding at commit.
- A retry reuses the original context, including its expiry. A different provider, packet or query conflicts; retries do not renew authority.
- Current case/evidence/model revisions, grants, source versions and release selection are rechecked. Revoke/regrant changes the grant revision; an old binding cannot resume under the replacement grant.
- Expired contexts, clock-epoch changes and changed/withdrawn sources prevent dispatch, publication or current disclosure. History and conservative spend reservations remain retained.
- Empty candidate downgrade/re-upgrade was rehearsed in a disposable schema. Downgrade explicitly refuses retained bindings. The original demonstration database was not accessed or migrated.

### API additions

| Endpoint | Contract |
| --- | --- |
| `GET /api/v1/cases/{case_id}/investigation-drafts/capabilities` | Authorized provider choice and regulatory-grounding flag; no credentials. |
| `POST /api/v1/cases/{case_id}/investigation-drafts/start` | Existing `InvestigationRequest`, optional `provider=auto/simulation/claude`, required `Idempotency-Key`; HTTP 202 with parent and child IDs. Admits both jobs in one transaction. Workers wait for verified parent completion. Closing the browser cannot interrupt admission. |
| Existing `POST .../investigation-drafts` | Preserves original parent/hash fields; optional explicit provider and regulatory query. Grounding is frozen only against an already verified packet. |
| Existing protected detail/history | Typed provider identity and verified results; no raw predictors or provider error bodies. Opening results revalidates current authority. |

The atomic-start endpoint is evidence-only. Optional regulatory binding is requested against a selected verified packet using the existing draft-request endpoint. The frontend does not silently convert an explicitly failed live request into simulated results.

`anthropic_analyst_generation_enabled` defaults to false and is independent from key presence, compatibility and regulatory approval. The existing explicit synthetic bootstrap remains separately scoped. No general analyst inference was activated.

## Historical Claude attempts — individually evidenced

Artifacts are private under `runtime/claude-demo-20261120/`. They are not publication candidates.

| Historical receipt | Retained evidence | Classification and corrective action |
| --- | --- | --- |
| `claude_probe_result.json` | HTTP 200; generic invalid-response failure; no detailed schema/usage/model receipt | Insufficient retained diagnostics to identify the precise cause. Do not infer an authentication or numeric-verification failure. |
| `claude_diagnostic_result.json` | HTTP 200, model matched, one text block, `end_turn`, schema invalid; 6,485 input / 2,033 output tokens | Structured-output contract failure confirmed; exact invalid field was not retained. |
| `claude_diagnostic_detail_result.json` | HTTP 200; `packet_sha256:string_pattern_mismatch`; 6,485 / 2,307 tokens | Model did not reproduce the application-owned digest. Wire schema now constrains the exact packet hash; original local hash verification remains mandatory. |
| `claude_fix_result.json` | HTTP 200; schema parsed, independent verification failed; 6,515 / 2,283 tokens | Exact verifier reason unavailable in this receipt. Do not retroactively assign the next attempt's cause to this attempt. |
| `claude_verification_result.json` | HTTP 200; `claim_type_mismatch`; 6,515 / 2,225 tokens | Section/claim-type mismatch confirmed. Wire schema now uses separate calculated/observed/model-signal constants; independent section/type verification remains intact. |

No failed historical output was rewritten or accepted. Contract tests exercise these corrections, but the new wire changes have **not** passed genuine live acceptance.

## Actual G5.3 Claude request

| Item | Observed result |
| --- | --- |
| Provider / requested model | Anthropic / `claude-sonnet-5-5` |
| Destination | `https://api.anthropic.com/v1/messages` |
| Preflight | Existing synthetic case, packet and current authorization/clock checks passed before the bounded attempt. |
| Requests dispatched this task | **1**, no automatic paid retry |
| HTTP status / latency | **400 / 1,429 ms** |
| Returned model / token usage | Not available in retained receipt |
| Structured output / independent findings | No usable response; not passed; no finding published |
| Estimated actual charge / invoice | Unknown; do not report zero |
| Attempt reservation | **$2.14 retained** |
| Cumulative ledger | 6 attempts, **$12.70 conservative reservations** against the existing $20 scope |
| Known historical token-rate estimates | $0.14048 across four receipts with usage; not total account spend or an invoice |

Commands executed through the existing adapter, isolated candidate runtime, attempt ledger and approval scope:

```powershell
.venv\Scripts\python.exe scripts/run_claude_diagnostic_probe.py --claim-fix --preflight
.venv\Scripts\python.exe scripts/run_claude_diagnostic_probe.py --claim-fix --recover-pre-dispatch
```

The HTTP 400 was received before the adapter retained bounded HTTP-error metadata. Its body cannot be recovered from this receipt; the cause remains **unconfirmed**. The adapter now captures only an allowlisted error type, whether a schema was mentioned and a bounded request ID. Raw messages/content/credentials are excluded. This is an observability correction, not proof that the rejected request has been fixed.

Anthropic's [structured-output documentation](https://platform.claude.com/docs/en/build-with-claude/structured-outputs), retrieved 21 November 2026, documents `output_config.format`, scalar `const` and schema restrictions. This supports the request design; it does not establish the cause of this particular HTTP 400 or prove account/model availability. No further paid call was made after the failure.

## Official regulatory status

**APPROVAL RECORD MISSING.** `assets/local/regulatory/reviews/` is absent. Read-only inventory of the identity-verified local application database found **0 official-source version approvals**. `scripts/verify_reference_proposals.py` confirmed proposed-source integrity, not legal approval:

- Proposal digest: `832f42eafdc27a1e7847a8acf21c4b0615c8ca129f3117df969ec116fefc84c1`.
- Complete proposed 31 CFR 1020.210 / 1020.320 scope remains historical **2026-11-02**, US / us_bank / English. No current source substituted.
- FinCEN FAQ historical validity remains unverified and excluded from publication.
- No accepted independent relevance labels found; independent Precision@5/Recall@5/MRR remain **not measured**.
- Official sources approved/published by this task: **0**. No synthetic approval fixture authorizes official guidance.

Required reviewer action remains the exact hash/scope/authority/publication/AI-grounding record and accepted independent evaluation labels described in `PHASE3_4_SOURCE_APPROVAL_CHECKLIST.md`. Keep official grounding disabled until the actual record passes governance validation.

## Verification commands and measured results

Reruns overlap and must not be summed as independent acceptance.

| Command / environment | Actual result |
| --- | --- |
| `python scripts/run_g5_3_tests.py` — earlier complete binding/API set, real Linux/PostgreSQL | **16 passed**, before the additive atomic-start and migration-observation tests. |
| Same command — expanded final set | **17 passed, 0 failed, 1 setup error**. Setup of `test_concurrent_requests_create_one_job_and_binding` received parent status `pending / processing_unavailable`; no acceptance assertion ran. Earlier runs at that fixture raised `ClockUnavailable`. Exact cause of the final worker error is unconfirmed. |
| `python scripts/run_g5_3_tests.py --regression` | **125 passed, 3 failed, 1 skipped**. Two direct `ClockUnavailable` failures; one parent worker returned pending instead of succeeded in the assignment-revocation fixture. |
| `python scripts/run_g5_3_tests.py --security` | **52 passed**, including controlled expiry/clock floor, revoked/stale snapshots, tampered financial claims, process-boundary checks and offline Claude contract tests. |
| `python -m pytest backend/tests/test_claude_contract.py backend/tests/test_claude_provider.py -q -p no:cacheprovider` | **29 passed**, no external requests; includes bounded HTTP-error transport diagnostics. |
| `npm.cmd test` | **149 passed**. The Claude rendering fixture is an explicitly mocked contract test, not genuine live inference. |
| `npm.cmd run build`, `npm.cmd run lint` | Passed. Changed-file formatting and Python Ruff checks passed. |
| `python scripts/run_ml_verification.py --check tests` | **178 passed**, pinned Linux runtime, network disabled. |
| Same runner `--check scoring`, `--check policy`, `--check shap` | **4,000 RF / 12,000 routes / 4,000 SHAP**, zero mismatches. Maximum RF error 0; maximum SHAP reconstruction residual `3.1086244689504383e-15`. Missing income 87 and observed-zero income 22 remain distinct. |
| `python scripts/check_publication.py` | Passed source/ignore-boundary check; private artifacts and `.env` excluded. |

Additional observed test failures retained for transparency:

- Initial wider regression: 91 passed / 3 failed / 1 skipped. A provider-child test used an inconsistent candidate schema expectation; the test runner now mounts the same candidate release identity/schema into parent and child processes. Other failures included clock denials. This was a harness compatibility correction, not a permission bypass.
- A newly added API test initially tried to JSON-serialize a Pydantic object; corrected with `model_dump(mode="json")`.
- The migration-observation test initially retained a database read transaction across Alembic's independent migration connection; corrected to observe each committed migration from a fresh connection. No migration implementation change was required.
- Expanded focused runs also recorded 15 passed / 1 failed / 1 setup error and 16 passed / 1 failed / 1 setup error while those two new test defects were corrected. A later 17-pass run does not erase the continuing setup error.
- First G5.3 Chromium run: **5 passed / 1 failed** (history refresh reached HTTP 429). Second: **4 passed / 2 failed** (one-action and history recovery; sanitized traces contain HTTP 429). Rate/capacity denials must not be interpreted as source revocation.
- The new atomic-start UI originally remounted the findings pane, repeating capabilities/history reads. It now derives the selected child run without remounting. Browser fixture recovery honors actual bounded `Retry-After`, leaving server limits unchanged.
- **Final Chromium rerun: 3 passed / 3 failed.** The atomic one-action workflow, wrong-analyst isolation and queued source-revocation checks passed. History/logout, partial-evidence and controlled-clock tests stopped before their intended assertions. All three captured final screens show `Request limit reached`; do not attribute those failures to clock regression or count the intended assertions as passed. Protected-read backpressure/recovery remains an application integration blocker. Earlier successful assertions remain historical evidence, not a substitute for final acceptance.
- Final provider-specific history-label change passed ESLint/Prettier checks. The preceding full React run had 149 passing tests and a successful build. A further full test/build command after the label change was **not executed**: automatic approval review failed because its usage limit was reached, explicitly without a safety determination. No approval check was bypassed. Full final-source verification therefore remains incomplete.
- Initial sandboxed frontend test/build could not resolve ancestor directories; the approved local verification rerun succeeded outside that filesystem restriction. No security policy or shell execution policy was changed.

### Clock and runner limitations

Read-only host diagnostics found Windows Time service **not started (`0x80070426`)**, and Docker kernel `6.6.87.2-microsoft-standard-WSL2`. This is not an independently clock-stable Linux host. It does not establish the precise cause of every worker failure. No host clocks/settings, expiration thresholds, token epochs or source/numeric checks were changed. Controlled clock-test success does not prove operational clock stability.

## Runtime and remaining gates

The isolated local app was reloaded with compatible additive routes. Frontend `http://127.0.0.1:5173`; backend `http://127.0.0.1:8010`. Database schema remains 0019; 2,003 stored cases and assessments were retained. Assessment/import/packet/draft workers and dispatcher were running/idle when checked. Live provider remains off, simulation is explicit, official approval count is zero. No original demo modification or deployment occurred.

The local helper reports `env_unchanged:false` against its historical startup baseline; that is not evidence of a change by this task. This task did not write `.env` and does not claim that the historical baseline comparison passed.

Next executable work:

1. Investigate the HTTP 400 using the newly bounded diagnostic path under a separately deliberate, current-authority attempt; do not retry automatically or mark compatibility verified. Genuine successful model/schema/evidence verification and operating approval are still required before analyst activation.
2. Diagnose the reproducible HTTP 429 browser interruptions and bounded protected-read recovery. Establish a clock-stable runner and diagnose the remaining `processing_unavailable` fixtures, then rerun incomplete browser/backend acceptance. Do not increase rate limits or bypass fail-closed guards to obtain a passing report.
3. Review/apply candidate 0020/0021 through the existing isolated migration/release procedure before using durable grounded drafts in a running application. No live migration was authorized here.
4. Obtain actual qualified source approvals and accepted independent labels. Only then publish and validate official RAG. Evidence-only Claude must continue to remain independent of this gate.

No commit, push, provider auto-activation, regulatory publication, model retraining or automatic case action was performed.
