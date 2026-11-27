# Luminal prepaid balance policy

> **Superseded for new probe preparation:** On November 18, 2026, the owner withdrew the $200 floor. The default `bounded_probe_v3` policy has no balance-floor requirement. The historical v2 policy and this document's original evidence are retained for audit. See [activation status](LUMINAL_RAG_ACTIVATION_STATUS.md). Live dispatch remains blocked for independent compatibility-bootstrap and billable-token-bound reasons.

**Policy implemented; live inference remains BLOCKED. The $200 account floor is not guaranteed.**

### Direct adapter review: November 18, 2026

- The existing server-side credential setting now also accepts `LLM_API_KEY`; `INVESTIGATION_PROVIDER_API_KEY` takes precedence when both are set. Neither alias enables external execution. The local offline worker remains intentionally isolated from provider credentials.
- A read-only configuration check found a provider credential configured, external execution disabled, no configured machine approval or terms binding, no contract verification and a zero live-call allowance. No provider requests were sent during this review.
- The existing adapter sends strict JSON-schema chat-completion requests and independently verifies returned findings. Actual authentication, model identity, schema compatibility, usage and financial-claim verification remain untested against Luminal.
- [Luminal pricing](https://www.luminal.com/pricing) describes a shared prepaid balance and charges for reasoning tokens. It does not establish that the approved request's output cap bounds all billable tokens or that an account-wide $200 floor can be atomically enforced. The previous balance lookup did not establish explicit USD units; no current balance is claimed.
- Offline adapter, alias, probe and budget tests: **55 passed, 3 skipped, 20 deselected**. These are not live-provider compatibility results. Live inference requests this review: **0**.

Local configuration rechecked November 17, 2026: the expected server-side key binding is present in `.env` (value not disclosed). External execution and contract verification remain false, and the configured live call limit is zero. The isolated local application deliberately does not mount the provider key and runs offline simulation only. No provider requests were made for this status check; these observations do not verify authenticated model compatibility, current balance or billing enforcement. The historical checks below remain unchanged.

### Subsequent activation request: November 17, 2026

- The owner requested live activation. The existing prepaid-floor and synthetic-data restrictions remain applicable; activation intent does not verify API compatibility or billing controls.
- Read-only configuration preflight confirmed key presence, no configured machine approval/terms binding, no compatibility verification, zero allowed live calls and external execution disabled. No secret values were emitted.
- Rechecked [official pricing](https://www.luminal.com/pricing): the candidate model remains listed, the balance is shared between services, and completed text responses are charged from reported usage. Those public statements do not establish account-specific spending controls or a complete billable-token bound.
- Made **one additional authenticated balance metadata GET**, with the existing fixed-host client, no retries and no investigation payload. The response failed the explicit-USD schema check (`balance_units_unverified`); no recognized balance field types were found. No raw response or credentials were logged. This is additional to the two historical reads below, not an inference request or verified account balance.
- **Live inference requests in this activation attempt: 0.** Provider flags, original approval package and spending guards remain unchanged. Activation is blocked on documented balance units/settlement, enforceable account-wide spending protection, billable-token bounds and the controlled compatibility bootstrap. Do not set `contract_verified=true` without actual verification or change the financial policy to a historical fixture mode.

## 1. Financial authorization

| Item | Current boundary |
| --- | --- |
| Owner-reported prepaid balance | **$997**, unverified; not treated as current available funds |
| Minimum balance | **$200**, configurable upward; lower runtime values rejected |
| Indicative additional spending ceiling | **$797**, configurable downward; not a verified available budget |
| Default safety buffer | $1 above the floor; configurable independently |
| Inference scope | Existing exact synthetic probes only; three attempts maximum, one per probe; no paid retries |
| Activation | Disabled; configured call allowance zero; contract verification false |

- Review date: November 16, 2026, America/New_York, session date; not a clock attestation.
- New [versioned financial authorization](../backend/app/policies/luminal_financial_authorization_v2.json): canonical SHA-256 `325d4dc7770f35606023fbd4c3a0738ee700ee1ad79b6499f09393ec4afdbe18`. Packaged with the backend; verified against the expected digest before using its scope.
- This changes **financial scope only**. It does not approve new payloads, ordinary analyst live generation, unlimited attempts, customer data, providers, legal sources or broader privacy terms.
- All seven files in the original three-probe proposal match their prior protected baseline. Original package digest remains `338703d5b331f6d98e84e58be4977adb49cf80a269af2fb49cacbe74b0d99183`.
- Real runtime `Settings` accepts only `prepaid_floor_v2`. The $1 legacy branch is retained for historical offline fixtures; runtime configuration cannot select it.

## 2. Current balance verification

| Measurement | Actual result |
| --- | --- |
| Official balance endpoint | [Pricing](https://www.luminal.com/pricing) documents `GET /v1/balance` on the text/image host and a shared prepaid balance |
| Authenticated metadata reads | **2** GET attempts to fixed `https://flash.luminal.cloud/v1/balance`, using the existing credential in memory |
| Response | HTTP 200 JSON; no supported explicit USD balance shape was established; schema/units rejected rather than inferred |
| Fresh verified USD balance | **Unavailable**; $997 was not promoted to verified funds |
| Inference requests | **0**; no synthetic investigation payload transmitted |
| Actual inference usage/charge | No inference dispatched; no provider usage receipt or invoice reconciliation available |

- Second GET was a bounded schema investigation, not an automatic retry. Only allowlisted field names/types were inspected; no recognized balance fields were found. Raw bodies, account identifiers and credential values were not stored or printed. No additional requests were made to guess endpoints or units.
- A JSON response does not certify the credential/account identity, billing freshness, settlement or spendable balance. No assumption of dollars, cents or credits was made.
- Public pricing describes text charges at response completion and shared text/image credit. It does not establish an account-wide atomic floor, in-flight text reservation semantics, complete usage reconciliation contract or a verified per-key hard monetary cap. These remain **unverified**, not proven unavailable. [Official terms](https://dash.luminal.com/terms)

## 3. Enforcement and accounting

| Control | Implementation / limit |
| --- | --- |
| Future admission | Existing [adapter](../backend/app/services/luminal_provider.py) and [durable draft service](../backend/app/services/investigation_drafts.py) reject prepaid dispatch before transport/reservation. Setting existing activation flags alone cannot bypass the new financial denial. |
| Configured ceiling | [Budget service](../backend/app/services/provider_budget.py): minimum of configured allowance, authorization ceiling and reported starting balance minus configured floor. This is an indicative authorization cap, not live balance verification. |
| Reservations | Existing immutable `DraftAttempt` ledger retained. [Finance projections](../backend/app/services/provider_finance.py) sum all local Luminal grants conservatively; unknown/prepared outcomes retain full reservations. No release based on an estimated receipt. |
| Reconciliation | Existing immutable receipts supply token-based configured-rate **estimates**, shown separately from retained reservations. Settled vendor charges and outside-account usage remain unknown; no fabricated reconciliation or refunds. |
| Projections | `reported balance - floor - buffer - retained reservations`; stale, future-dated, epoch-invalid, missing or malformed observations provide no usable headroom. Default freshness limit 15 seconds. Projections never authorize dispatch. |
| Outside usage | Local ledger has no complete account-wide attribution, external-client reservations or settlement feed. Multiple local grants are counted, but other clients/account keys cannot be locked by TrueFlag. **Paid admission therefore remains closed.** |
| Transport | New [read-only balance client](../backend/app/services/luminal_balance.py): fixed HTTPS host, no redirects/proxies/retries, 16 KiB response limit, explicit USD normalization, duplicate-field rejection, bounded I/O and elapsed-time checks. |

- The original 27-feature contract, RF, policy thresholds and SHAP are unchanged. No new scoring pipeline, regulatory publication, case decision, dismissal or SAR action.
- No `contract_verified=true` bootstrap workaround. The controlled first-probe bootstrap remains unfinished; this financial change does not establish compatibility, source authority or stable clock acceptance.
- No application mechanism can guarantee the entire shared account stays above $200 while outside usage remains uncontrolled. Current protection is to **send no paid requests** under the unresolved conditions.

## 4. Administration and configuration

- New **Provider Usage** navigation item at `#/admin/provider-usage`, visible to administrators only. Existing React layout, colors, navigation and session controls reused.
- `GET /api/v1/internal/provider-usage`: admin-only local ledger totals, estimates, balance observation, indicative ceiling, protected floor, unknown headroom and explicit blocked reasons. No provider call on page load/polling.
- `POST /api/v1/internal/provider-usage/balance-refresh`: explicit read-only provider lookup, disabled by default. Requires current admin, financial authorization and expected server key binding; rechecks role and clock epoch before publication. Serialized account-wide refresh admission; maximum one committed refresh per 60 seconds; shared authenticated API rate limits retained.
- Financial read/lookup events use the existing append-protected `evidence.investigation.provider.*` audit namespace. No migration or new accounting tables.
- UI clears financial state on denial, unmount/logout and access-verification changes. Failed refreshes show a sanitized error; arbitrary provider diagnostics are not rendered. No activation/generation control is exposed.

| Server setting | Default / rule |
| --- | --- |
| `INVESTIGATION_PROVIDER_FINANCIAL_POLICY` | `prepaid_floor_v2` only |
| `INVESTIGATION_PROVIDER_FINANCIAL_AUTHORIZATION_SHA256` | Exact v2 record digest |
| `INVESTIGATION_PROVIDER_MINIMUM_BALANCE_USD` | 200; values below 200 rejected |
| `INVESTIGATION_PROVIDER_BALANCE_BUFFER_USD` | 1 |
| `INVESTIGATION_PROVIDER_SPEND_LIMIT_USD` | 797; zero/lower values remain restrictive |
| `INVESTIGATION_PROVIDER_BALANCE_MAX_AGE_SECONDS` | 15, bounded 1-60 |
| `INVESTIGATION_PROVIDER_BALANCE_LOOKUP_ENABLED` | false |

Existing expected key binding remains absent in running services; the stored legacy key was used only in memory for the authorized read-only checks. `.env` was not overwritten. Existing per-request configuration/output cost limits and the maximum three-attempt scope were not enlarged.

## 5. Verification

| Final selected suite | Passed / Failed / Skipped |
| --- | --- |
| Linux/PostgreSQL financial policy, admin API, balance contracts and existing probe/security tests | **104 / 0 / 0** |
| Existing provider/draft/evidence/human-casework integration | **73 / 0 / 0** |
| Existing coordinator/snapshot/clock/release security | **112 / 0 / 0** |
| React | **118 / 0 / 0** |
| Real Chromium admin/mobile/logout/analyst-denial/role-revocation | **3 / 0 / 0** |
| Pinned Linux ML | **178 / 0 / 0** |

- Frozen parity: RF 4,000, max error 0; policy 12,000, zero route/trace/count mismatches; SHAP 4,000, zero mismatches, max reconstruction residual `3.1086244689504383e-15` under `1e-6`. Missing-income 87 and observed-zero 22 preserved.
- Verified new policy denial before HTTP, malformed/ambiguous amounts, disabled/missing credentials, error/timeout no-retry behavior, concurrent metadata reads, immutable audit events, role revocation during lookup, failed audit rollback, clock-epoch invalidation, and accounting across grants with an unknown retained attempt. All provider success in automated tests is mocked; it is not a verified account balance.
- New tests initially assumed a new parent/attempt for an already completed identical intent, used the wrong browser command filename, and attempted an illegal direct epoch update. Corrected to respect existing deduplication, the established fixture protocol and the existing controlled-clock simulator. No production idempotency, epoch guard or timeout was relaxed. One new test-file formatting check was corrected.
- Ruff, ESLint, Prettier and TypeScript/Vite build passed. These are focused local checks, not a full backend-suite run, security certification or clock-environment remediation.

Reproduction, from repository root except npm commands from `frontend`:

```powershell
.venv\Scripts\python.exe runtime/g4-prepaid/run.py --mode unit --label prepaid-release-acceptance
.venv\Scripts\python.exe runtime/g4-prepaid/run.py --mode materialize --label prepaid-existing-provider-and-casework
.venv\Scripts\python.exe runtime/g4-prepaid/run.py --mode regression --label prepaid-snapshot-security
.venv\Scripts\python.exe runtime/g4-prepaid/browser.py --suite probe
.venv\Scripts\python.exe runtime/g4-prepaid/run_ml.py --check tests
.venv\Scripts\python.exe runtime/g4-prepaid/run_ml.py --check scoring
.venv\Scripts\python.exe runtime/g4-prepaid/run_ml.py --check policy
.venv\Scripts\python.exe runtime/g4-prepaid/run_ml.py --check shap
.venv\Scripts\ruff.exe check backend scripts
.venv\Scripts\ruff.exe format --check backend scripts
# frontend:
npm.cmd test -- --reporter=dot
npm.cmd run lint
npm.cmd run format:check
npm.cmd run build
```

Labels create exclusive artifacts and need replacement for a repeat run. Protected evidence is identified by `runtime/g4-prepaid/current.json`; the one-shot actual balance readers are not automated acceptance commands and were executed only twice total.

## 6. Activation decision and remaining prerequisites

**Live inference cannot safely begin.** Required before another paid attempt:

1. Establish the authenticated balance response's documented USD units, account attribution, freshness and complete settled/pending billing semantics.
2. Establish a provider-enforced account-wide floor/atomic reservation mechanism covering all clients, or another demonstrably enforceable boundary. A fresh read alone has a time-of-check/time-of-use race and is insufficient.
3. Verify maximum billable prompt/reasoning/output cost for the unchanged approved request; pricing margin is not a guarantee.
4. Complete the scoped compatibility bootstrap through the existing immutable ledger, current case/source/snapshot authority and clock-health checks; retain exact-payload approval and abort controls. Do not activate the normal investigator or launch batches.

No original demo writes, live migrations, role/credential changes, `.env` edits, commits, pushes or deployment. Financial authorization is recorded; operational activation remains disabled.

Final preservation: all 466 baseline files compared; exactly 12 intended existing paths changed (financial/provider integration, admin navigation, packaging/test fixture and ignored release metadata). Unrelated files, original seven-file probe package, frozen assets and backups unchanged. Retained G1/G2 cohorts unchanged; 111 foreign keys checked, zero orphans/invalid constraints/indexes. Temporary test schemas cleaned and only the owned rehearsal database stopped; original demo stayed stopped, so its current live schema was not queried. Known-key-byte scan: zero findings across 4 bundles, 412 public source/report files, 113 task diagnostic files and 269 indexed blobs; not a full history/unknown-secret certification. Publication check passed for 437 candidates; normal Git whitespace check passed.
