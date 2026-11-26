# Owner-approved Claude validation result — 22 November 2026

## Decision

**One approved live request executed. Complete independent verification gate: NOT PASSED. No automatic retry, analyst inference activation or regulatory publication.**

## Approval and dispatch evidence

- Approval ID: `claude-live-validation-review-2026-11-22-v1`. The owner explicitly approved the exact request in this conversation. [Recorded approval](../runtime/claude-demo-20261120/live_validation_owner_approval.json) preserves the pending predecessor and links a formatting-normalized transcription of the actual user authorization.
- Approval recording clock observation: **2026-11-22 11:58:53 UTC**, obtained from the clock tool. This is not an asserted user-message timestamp. The original message timestamp and legal name were not supplied; `approved_at` remains null, and the actor is identified only as the conversation user acting as project owner. No signature or independently verified identity was invented.
- Original request verified at **14,477 bytes**, SHA-256 `bfad88682342c1e5ea885b10f3c1ff6e78db5f2653849bd7501292621df17668`.
- Template schema `eb6df4791f3d12ecb7d066ed7facf330e5c078a49b5140b86db9b9a914919e83`; embedded exact schema `8ff1f321fcb4cd5b8d8c7f740ff4a41add84f4e5b8eadf7d73478dc84e28b333`. Both matched the owner's reviewed package; rebuilding the adapter request produced identical bytes.
- Plain URL and actual adapter destination verified: POST `https://api.anthropic.com/v1/messages`, requested model `claude-sonnet-5-5`. No Markdown wrappers, user information, query, fragment or alternate host. Redirects remain disabled.
- All reviewed token, byte, deadline and one-attempt limits matched the existing configuration. Synthetic case/source authority, verified parent packet, three clock observations, valid snapshot and ledger checks passed along the existing execution path before dispatch. No guards were relaxed.
- Existing conservative allowance before execution: **$14.85 over 7 attempts**; this attempt reserved **$2.15** within the existing **$20** scope. No external request other than this approved inference was made in this task.

## Actual response

| Field | Observed result |
| --- | --- |
| External requests / retries | **1 / 0** |
| HTTP status | **400** |
| Provider error type | `invalid_request_error` |
| Provider request ID | `req_011ChHvqtidYeKx1B7wN58PH` |
| Adapter latency | **1,151 ms**; durable receipt elapsed **1,227 ms** includes job processing overhead |
| Requested / returned model | `claude-sonnet-5-5` / **not provided** |
| Strict schema compatibility | **Not validated: provider rejected the request** |
| Token usage | **Unavailable**: input, output and cache counts were not returned |
| Estimated actual charge / invoice | **Unknown**; cannot calculate without token usage; no claim of zero charge |
| Current reservation / cumulative reservations | **$2.15 retained / $17.00** across 8 attempts |
| Remaining application reservation headroom | **$3.00**; not a provider balance or automatic authority for another request |

The bounded diagnostics report that the provider error mentioned the schema; their only retained vocabulary term is `too`, with rejection category `unknown`. The raw error message is intentionally not retained. This does **not** establish a specific unsupported keyword, schema-complexity cause or model failure. No request/schema mutation or further attempt was made to investigate it.

## Financial and evidence verification

- **Input checks passed:** byte identity, approved synthetic evidence, current source/case authority and existing independent packet validation before invocation.
- **Output verification did not run:** there was no usable structured model output and therefore no model-proposed financial figures, citations or findings to validate.
- No findings were accepted, repaired, substituted or published. No simulated finding was presented as a successful Claude response.
- A genuine HTTP response proves this transport received a response; it does not establish schema compatibility, verified model identity, investigation quality or readiness for live analyst use.

## Durable history and audit confirmation

- Draft run: `16b8c551-7d76-45ad-a64e-4c910136a799`.
- Read-only PostgreSQL confirmation found **one run attempt**, one retained failure receipt, a **failed** job, **zero published drafts**, **four audit events**, and **no retry scheduled**. Persisted configuration matched the approved wire schema, minimized input and $2.15 reservation.
- All eight historical attempts and receipts remain in the existing immutable database ledger; none were altered or deleted. The receipt's `usage` field holds diagnostic metadata with basis `provider_response_diagnostics`; its presence is **not** token-usage reporting.
- [Approval-bound execution archive](../runtime/claude-demo-20261120/claude-live-validation-review-2026-11-22-v1.execution.json) is a new exclusive file linking the decision, payload, actual response and scoped ledger verification. [Read-only ledger receipt](../runtime/claude-demo-20261120/approved_attempt_ledger_receipt_20261122.json).

## Verification performed

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_claude_live_validation_approval.py backend/tests/test_claude_contract.py backend/tests/test_claude_provider.py -q -p no:cacheprovider
.venv\Scripts\python.exe scripts/inspect_claude_probe.py
.venv\Scripts\python.exe scripts/validate_claude_live.py --execute
.venv\Scripts\python.exe scripts/inspect_claude_probe.py
```

- Offline selection: **41 passed / 0 failed / 0 skipped**. Actual live request: **one HTTP 400**, not a successful compatibility test.
- Additional scoped ledger inspection ran with a PostgreSQL read-only transaction in the existing identity-verified isolated environment. No source, API, model or policy code was changed for this execution; no migrations or demo record changes were made.

## Remaining blocker

The exact approved schema is still rejected. Future work should improve offline schema diagnosis or investigate the retained request ID through an authorized support channel. A different request requires its own explicit approval; the present approval has been consumed. General live analyst inference, compatibility flags and official regulatory publication remain unchanged and disabled. No commit, push or deployment.
