# Claude development unblock and exact request review — 22 November 2026

**Latest final-review outcome:** [Exact-payload pre-dispatch review](CLAUDE_V2_FINAL_PRE_DISPATCH_REVIEW_2026_11_22.md) confirms unchanged 11,540-byte request, source provenance, active grants and offline contract shape. The fresh dynamic preflight failed closed with `ClockUnavailable`; dispatch is blocked and approval remains pending. Older successful preflight observations below are historical. No inference request was sent.

**Implemented and prepared; NOT live-validated. New exact-payload approval is PENDING. Live requests in this task: 0.** The consumed November 22 v1 approval is unchanged and grants no authority for this request. General analyst generation and regulatory publication remain disabled.

## 1. HTTP 400 investigation

The complete prior Anthropic error body is **not available**. The existing adapter discarded it after producing sanitized metadata; inspection found only the saved execution reports, immutable receipt and diagnostics. Retained facts: HTTP 400, `invalid_request_error`, request ID `req_011ChHvqtidYeKx1B7wN58PH`, schema mentioned, and vocabulary term `too`. The exact offending keyword or compilation rule **cannot be established from these artifacts**. No response body, diagnostic or successful result was fabricated, and no request was sent to recreate the error.

Current official documentation was reviewed on November 22:

| Area | Documentation and repository finding | Change |
| --- | --- | --- |
| JSON output API | `output_config.format` / `type=json_schema` is the documented interface | Retained |
| Keywords / references | Primitive types, scalar enum/const and local references are supported; not proof that the old schema is accepted | New reference-free wire schema uses basic objects, arrays, strings, booleans and small enum/const constraints |
| Required / nullable fields | Optional fields and unions contribute to grammar complexity | All wire fields required; no union/null grammar. Empty string denotes only absent nullable numeric metadata; local models still validate it |
| Model / thinking | Requested Sonnet 5.5 supports `between_tools` at `high` effort without tools | Model, thinking and effort retained; no extra tool or reasoning-budget field |
| Financial values | Existing local Decimal and independent raw-source checks are authoritative | Numeric values remain exact strings; no tolerance or correctness check weakened |

Sources: [structured-output contract and limits](https://platform.claude.com/docs/en/build-with-claude/structured-outputs), [Sonnet 5.5 thinking/effort compatibility](https://platform.claude.com/docs/en/models/sonnet-5-5/whats-new-sonnet-5-5), [current model identity and standard pricing](https://platform.claude.com/docs/en/models/sonnet-5-5/overview).

Grammar complexity is a **compatibility risk**, not a confirmed diagnosis of the historical response. The new projection must still pass genuine provider validation after approval.

## 2. Implementation

| Component | Responsibility |
| --- | --- |
| `backend/app/services/claude_wire_v2.py` | Typed `flat_selection_v2`: one findings array, hypotheses, coverage, questions, limitations and abstention; reference-free strict schema; deterministic conversion to the existing `AIProposal` |
| `claude_contract.py`, `claude_provider.py` | Existing native adapter builds/parses the versioned wire contract. Legacy request bytes remain unchanged. Development-only bounded HTTP-error detail is retained with credential redaction; ordinary diagnostics stay restricted |
| `provider_live.py`, `config.py`, `live_provider_runner.py` | Default-off, exact-input and approval-ID-bound development capability; bounded existing Linux subprocess and existing server-side secret channel |
| `investigation_drafts.py` | Existing atomic jobs, current source/case/snapshot checks, provider-wide admission lock, one outstanding paid attempt, immutable receipt/audit and independent completion. Development scope enforces one attempted dispatch per approval ID |
| `0022_claude_development_scope.py` | Candidate-only envelope permits explicit development scope with zero monetary reservation; preserves prior provider restrictions and blocks downgrade after development history exists |
| `scripts/validate_claude_live.py --development` | Reuses original synthetic source and coordinator; prepares a new exact request. `--execute` first requires the separate new owner approval, unchanged bytes/schema/terms and current authority |

No local financial-verification or citation verifier was relaxed. Flat findings are reassembled by their explicit claim type and passed through the **original `AIProposal` validation and independent verifier**. Decimal strings are not rounded; empty amount strings fail. Forged references and tampered totals remain rejected. Development v2 rejects regulatory-grounded input and regulatory output fields; existing approved-source/citation paths are unchanged.

The strict wire schema is **2,263 bytes**, versus **5,770 bytes** in the prior request, using compact JSON serialization. The complete request is **11,540 bytes**, versus 14,477. The new wire has no `$ref`, `$defs`, optional field or union. These are measured size/shape changes, not proof of provider acceptance or model quality.

## 3. Financial policy change — this development scope only

[Versioned financial authority](../contracts/claude_development_financial_scope_v1.json) records the owner's explicit withdrawal of the $20 testing cap and $2.15 reservation prerequisite for this task. It **does not approve a new exact request**.

- Scope: `development_no_spend_cap_v1`, purpose `development_validation`; explicit operator enablement and new approval-ID/exact-input matching required. No general inference flag is enabled.
- No application monetary reservation or total spend ceiling is a dispatch prerequisite in this scope. `max_cost_usd=0` is a **no-reservation accounting marker**, not a zero-dollar invoice guarantee or request spending cap. The provider adapter does not compare actual estimated charge against that marker.
- Normal Claude/demo and Luminal financial safeguards remain intact. Development settings deliberately set the old demo allowance/call cap to zero; passing development tests demonstrate that only the explicitly scoped path bypasses them.
- Existing monetary history remains **8 attempts / $17.00 reserved**, unchanged. New token/cost receipts continue to distinguish provider-reported usage, configured-rate estimates, unknown usage and reservations. No historical reservation or receipt was altered or deleted.
- One outstanding external attempt under the existing lock; one attempt per exact approval; no automatic paid retries or request loop. Output, body, execution-time and subprocess limits remain enforced. A timeout/ambiguous outcome is not authority to resend.

## 4. Exact NEW request requiring review

- [Complete readable request](../runtime/claude-demo-20261120/development-v2/request_readable.json).
- [Exact request bytes](../runtime/claude-demo-20261120/development-v2/request.json).
- [New pending owner record](../runtime/claude-demo-20261120/development-v2/owner_approval.json).
- [Fresh isolated preflight](../runtime/claude-demo-20261120/development-v2/preflight.json).

| Item | Identified scope |
| --- | --- |
| Approval ID | **`claude-development-review-2026-11-22-v2`** |
| Decision / identity / time | **Pending**; no reviewer identity, approval evidence or timestamp supplied or fabricated |
| Provider / model | Anthropic / `claude-sonnet-5-5` |
| Method / endpoint | POST `https://api.anthropic.com/v1/messages` — plain HTTPS, fixed host, no redirects |
| Exact request SHA-256 | `45cf3308e79f6bb86c932dba0e528cdba6b47b1c6b6f5c06d50c0880dcf935a9` |
| Template wire-schema SHA-256 | `ee937e7456e9e6e98a792909ccc822363ab1bbdec54cd3ec770a0252ffd9bfae` |
| Embedded exact schema SHA-256 | `64371fd7233393d23628d587bbfc6507db1c1bfe5c579f8e641d431e5ebf2cec` |
| Canonical input SHA-256 | `944999400800b4f9ee26aaa9a12f43291c696857a4c2855eca7a6f68f779f060` |
| Data | Original verified synthetic concentration case: 12 observations, 2 financial summaries, 17 opaque source-version references; no RF assessment, raw predictors or regulatory passages |
| Body limits | Prepared body 11,540 bytes; request/response limits 65,536 bytes each |
| Token limits | 32,768 accepted input tokens; 4,096 requested output tokens; application total-token budget 36,864. Input acceptance threshold is not a provider billing cap |
| Requests / outstanding / automatic retries | **1 / 1 / 0** |
| Execution deadline | **20 seconds**, existing bounded Linux process |
| Monetary policy | Explicit development-only withdrawal of old caps; no application monetary reservation prerequisite; actual tokens and estimated costs still recorded |
| Scope exclusions | No analyst activation, real customer data, regulatory publication, tools, streaming or prompt caching |

Byte reconstruction and credential-isolation scans passed without exposing key values. The canonical minimized evidence is identical to the independently regenerated synthetic material in the earlier source review; fresh current source/case checks, three clock observations and packet verification passed in the candidate runtime. This is not a claim of perpetual snapshot validity or a stable host clock. Permission, revision, clock and 900-second snapshot checks must pass again immediately before dispatch/publication. Changed bytes, schema or terms require a new review.

## 5. Database preparation and recovery

`scripts/rehearse_claude_development.py` verified the existing isolated cluster identity and prohibited the original source database. It:

1. Created a new protected, schema-scoped custom-format backup of the private probe, leaving existing backups unchanged; verified its restore listing.
2. Restored it into a separate disposable database and applied candidate 0021/0022 there.
3. Compared complete historical draft-run, attempt, receipt and draft-audit projections before/after; required exact equality and no running draft job.
4. Only after restore/rehearsal succeeded, upgraded **the private probe schema** from 0020 to 0022 and repeated the history/compatibility checks.

[Backup, restore and migration receipt](../runtime/claude-demo-20261120/development-v2/isolated_migration_receipt.json). All eight historical attempts remain identical. No original demo or local application's schema was migrated. Candidate release metadata explicitly retains unknown build/source identity, as in the existing private probe; no deployed release or production certification is asserted. The running local application remains on its existing release.

## 6. Actual tests and commands

| Verification | Result |
| --- | --- |
| Offline development, legacy contract/transport and approval selection | **71 passed / 0 failed / 0 skipped** |
| Disposable Linux/PostgreSQL development tests | **5 passed / 0 failed / 0 skipped** |
| Existing Linux/PostgreSQL snapshot/clock/provider security selection | **55 passed / 0 failed / 0 skipped**; overlaps offline contracts |
| Backup restore/rehearsal, isolated migration and history equality | **PASS** |
| Fresh candidate preflight / unchanged request | **PASS**, zero provider calls |
| Ruff lint / formatting | **PASS**; 14 changed Python files already formatted |
| Publication boundary / whitespace checks | **PASS**; 525 source candidates, private/secret boundaries preserved |

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_claude_development.py backend/tests/test_claude_contract.py backend/tests/test_claude_provider.py backend/tests/test_claude_live_validation_approval.py -q -p no:cacheprovider
.venv\Scripts\python.exe scripts/run_g5_3_tests.py --development
.venv\Scripts\python.exe scripts/run_g5_3_tests.py --security
.venv\Scripts\python.exe scripts/rehearse_claude_development.py
.venv\Scripts\python.exe scripts/validate_claude_live.py --development
```

PostgreSQL tests verified independent source-backed completion using explicit offline fixtures, tampered amount/reference rejection, zero-reservation usage accounting, concurrent-outstanding admission denial, consumed-approval replay denial and immutable history. Mock transport success is **not real provider compatibility**. No full backend suite, Chromium journey or frozen 4,000/12,000/4,000 scientific comparison was rerun; no frozen scientific assets or frontend code changed. No failed live result was rewritten.

## 7. Owner decision and next execution

After reviewing the full new request, explicitly approve **`claude-development-review-2026-11-22-v2`** if acceptable. Only that real decision may change its pending record. The previous v1 approval remains consumed. Financial-limit withdrawal alone is not exact-payload approval.

After approval and all current checks, the existing command is:

```powershell
.venv\Scripts\python.exe scripts/validate_claude_live.py --development --execute
```

That command was **not run** in this task. It permits one attempt, records HTTP/schema diagnostics, typed usage and estimated cost, then uses the existing independent verifier and immutable completion/failure path. Any failure ends the attempt without paid retry. General analyst inference remains disabled until actual provider verification and applicable evaluation/activation gates pass. No `.env` overwrite, original demo migration, regulatory approval, commit, push or deployment.
