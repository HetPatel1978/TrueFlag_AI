# G4.2B — Provider approval and cost-control gate

## Authorization decision

**NOT AUTHORIZED.** An existing key and requested preparation are not authorization for authenticated connectivity probes, paid calls or external evidence transfer. No current grant supplies an approved owner, recipients, dataset/input hashes, expiry, call ceiling, spend or privacy decision. Do not change `.env`, enable external execution, set contract verification or repurpose a mock approval ID.

## Public-source review dossier

Unauthenticated public HTML snapshots retained privately under `runtime/g4-2b/<run>/public-source-review/`; the exact directory is in `runtime/g4-2b/current.json`. All three returned HTTP 200. Host retrieval timestamps (2026-11-16 approximately 21:03 UTC) are recorded as **not release-clock-attested**. Hashes bind retrieved bytes; they do not constitute approval or legal certification.

| Source | Displayed version | Exact HTML SHA-256 |
| --- | --- | --- |
| [Pricing](https://www.luminal.com/pricing) | Retrieved current listing; no effective date asserted | `4c4082bfd72fa4ba06b647da517f1df71ff05de38868f33b913594c9ec001b69` |
| [Terms](https://dash.luminal.com/terms) | Effective October 21, 2026 | `0fa6f6c4e8434988546f12f47e847a64ff63d35f3ddf88c3e2582fe2715e66b6` |
| [Privacy](https://dash.luminal.com/privacy) | Effective October 7, 2026 | `ceefc6b9c408c8da9ed2963d6fbc855800a6413dbc5b5e28a49e8c29728328bc` |

Material facts for reviewer consideration: the policy describes seven-day retention of sampled text requests/outputs and failed text requests, up to 90 days for flagged conversations, and account-lifetime retention of safety findings. It lists backup providers DeepSeek, Fireworks and Z.AI; it says DeepSeek may train on inputs and stores data in China. Processing geography and fallback therefore cannot be inferred from the fixed Luminal hostname. These are provider-published statements requiring qualified review, not our certification of downstream practices. [Privacy §§3–6](https://dash.luminal.com/privacy)

## Required owner/reviewer actions

| Gate | Current state / required decision |
| --- | --- |
| Provider/model/host | Approve the exact candidate, revision/alias policy and fixed network destination; current price-list presence is insufficient. |
| Transmission scope | Approve exact synthetic minimized input hashes and metadata; no real customer data, secrets, analyst notes or original demo records. |
| Privacy, retention and training | Review archived source versions and explicitly accept/reject the documented exceptions. Obtain any required contractual protections/deletion terms. |
| Fallback/subprocessors/regions | Decide permitted recipients and geographies; verify provider-side restriction/attestation where needed. Client no-redirect policy cannot control internal vendor routing. |
| Credentials | Arrange approved, memory-only/server-secret binding from the existing key to the expected setting in an isolated Linux worker. No key validity claim from presence; no browser exposure. |
| Scope/expiry | Record approval owner/ID, purpose, expiry and current clock-health requirement. Configuration flags are not a signed, expiring grant. |
| Call and token ceilings | Explicit limits for probe versus benchmark, all attempts including errors/rate limits/unknown delivery, concurrency one, input/output/reasoning tokens and bytes. No approved numbers currently. |
| Spend | Approve conservative reservation ceiling and frozen rates; no automatic purchase, top-up or balance query. |
| Dataset and independence | Approve frozen 18/18 split, case/input hashes, reviewer roster, qualifications/conflicts, metric thresholds and critical-failure rules before results. |
| Emergency disable | Approve stopping/fencing the isolated provider worker and withdrawing authorization; retain attempts/audits and unresolved reservations. Key revocation is an owner action, not performed here. |

## Existing controls versus missing controls

| Existing implementation | Limit / unresolved requirement |
| --- | --- |
| `LuminalProvider.authorize` checks enable flag, exact approval/digest/rates, secret, contract flag and spend. | These technical flags do not verify a human-signed scope/expiry or downstream privacy restrictions. No fallback-route attestation is parsed. |
| Durable attempt/token reservations and approval-wide conservative spend ledger under PostgreSQL advisory lock. | No explicit approval-wide **request-count ceiling** or approval-expiry field is implemented. Worker `--max-jobs` and per-run `max_attempts` are not equivalent. A separately reviewed bound is required before live execution. |
| Fixed HTTPS host/model, TLS verification, no environment proxy/redirects/tools, bounded request/response/time and Linux child process. | Exact hosted model revision, strict-schema dialect, reasoning-token limits and returned usage remain unverified live. |
| No automatic paid retry after ambiguous dispatch; rate retries are bounded by existing config. | Future approved probes should use one attempt; every attempted request must consume its call allowance and retain uncertain spend until reconciled. |
| Source/permission/clock checks before dispatch/publication and independent financial/reference validation. | Independently stable runner acceptance remains absent; unresolved clock uncertainty must block execution. |

## Cost worksheet — illustrative, never approved or incurred

[Public pricing](https://www.luminal.com/pricing) lists $0.1425/M input, $0.0029/M cached input and $0.5700/M output including reasoning. Current configured rates/spend remain **zero**. Proposed calculations ignore cache discounts and are not vendor-billing measurements.

| Default candidate ceilings | Arithmetic using listed rates |
| --- | ---: |
| 32,768 input + 4,096 output | `$0.00700416` token-ceiling estimate, conditional on complete billed usage fitting those caps |
| Existing conservative reservation, 36,864 × max rate / 1M | `$0.02101248` per attempt |
| Example: one probe + at most 32 eligible generation cases, 33 identical reservations | `$0.69341184` |

The benchmark includes **four lifecycle security cases** that must demonstrate denial/no egress; these are not requests to send revoked historical packets. The 33-attempt example is a planning ceiling, not authorization or a guaranteed final charge. Any retry, parameter/rate change, unverified reasoning accounting or extra diagnostic call changes the budget and requires explicit review. No target spend or call limit was invented as an approved value.

The initial probe must have its own narrowly documented authorization without falsely marking live compatibility verified. The current all-or-nothing contract flag and missing global call/expiry grant make the activation procedure incomplete; do not bypass them to manufacture a successful probe.
