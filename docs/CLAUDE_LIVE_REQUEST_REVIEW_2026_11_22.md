# Exact Claude request for owner review — 22 November 2026

**Current decision: APPROVED; single attempt consumed.** After preparation, the owner explicitly approved this exact request in the conversation. One live request returned HTTP 400; no independent output-verification gate passed. [Actual result and immutable ledger confirmation](CLAUDE_APPROVED_PROBE_RESULT_2026_11_22.md). The preparation details below describe the package as originally presented; their pending-state statements are historical. This approval does not enable analyst inference or approve regulatory sources.

## Review the complete request

- [Complete readable JSON request](../runtime/claude-demo-20261120/live_validation_request_review_20261122.json): model, system instructions, all synthetic observations, exact references, limitations and complete strict output schema. The user-message `content` is a JSON string, as actually submitted by the existing Messages adapter.
- [Exact 14,477-byte request body](../runtime/claude-demo-20261120/live_validation_payload_bfad88682342c1e5ea885b10f3c1ff6e78db5f2653849bd7501292621df17668.json): these original bytes define the approval scope. The readable copy is formatted differently; it is semantically identical and is not the byte-hash target.
- [Pending machine-readable owner approval record](../runtime/claude-demo-20261120/live_validation_owner_approval.json): ID **`claude-live-validation-review-2026-11-22-v1`**. `decision=pending`; reviewer, approval time and evidence are null. Nothing was signed or self-approved.
- [Read-only source verification receipt](../runtime/claude-demo-20261120/approval_provenance_20261122.json).

## Identified request and limits

| Item | Exact scope |
| --- | --- |
| Provider / method / endpoint | Anthropic; POST `https://api.anthropic.com/v1/messages` |
| Model | `claude-sonnet-5-5` |
| Request body SHA-256 | `bfad88682342c1e5ea885b10f3c1ff6e78db5f2653849bd7501292621df17668` |
| Template wire-schema SHA-256 | `eb6df4791f3d12ecb7d066ed7facf330e5c078a49b5140b86db9b9a914919e83` |
| Exact embedded output-schema SHA-256 | `8ff1f321fcb4cd5b8d8c7f740ff4a41add84f4e5b8eadf7d73478dc84e28b333` |
| Canonical minimized-input SHA-256 | `944999400800b4f9ee26aaa9a12f43291c696857a4c2855eca7a6f68f779f060` |
| Retained provider-terms snapshot SHA-256 | `09a6e98ace568b6414537edefaab32aafe7bbbb460f6378721fa8acb047d5252` |
| Attempts / automatic retries | Exactly **1** authorized external request; **0** automatic paid retries. Ambiguous outcomes must not be resent |
| Request / response body limits | 65,536 bytes each; prepared request is 14,477 bytes |
| Input / output / total token limits | 32,768 accepted/reported input tokens; 4,096 requested output tokens (`max_tokens`); 36,864 application token budget |
| Input-token qualification | No authenticated token-count call was made. The accepted-input threshold is not a proven provider billing cap; reservation conservatively accounts for the model's full configured context. Over-limit or missing usage fails safely and retains reservation |
| Execution deadline / concurrency | 20-second bounded existing provider subprocess; one outstanding paid attempt under the existing reservation lock |
| Thinking / effort | `between_tools` / `high` |
| Tools / streaming / redirects / prompt caching | None enabled |
| Per-attempt reservation / existing allowance | **$2.15 / $20.00**. Fresh read-only ledger: **7 prior attempts, $14.85 reserved**; projected cumulative reservation **$17.00** |
| Invoice qualification | Reservation and token-rate estimate are not a guaranteed final invoice. Unknown usage retains its full reservation |
| Broader activation | **Not authorized by this approval**. General analyst generation remains disabled pending the full verification gate |

The template schema and embedded schema intentionally have different hashes: the actual request constrains `packet_sha256` to this exact server-owned packet identity. Both were recomputed; original request and template hashes match the November 21 activation report. Rebuilding the request with the current adapter produces identical bytes.

## What leaves the application if subsequently approved

- One minimized fictional `g1_concentration` scenario: **12 transaction observations, 2 deterministic financial summaries and 17 opaque evidence-version references**.
- The 12 observations contain **4 credits totaling USD 4,000.00000000** and **8 debits totaling USD 6,020.00000000**. Gross observed total: **USD 10,020.00000000**, not a settled/net balance. These values were recomputed directly from the saved observations and agree with its financial summary.
- Concentration summary: 10 observations totaling USD 10,000; 2 totaling USD 20. Review the complete amounts, dates, references and calculation windows in the linked request.
- Explicit missing evidence: comparable expected activity, supporting documents, sampling metadata, selected assessment and settlement status. No conflicts are supplied. Human semantic review and synthetic/gross-observation limitations are included.
- **No RF/SHAP assessment or raw 27-feature predictors are included. No regulatory passages or approved regulatory claims are included.** This is an evidence-only compatibility request, not full AML-system or model-quality acceptance.

## Checks completed without provider access

- A PostgreSQL **read-only transaction** in the identity-verified isolated environment matched the saved request to the immutable stored packet and original probe case. Every linked source was classified synthetic; existing `verify_release` independently regenerated the source records from the stored generator configuration and verified their integrity.
- All 17 source references exist and remain actively linked; the original actor remains active. These observations are not a substitute for current server-side permission, source, revision, snapshot and clock checks immediately before any future dispatch or publication.
- The request contains no customer names, account identifiers, source document text or real customer records. This finding is grounded in exact regeneration of the synthetic source and byte-identical trusted minimization, rather than merely trusting a `synthetic` flag.
- Known nonempty credential values were compared locally against the request body, with no values, prefixes, suffixes, hashes or lengths disclosed. No credential was found in the JSON. The future HTTPS request necessarily authenticates using the existing server-side key in its header; the key is not part of this review payload or approval record.
- Initial generic credential-field matching incorrectly included public token-duration configuration; narrowed matching to actual credential fields. This was a scan correction, not a payload change.
- Existing offline exact-approval tests: **10 passed / 0 failed / 0 skipped**. Actual pending record is rejected by `approved_request`. No inference, credential validation or token-count HTTP request was made.

## Required next owner decision

After reviewing the complete linked request, the owner may explicitly approve **`claude-live-validation-review-2026-11-22-v1`**, binding all hashes and limits above. Only then may the pending record receive the actual recorded decision and its evidence. The record must not be silently changed to approve a different request.

After approval, execution still requires unchanged bytes/schema/terms, fresh case/source authority, healthy clock and valid 900-second snapshot, available shared allowance and one-attempt ledger admission. Any changed payload must return for review. Failed or ambiguous requests have no automatic retry.

The subsequent report must distinguish actual HTTP status, returned model, strict-schema compatibility, provider-reported tokens, estimated charge versus unavailable invoice information, and independent financial/evidence verification. HTTP 200 alone does not authorize live analyst generation.

No `.env`, demo database, model/policy/SHAP, regulatory approval, frontend activation, commit, push or deployment was changed by this preparation.
