# G4.2B.2 - first live probe prerequisite result

**Decision: BLOCKED at the billing/token-bound prerequisite.**
**Live Luminal inference requests executed: 0.**

## 1. Authorization validation

- Review date: November 16, 2026, America/New_York, session date; not clock-health attestation.
- Reused the owner's explicit authorization and recorded privacy acceptance. No repeated approval request; no material scope change proposed.
- Current instruction permits **Probe A only, at most one attempt in this task**. Package maximum remains three attempts/$1 application ceiling, no paid retries. B/C and continuous analyst generation are not authorized by this execution step.
- Package canonical digest verified: `338703d5b331f6d98e84e58be4977adb49cf80a269af2fb49cacbe74b0d99183`.
- All three raw request hashes and source oracles reverified; current adapter reconstructs identical bytes. Probe A SHA-256: `135f684427912c0231d0a97f09f7773ff73882e033aed5045fd59fd350c886f6`.
- Exact provider/model/destination remain Luminal / `deepseek-ai/DeepSeek-V4.1-Flash` / `https://flash.luminal.cloud/v1/chat/completions`. Synthetic-only constraints remain intact.
- Approval validity is the current explicit, conditional task; no indefinite machine grant or invented expiry was created. Historical proposal remains pending as an artifact; subsequent owner decisions are recorded in [the activation report](G4_LIVE_LUMINAL_ACTIVATION.md), not fabricated edits to that proposal.
- Existing [abort procedure](G4_2B_1_APPROVAL_CHECKLIST.md#immediate-abort-and-uncertain-outcomes) remains applicable: withdraw grant, stop dispatch and isolated provider child, retain unknown reservations, no automatic restart/retry. There is no outstanding request to cancel.

## 2. Credential and bootstrap status

| Item | Verified result |
| --- | --- |
| Stored credential | `LLM_API_KEY` present/nonempty; no value or derived fingerprint emitted |
| Expected binding | `INVESTIGATION_PROVIDER_API_KEY` absent; supported explicit Settings binding validated in memory only |
| Provider process | No investigator provider worker started or provisioned with the credential; actual worker receipt not verified |
| Activation | External flag false; call allowance zero; `.env` unchanged |
| Compatibility bootstrap | **Not implemented in this task.** Billing cannot satisfy the mandatory dispatch prerequisite; the existing contract gate was left unchanged rather than introducing an unverified activation exception. This remains unfinished work. |
| Immutable accounting | No new live attempt, reservation, receipt or compatibility-success record created; no ledger reset or replacement accounting path |

The existing [adapter](../backend/app/services/luminal_provider.py), [Linux runner](../backend/app/services/live_provider_runner.py) and [draft ledger](../backend/app/services/investigation_drafts.py) were inspected. No `contract_verified=true`, transport bypass, ordinary analyst activation or second provider pipeline was introduced.

## 3. Billing evidence and mandatory stop

Public official documents were reviewed without authentication, provider API calls or synthetic-data transfer. Retrieval date: November 16, 2026. Indexed public text is not account-specific billing attestation or a fresh raw-HTML hash comparison.

| Question | Evidence / exact gap |
| --- | --- |
| Current published prices | [Pricing](https://www.luminal.com/pricing): input $0.1425/M, cached input $0.0029/M, output $0.5700/M including reasoning. Listing matches the reviewed proposal. |
| Request token bound | Approved A sends `max_tokens: 512`, input admission 8192. No reviewed official field-level contract establishes that **this exact field** limits all billed reasoning plus visible output, or supplies a reliable upper bound for billed prompt/template tokens. Byte admission is not verified tokenizer accounting. |
| Usage | Pricing identifies response `usage` counts and `usage.prompt_tokens_details.cached_tokens`; the full actual envelope and reasoning-token accounting remain unverified. Post-response usage validation cannot prevent a charge already incurred. |
| Rate limits | Published defaults: 60 RPM, 1M TPM, burst 10/s. These are not monetary limits. |
| Provider monetary cap | No verified per-key/request hard spending cap covering in-flight charges found in reviewed public documents. Account settings were not queried; existence is **unverified**, not claimed unavailable. |
| Proposed reservations | A $0.00992256; package $0.06945792 with 2x pricing margin. Conditional estimates only; not a demonstrated maximum possible charge. |

- [Terms](https://dash.luminal.com/terms), effective October 21, describe format compatibility, mutable dashboard pricing and taxes. Format compatibility alone does not prove token-cap semantics. Dashboard documentation access redirected to sign-in; no login/account request was attempted.
- [Privacy](https://dash.luminal.com/privacy), effective October 7, remains consistent with the disclosed conditions accepted for the exact synthetic probes. No broader privacy approval inferred.
- **Stop reason:** the maximum charge cannot currently be reliably bounded under the required exact payload. No unsupported assumption was used to spend against the approved ceiling.
- **Safe next action:** obtain authoritative Luminal confirmation for the unchanged A request: `max_tokens=512` caps all billable reasoning/output, bounded prompt/template accounting, applicable rates/fees and response usage semantics. Alternatively, establish a provider-enforced hard cap and review whether reservations/cost scope must change. No provider email, purchase or account modification was performed.
- Adding `max_completion_tokens`, changing caps/model/prompt/schema or raising reservations is not an approved workaround; material changes require a separately reviewed package.

## 4. Source and clock authority

- Reverified archived synthetic sources, source membership, provenance and independent financial checks. This establishes fixture correctness, **not current case authorization**.
- The approved artifacts came from disposable schemas; current case assignment, source/evidence revisions and snapshot authority were not established in this task. No original or isolated database was started/queried to reconstruct them after the billing stop.
- A future supported fixture must establish current authority and reproduce the exact wire hash. If rematerialization changes that hash, the old approval does not cover the replacement. No direct row insertion, forced identity substitution or fabricated source state was used.
- Existing durable floor/epoch guards and 900-second token expiry remain unchanged. No new current PostgreSQL/API/worker clock acceptance is claimed. The prior activation review's two healthy 60-second observations are historical evidence, not resolution of WSL2 instability.

## 5. Actual response and independent verification

| Field | Actual result |
| --- | --- |
| External inference attempts / responses | 0 / none |
| Authentication / model identity / strict-schema compatibility | Not tested against Luminal |
| Provider tokens / latency | Unmeasured; not reported as zero usage |
| Inference charge caused by this task | $0: no inference dispatched; provider invoice not queried |
| Independent model-output verification | Not applicable: no model output |
| Probe B | **NO-GO**; A not executed, prerequisites unresolved, no automatic continuation |

## 6. Verification performed

| Current-task checks | Passed / Failed / Skipped |
| --- | --- |
| Linux provider/transport, disable, retry-policy admission and budget-boundary contracts; HTTPX mocks, network disabled | 55 / 0 / 0 |
| React regression suite | 111 / 0 / 0 |
| Pinned Linux ML suite, network disabled/read-only assets | 178 / 0 / 0 |

- Frozen RF 4,000: zero mismatches/max error 0. Policy 12,000: zero route/trace/count differences. SHAP 4,000: zero mismatches, residual `3.1086244689504383e-15` under `1e-6`; missing-income 87 and zero-income 22 preserved.
- Ruff check and formatting passed, 243 files. No application/frontend source changes.
- Final preservation checks passed: all 456 baseline files and all seven approved package files unchanged, `.env` unchanged, Git whitespace check passed. Exact known-key-byte scan found zero matches in 4 frontend bundles, 402 public source/report files, 17 current diagnostics and 269 Git index blobs; unknown/encoded secrets and complete history are outside that scan. Publication check passed for 426 candidates.
- **Not rerun here:** PostgreSQL integration/concurrent-ledger/source-clock suites, Chromium, full backend suite and build. Stopped at the required billing blocker without starting acceptance databases or changing runtime behavior. Prior activation results (243 focused PostgreSQL, 8 Chromium) are not included in current-task counts or represented as bootstrap acceptance.

Commands from repository root, except React command from `frontend`:

```powershell
.venv\Scripts\python.exe runtime/g4-2b-2/preflight.py
.venv\Scripts\python.exe runtime/g4-2b-2/audit.py
.venv\Scripts\python.exe runtime/g4-2b-2/inspect_local.py
.venv\Scripts\python.exe runtime/g4-2b-2/run_offline.py --check provider
.venv\Scripts\python.exe runtime/g4-2b-2/run_offline.py --check tests
.venv\Scripts\python.exe runtime/g4-2b-2/run_offline.py --check scoring
.venv\Scripts\python.exe runtime/g4-2b-2/run_offline.py --check policy
.venv\Scripts\python.exe runtime/g4-2b-2/run_offline.py --check shap
.venv\Scripts\ruff.exe check backend scripts
.venv\Scripts\ruff.exe format --check backend scripts
# frontend:
npm.cmd test -- --reporter=dot
```

Protected reports: directory identified by `runtime/g4-2b-2/current.json`; one-shot preparation/check outputs require a new review directory for another run. Approved package files remain unchanged. Original demo, `.env`, frozen artifacts and unrelated work preserved. No commit, push, migration, deployment, regulatory publication or autonomous AML action.

**G4.2B.2 is blocked, not complete. Stop at the documented technical prerequisite; no live success, bootstrap readiness or permission to execute B/C is inferred.**
