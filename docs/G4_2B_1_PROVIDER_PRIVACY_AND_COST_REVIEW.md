# G4.2B.1 — Public-document, privacy and cost review

**No direct Luminal request was made in this task.** Public-document research used indexed official pages and the exact documents already archived in G4.2B. No provider GET/POST, authentication, account/balance query, `/models`, token verification or inference probe was executed. An indexed listing cannot prove authenticated availability or current account billing terms.

## Sources and supported claims

Research date: **2026-11-16, America/New_York** (session date; not a clock-stability attestation). Earlier exact HTML retrievals were 2026-11-16 at approximately 21:03 UTC. Retained source snapshots are identified by `runtime/g4-2b/current.json` → `public-source-review/manifest.json`; this task did not refresh them through provider HTTP.

| Official source / version | Supported claim | Unverified assumption / human action |
| --- | --- | --- |
| [Pricing](https://www.luminal.com/pricing), indexed listing; previously archived November 16 | Candidate model listed; $0.1425/M input, $0.0029/M cached input, $0.5700/M output including reasoning. Text responses billed on completion. Published defaults: 60 requests/minute, 1M tokens/minute, burst 10/second. | Index reports an earlier crawl; current contractual prices, taxes, fees, tokenizer and complete billed usage are not independently confirmed. Freeze reviewed rates before approval. |
| [Terms](https://dash.luminal.com/terms), effective October 21, 2026; prior archive | Describes OpenAI-style chat-completions compatibility and provider-controlled backup routing. | Does not establish exact strict `json_schema` dialect, identity aliases, usage fields or support on this model. No API probe is authorized. |
| [Privacy](https://dash.luminal.com/privacy), effective October 7, 2026; prior archive | Describes 7-day content samples/failed-text retention, up to 90 days for flagged conversations, and longer-lived account safety findings. Luminal states it does not train on inputs; downstream processing differs. Backup providers include DeepSeek, Fireworks and Z.AI. The policy says DeepSeek may train on inputs and stores data in China. | Human review must accept/reject retention exceptions, recipients, training use and geography. A fixed hostname does not constrain internal routing; obtain contractual/technical restrictions if required. |
| Strict structured-output documentation | No adequate official field-level evidence located in indexed research. | **Unverified**, not proven unsupported. Keep strict schema; a separately authorized probe may establish compatibility. No free-text downgrade. |

Archive HTML identities, for reviewer verification only:

- Pricing: `4c4082bfd72fa4ba06b647da517f1df71ff05de38868f33b913594c9ec001b69`.
- Terms: `0fa6f6c4e8434988546f12f47e847a64ff63d35f3ddf88c3e2582fe2715e66b6`.
- Privacy: `ceefc6b9c408c8da9ed2963d6fbc855800a6413dbc5b5e28a49e8c29728328bc`.

## Conservative application budget

| Item | Prepared policy |
| --- | --- |
| Task ambiguity | Use **$1.00**, the stricter repeated Section 5/8 ceiling, not the objective's $10. |
| Padded rates | 2× indexed prices: $0.285/M input; $1.14/M output. These are proposed reservation rates, not approved vendor tariffs. |
| Reservation arithmetic | `(maximum input + maximum output tokens) × $1.14 / 1,000,000`; no cache discount or early release. Total **$0.06945792** across A/B/C. |
| Application ceiling | Existing durable attempt ledger, approval-wide advisory lock, **maximum 3 reservations**, cumulative conservative spend **≤min(configured limit, $1.00)**. No schema migration/new integration. |
| Paid retries | Live configurations with `max_attempts != 1` rejected before transport, including rate-limit retries. Error/timeout/unknown delivery retains the entire reservation and consumes an attempt. |
| Disable | New `INVESTIGATION_PROVIDER_CALL_LIMIT` defaults to **0**; external flag, approval, contract and key checks remain required. Existing `.env` unchanged. |

Implementation: `backend/app/services/provider_budget.py`, existing `InvestigationDraftService.prepare`, `LuminalProvider.authorize` and Linux runner. Limits apply to the approved controlled-worker path and immutable ledger; direct arbitrary Python/key use is outside that enforcement boundary and is not an approved probe path. No new live probe executor is provided.

The ledger counts conservative reservations, including prepared-but-undelivered attempts, so fewer than three actual calls may be possible. Changing approval IDs to reset counters is not an authorized continuation. Lower reported usage does not release unknown/ambiguous reservations. Provider-reported counts and configured-rate estimates remain separate from vendor-verified charges.

## Required stop conditions

- **Reliable provider invoice/token bound is not established.** Byte length is only local admission; hidden reasoning/accounting behavior and current pricing remain unverified. A 2× margin cannot prove those assumptions. No live GO until adequate evidence resolves them.
- Stop on unavailable/changed/ambiguous pricing, unapproved recipient/fallback, wrong model, unsupported schema, missing usage, excess usage, clock uncertainty, exhausted reservation/call allowance, source revocation or withdrawal of any approval.
- Do not infer a $1 provider invoice guarantee. No provider-enforced account spending cap was checked or configured. Explicit acknowledgement of residual billing uncertainty is required separately.
- No top-up, purchase, credential change, data transfer, legal/privacy acceptance or model-quality certification is performed here.
