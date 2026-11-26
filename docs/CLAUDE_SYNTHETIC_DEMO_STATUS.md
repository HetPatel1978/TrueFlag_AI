# Claude synthetic investigation demo status

## 2026-11-21 readiness recheck

- `backend/tests/test_claude_contract.py` and `backend/tests/test_claude_provider.py`: 27 passed, 0 failed (offline transports only).
- `python scripts/run_claude_postgres_tests.py`: 6 passed, 1 failed in the isolated PostgreSQL candidate schema. The `incorrect_total` test was denied with `ClockUnavailable` during setup, before its incorrect-total assertion. This run does not establish that the assertion passed or identify the clock denial's root cause.
- The separate running local application subsequently reported clock status available, one clock denial, and epoch 2. A later available observation does not establish a stable clock or resolve the test failure.
- No additional paid inference was sent, no provider approval was changed, and no unapproved regulatory source was published during this recheck. The claim-type schema correction remains unverified against a live response.

## Subsequent 2026-11-21 claim-type fix preparation

- Added a separately disabled, one-attempt synthetic claim-type-fix verification purpose. Its provider-wide lock, reservation, original actor, case, terms, recorded verifier failure, exact current input, and prior failure audit are checked before dispatch. Ordinary analyst inference is not enabled. A fresh source-authorized packet is assembled through the existing coordinator.
- Offline tests: Claude contract/provider tests **27 passed**. Isolated PostgreSQL: the expanded gate suite ran **8 passed**, followed by **7 passed, 1 failed** due to `ClockUnavailable` before the first claim-gate assertion. A successful isolated run does not resolve the recurring clock instability. Lint passed for the changed provider files.
- A network-free isolated preflight produced a verified synthetic packet. The subsequent command stopped in preparation because the preflight and attempted run used the same worker name with different tokens. The ledger independently showed **5 attempts and 5 receipts, $10.56 reserved**: no sixth provider attempt was created, and no provider call occurred. The worker-name conflict was corrected. The original pre-dispatch marker was retained; a separate one-time recovery marker is available only for the verified pre-dispatch condition and the unchanged five-attempt ledger.
- **No recovery dispatch was performed:** the subsequent PostgreSQL run again observed a fail-closed clock denial. A clock-stable authorized runner or a verified remedy for the host/guest clock is required before further paid compatibility testing. Do not treat one passing rerun as clock stability.
- [AI-assisted regulatory research review](REGULATORY_AI_RESEARCH_REVIEW_2026_11_21.md) confirms staged source hashes but is not a human legal review, source approval or publication.

## Status: blocked before live analyst use

- The owner authorized up to $20 for this synthetic demo. `ANTHROPIC_API_KEY` is present;
  its value was not printed or copied into source control.
- Anthropic's authenticated model-list endpoint returned HTTP 200 and listed
  `claude-sonnet-5-5`. Five bounded synthetic inference requests returned HTTP 200.
- No provider output passed the complete independent evidence-verification gate. The public
  investigation-draft API remains simulation-only; Claude is not enabled in the frontend.
- Official regulatory sources and independent labels are not approved; regulatory guidance
  remains unavailable. No regulatory sources were published.

## Real probe findings

| Attempt | Outcome | Provider-reported usage | Reservation |
| --- | --- | --- | --- |
| Initial probe | HTTP 200; response failed schema validation; exact cause unrecorded | unavailable | $2.10 |
| Basic diagnostic | HTTP 200; JSON did not pass the original schema | 6,485 input / 2,033 output | $2.10 |
| Detailed diagnostic | `packet_sha256:string_pattern_mismatch` | 6,485 input / 2,307 output | $2.11 |
| Hash-fix verification | Structured response parsed; independent verification rejected findings | 6,515 input / 2,283 output | $2.12 |
| Evidence diagnostic | Independent verification rejected `claim_type_mismatch` | 6,515 input / 2,225 output | $2.13 |

- Total retained reservation: **$10.56** of $20. All five attempts and receipts are retained
  in a dedicated schema on the isolated recovery PostgreSQL cluster. The first response's
  token usage was not retained; its full reservation remains held.
- Estimated standard-rate usage for the four responses with token counts is **$0.14048**.
  This is not a settled invoice, does not include the first request, and does not account for
  other use of the provider account. Application reservations cannot guarantee the invoice.
- The confirmed packet-hash mismatch was corrected by requiring the exact server-owned hash
  as a JSON Schema `const`. That correction was verified by a real subsequent response.
- The confirmed claim-type mismatch was corrected by constraining each response section to
  its corresponding claim type. The correction has offline and isolated PostgreSQL tests;
  it has **not** been verified with another live request. No further paid request was sent.
- Finding references, numbers, missing evidence and permissions are still independently
  checked. Only bounded diagnostic categories and token counts are retained on failures.

## Code, isolation, and remaining work

- Claude has a native fixed-host Messages transport, strict response parsing, a separate
  provider identity and a provider-scoped immutable reservation ledger. Runtime activation,
  compatibility approval and public analyst access remain off.
- Candidate migration `backend/alembic/candidates/0020_claude_provider.py` is staged outside
  the active Alembic chain. It was exercised only through a read-only overlay in disposable
  PostgreSQL schemas. The active release still expects `0019_upload_sessions`; the original
  demo database was not migrated.
- A complete demo still requires a verified real Claude result and evaluation, an authorized
  protected API/UI path, and linking uploaded synthetic alerts to transaction evidence. The
  alert CSV alone does not create transaction histories.
- `runtime/claude-demo-20261120/scored_alerts.csv` contains five approved synthetic training
  examples: three source-label positives scored above the frozen review threshold; two scored
  below it. These training rows demonstrate workflow, not independent model performance.
  They are not currently linked to the separate synthetic evidence scenarios.
- The local Docker/WSL clock has a history of regressions; the existing snapshot and clock
  checks remain fail-closed. No independent stable-runner acceptance is claimed.

## Tests

- Focused Windows tests: **106 passed, 5 skipped** across Claude, Luminal, budget and catalog
  tests. Isolated Linux/PostgreSQL Claude tests: **7 passed**. Existing isolated investigation,
  malicious-output, numeric and revocation regressions: **20 passed**.
- These tests do not establish production readiness or complete browser end-to-end acceptance.
- No source commit, push, deployment, live-demo migration, RF change, or automatic case action.

## Public sources

- [Anthropic structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- [Messages API](https://platform.claude.com/docs/en/api/messages/create)
- [Published pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- [API retention](https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data)
- [Commercial data and training](https://privacy.claude.com/en/articles/7996868-is-my-data-used-for-model-training)
