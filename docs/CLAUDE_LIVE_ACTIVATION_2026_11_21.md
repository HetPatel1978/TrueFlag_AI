# Claude live activation — 21 November 2026

**22 November approved execution:** the owner subsequently approved exact request `bfad8868…17668` under ID `claude-live-validation-review-2026-11-22-v1`. One request returned HTTP 400; no retry or output acceptance. Ledger is now **8 attempts / $17.00 reserved**. See [actual response, verification status and audit confirmation](CLAUDE_APPROVED_PROBE_RESULT_2026_11_22.md). Historical pending-state text below is superseded by this execution result.

**22 November exact-review update:** the saved revised payload was verified byte-for-byte, independently tied to regenerated synthetic sources in a read-only isolated database check, and presented in a [complete request/limits approval package](CLAUDE_LIVE_REQUEST_REVIEW_2026_11_22.md). The owner record is **pending**, not approved. No additional provider request or live activation occurred. Historical attempt results below remain unchanged.

## Actual status

- The owner requested live Claude investigations, using the existing synthetic-only $20 demo allowance. No credential, `.env`, original demo, RF, policy, SHAP or regulatory approval was changed.
- The running local application remains simulation-only. No compatibility flag or general analyst activation was set. No automatic simulation substitution was added.
- This task dispatched **one genuine Anthropic request** through the existing Linux subprocess, durable job, reservation ledger, current source/case checks and independent verifier. HTTP **400**, `invalid_request_error`, output schema mentioned, latency **1,217 ms**; request ID `req_011ChH9DAYNvssh9D3ruDAPM`.
- Returned model, token usage and actual charge were unavailable. No verified finding was produced. Retained reservations increased from **$12.70 / 6 attempts** to **$14.85 / 7 attempts**, against the existing $20 allowance. These are reservations, not account balance or an invoice.
- The first invocation stopped before admission at a confirmed worker-registration conflict: preflight and execution reused one name with different tokens. Registration now uses a unique name; recovery preserved the original marker and required database proof of no prior reservation for that wire version. It did not resend a paid request.

## Implemented

- `scripts/validate_claude_live.py`: network-isolated preflight by default; explicit single-attempt live validation uses the existing adapter, authority, ledger, financial limits and source/numeric verifier. Immutable attempt history is retained. Current API/worker clock checks remain mandatory.
- Exact-input-bound `live_validation` authorization is distinct from `investigation`. Ordinary paid inference still requires separately verified compatibility. Provider-wide locking, no outstanding paid attempt, one attempt per wire schema and the $20 total reservation ceiling remain enforced.
- Strict schema projection makes defaults explicit and uses shared section definitions and Decimal text, reducing optional/union grammar growth while retaining original local validation. No permissive prose parsing, numeric tolerance change, forged-reference acceptance or scientific change.
- Bounded HTTP diagnostics retain allowlisted rejection categories/schema vocabulary, not response prose, feature values or credentials. Historical 400 bodies were not retained and cannot be reconstructed.

## Exact pending request for owner review

Automatic approval review rejected a further paid request because a changed wire schema is a changed approved payload. **The rejected command did not execute.** The revised request is prepared locally; it is not approved or sent.

| Field | Prepared scope |
| --- | --- |
| Provider / endpoint | Anthropic / `https://api.anthropic.com/v1/messages` |
| Model | `claude-sonnet-5-5` |
| Data | Original approved isolated synthetic case, current source authority; no real customer records, private ML artifacts or regulatory passages |
| Request SHA-256 | `bfad88682342c1e5ea885b10f3c1ff6e78db5f2653849bd7501292621df17668` |
| Wire schema SHA-256 | `eb6df4791f3d12ecb7d066ed7facf330e5c078a49b5140b86db9b9a914919e83` |
| Minimized input SHA-256 | `944999400800b4f9ee26aaa9a12f43291c696857a4c2855eca7a6f68f779f060` |
| Local payload | `runtime/claude-demo-20261120/live_validation_payload_bfad88682342c1e5ea885b10f3c1ff6e78db5f2653849bd7501292621df17668.json` |
| Requests / retries | **One**, no automatic paid retry; no general analyst activation |
| Limits | 65,536 request bytes; 32,768 accepted input tokens; 4,096 output tokens; fixed-host/no redirects; existing bounded subprocess deadline |
| Reservation | **$2.15**; projected cumulative reservations **$17.00 / $20**; unknown charges retain reservations |
| Required before dispatch | Recorded owner approval binding the exact request/wire hashes, provider/model/endpoint and one-request financial scope; current source/case/clock checks; unchanged retained provider terms; ledger admission |

Approval belongs in a new `runtime/claude-demo-20261120/live_validation_owner_approval.json` record after an explicit owner decision. The runner checks it and rejects changed request bytes before provider invocation. No approval is inferred from key presence, past successful HTTP responses or source-review templates.

## Tests and limitations

- Offline Claude contract/transport and exact-payload approval: **41 passed**, including exact operator authority, continued denial of ordinary inference, strict section types, bounded request/response, malformed/hostile output and denial of changed model, endpoint, payload, budget and request-count scope. Command: `python -m pytest backend/tests/test_claude_contract.py backend/tests/test_claude_provider.py backend/tests/test_claude_live_validation_approval.py -q -p no:cacheprovider`.
- Existing isolated snapshot/clock/provider security selection: **55 passed**, command `python scripts/run_g5_3_tests.py --security`. This overlaps contract tests and is not an additional independent 55-provider evaluation. Ruff lint/format passed for all 11 changed Python files; publication boundary check passed (516 source candidates).
- Real isolated Linux/PostgreSQL provider tests: **8 passed / 1 failed** on each of three runs. The new one-reservation-per-wire test passed. The existing multi-stage bootstrap test failed first at parent worker setup (`pending` instead of `succeeded`), then at clock checks in prepare and claim. Do not claim complete reliability acceptance or a fixed historical intermittent cause.
- Source preflight passed with three repeated authoritative clock observations; this does not establish ongoing host clock stability. A later uncertainty still denies dispatch/publication.
- Full frozen 4,000/12,000/4,000 regressions were not rerun in this activation task. No frozen artifacts were edited.
- No new frontend code, demo migration, source publication, commit, push or deployment.

## Authoritative contract research

Retrieved 21 November 2026:

- [Sonnet 5.5](https://platform.claude.com/docs/en/models/sonnet-5-5/overview): model identity, 1M context and standard $2/$10 per million input/output token pricing. Standard token-rate estimates are not provider invoices.
- [Thinking](https://platform.claude.com/docs/en/build-with-claude/thinking): thinking consumes output-token budget. No tools, caching, batch discount or other billing feature is enabled here.
- [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs): strict JSON Schema subset and grammar complexity limits. Schema rejection is confirmed; the first retained 400's precise schema defect remains unconfirmed. Projection changes are compatibility candidates, not proof of a fix.

## Remaining activation gates

1. Obtain explicit approval for the exact revised synthetic request; execute at most one attempt.
2. Require a genuine typed response and successful independent financial/reference verification; never pre-set compatibility to true.
3. Validate candidate migrations/release and shared reservation accounting before enabling the local analyst runtime. An application ledger in another database must not reset the existing $20 allowance.
4. Resolve clock-health acceptance; keep permission, snapshot expiry and financial evidence checks fail-closed.
5. Official regulatory grounding remains separately unavailable until valid source approvals exist. It is not necessary for evidence-only Claude compatibility.
