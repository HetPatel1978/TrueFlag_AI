# Claude v2 final pre-dispatch review — 22 November 2026

**Static review: PASS. Current dynamic dispatch review: BLOCKED BY CLOCK GUARD. Approval: PENDING. Live inference requests during this review: 0.**

This user message requested review, not approval or execution. No decision, reviewer identity, signature or approval timestamp was fabricated. The consumed v1 approval was not reused. No request/schema bytes were changed.

## Exact request offered for the owner's decision

| Item | Verified scope |
| --- | --- |
| Approval ID | `claude-development-review-2026-11-22-v2` |
| Complete readable request | [request_readable.json](../runtime/claude-demo-20261120/development-v2/request_readable.json) |
| Exact saved request body | [request.json](../runtime/claude-demo-20261120/development-v2/request.json), **11,540 bytes** |
| Request SHA-256 | `45cf3308e79f6bb86c932dba0e528cdba6b47b1c6b6f5c06d50c0880dcf935a9` |
| Template schema SHA-256 | `ee937e7456e9e6e98a792909ccc822363ab1bbdec54cd3ec770a0252ffd9bfae` |
| Embedded schema SHA-256 | `64371fd7233393d23628d587bbfc6507db1c1bfe5c579f8e641d431e5ebf2cec` |
| Provider / model | Anthropic / `claude-sonnet-5-5` |
| Actual adapter destination | POST `https://api.anthropic.com/v1/messages`; plain HTTPS, no user info, alternate port, query, fragment or redirects |
| Attempts / outstanding / automatic retries | **1 / 1 / 0** |
| Output / deadline | **4,096 requested output tokens / 20-second execution deadline** |
| Input / total token acceptance budget | 32,768 / 36,864; input acceptance is not a guaranteed provider billing cap |
| Request / response body bounds | 65,536 bytes each |
| Financial scope | `development_no_spend_cap_v1`: old $20/$2.15 prerequisites withdrawn only here; historical records and other financial scopes unchanged |
| Exclusions | General analyst inference, regulatory grounding/publication, tools, streaming and prompt caching remain disabled |

[Pending owner record](../runtime/claude-demo-20261120/development-v2/owner_approval.json). Only an explicit owner decision approving this identified request can authorize an attempt, and all dynamic checks must still pass at dispatch. Approval cannot waive the clock denial or permit modified bytes. The existing one-attempt ledger and marker prevent replay after consumption.

## Static and schema checks actually performed

- Recomputed SHA-256 and byte count from the original file. The readable copy parses to the same JSON; rebuilding with the existing adapter produces **identical request bytes**. Template schema, exact embedded schema, minimized evidence and retained terms digests match the pending record.
- Verified the fixed destination from the actual adapter's POST call, rather than merely trusting the approval record. Model, `max_tokens`, `thinking`, `output_config`, message roles and all configured request limits match.
- Compared known nonempty local credential values with the JSON body without printing values, prefixes, suffixes, hashes or lengths. No credential was present. Future authentication uses the existing server-side key in an HTTPS header; no credential is part of the reviewed JSON.
- Reviewed the current official [structured-output interface and schema subset](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) and [Sonnet 5.5 thinking/effort contract](https://platform.claude.com/docs/en/models/sonnet-5-5/whats-new-sonnet-5-5). The request uses `output_config.format.type=json_schema`, primitive types, scalar enum/const, required properties and `additionalProperties=false`; `between_tools` with `high` effort is documented for this model.
- The **2,263-byte embedded schema** has 4 object definitions, maximum inspected schema depth 5, and **zero optional fields, references or unions**. Its keywords fit the documented subset and explicit optional/union limits. No unsupported tool/citation feature or assistant-message prefill is present.
- Local schema-subset and contract-shape checks passed. A standalone `jsonschema` metaschema validator is not installed and was not installed for this review; no formal metaschema execution is claimed. Provider grammar compilation, authenticated account/model availability and actual response quality **cannot be established without live transport**.
- **71 offline tests passed / 0 failed / 0 skipped** across development/legacy contracts, transport fixtures and exact approval gates. These are offline checks, not paid compatibility evidence.

[Machine-readable static review](../runtime/claude-demo-20261120/development-v2/final_static_review_20261122.json).

## Authorized synthetic-source verification

A fresh PostgreSQL read-only transaction in the identity-verified isolated environment confirmed:

- Original `g1_concentration` synthetic alert and synthetic source classifications; existing `verify_release` regenerated the source records and verified their stored integrity.
- The saved request exactly equals minimization of the immutable stored packet; **12 transaction observations, 2 deterministic financial summaries and 17 opaque evidence-version references**.
- All 17 records remain actively linked; case/source access grants are active; the original source owner/administrator remains active. No real customer records, raw 27-feature predictors, RF assessment or regulatory passages are included.
- **Zero prior attempts for this v2 approval and zero outstanding provider attempts.** All 8 historical attempts remain retained, with $17.00 historical reservations. That historical amount is not a cap for this development request.

[Source/grant/ledger inspection receipt](../runtime/claude-demo-20261120/development-v2/final_provenance_review_20261122.json). This read-only inspection is not a substitute for the ordinary server-side permission, revision, snapshot and clock checks immediately before transmission/publication.

## Current clock/snapshot result — blocking

The existing network-isolated command was invoked **without `--execute`**:

```powershell
.venv\Scripts\python.exe scripts/validate_claude_live.py --development
```

It exited 1 with **`ClockUnavailable`**, at `SnapshotTime.observe()`'s backward-time rejection branch, before provider admission/dispatch. This failed service preflight was **not retried**. No attempt marker, reservation, live provider call or model output was created.

A subsequent **read-only** clock inspection found `regressed=true`, epoch **2**. At that later sample wall time was 133 seconds above the stored floor; this does **not** erase the preceding denial, clear the persisted flag, prove stable synchronization or constitute a successful service preflight. No manual clock/floor/epoch changes, synchronization changes or expiry extensions were made. The guard's normal durable regression containment was preserved.

[Clock inspection receipt](../runtime/claude-demo-20261120/development-v2/final_clock_review_20261122.json). Earlier successful observations in `preflight.json` are historical; they do not override this latest failure.

**Dispatch remains blocked.** Even after explicit approval, a fresh authorized service check must establish trustworthy time, valid current snapshot/epoch and unchanged evidence/request bytes. If it cannot, report zero transmission rather than loop, weaken the guard, reuse stale authority or silently change the reviewed payload.

## Response reporting and verification plan

After explicit approval and successful gates, permit exactly one request. Record actual HTTP status, returned model when present, retained sanitized provider detail or structured result, provider-reported tokens, configured-rate cost estimate and the independent verifier's outcome. Unknown usage/cost must remain unknown. HTTP 200 alone does not pass the complete gate.

The existing diagnostics are bounded: HTTP error body reads up to 8 KiB, retained development error message up to 2,048 characters, response-body limit 65,536 bytes. Retained error detail is credential-redacted and private, not a public API error body. Any truncation or missing raw envelope must be disclosed; an unbounded/full raw response is not promised. No actual provider error or response was generated in this review.

The original `AIProposal`, Decimal equality, source-reference membership, coverage, abstention, current permission/revocation, immutable audit and consequential-action controls remain intact. General analyst inference and regulatory publication remain disabled until the applicable complete verification gates pass. No application code, `.env`, model/policy/SHAP artifacts, original demo schema, consumed approval, commit, push or deployment was changed by this review.
