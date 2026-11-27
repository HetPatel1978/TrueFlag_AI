# Final integration and demonstration gate

November 22, 2026. **BLOCKED: no real Claude + official Regulatory RAG browser investigation has passed. Live requests executed in this task: 0.**

## 1. Gate status and immediate actions

| Gate | Actual status | Precise reason / immediate corrective action |
|---|---|---|
| Runtime stability | **External dependency** | Owner confirmed no independent runner is available. Docker remains WSL2-backed; unidentified SSH entry is not an authorized target. Supply an approved native Linux host and follow [the setup procedure](NATIVE_REGULATORY_RUNNER_SETUP.md) |
| Durable orchestration | **Candidate implemented; PostgreSQL acceptance pending** | Server admits parent/child intents together; worker freezes approved passages after parent verification. Apply/rehearse candidate 0023 only on the new isolated target and run the prepared acceptance tests |
| Regulatory sources | **Official bytes available; approval missing** | No `assets/local/regulatory/reviews/` record; reviewer registry remains unapproved/empty. Obtain genuine hash/scope/version/applicability/publication/grounding decisions through existing governance |
| Claude API acceptance | **Not attempted** | Stable preflight/source permission absent. Saved evidence-only v2 approval remains pending and cannot authorize new grounded bytes. Prepare/show a new complete grounded request only after those prerequisites |
| Independent verification | **Existing guards retained; new live result not verified** | Run real response through the existing source/numeric/citation validator. Reference membership is not legal claim-support certification; human semantic review remains required |
| Browser end to end | **Not run** | No compatible stable candidate API/workers with authorized real findings. Exercise React against that actual stack after the prior gates, including refresh and human review |
| Video readiness | **NO** | Do not record simulation as live Claude or unapproved references as approved guidance |

No VM/cloud provisioning, remote connection, CI dispatch, paid transport, source publication, live migration, commit, push or deployment occurred.

## 2. Implemented durable handoff

The existing React primary action already calls `POST /api/v1/cases/{case_id}/investigation-drafts/start`. It now supports backend-controlled regulatory retrieval without browser job chaining:

1. Existing case authorization/revision checks admit the evidence parent and draft child atomically. With regulatory integration disabled, the old evidence-only contract is preserved.
2. With regulatory integration enabled, start persists an immutable `ReferenceQuery` and a server-computed context/release/grant-revision fingerprint in the child configuration. Optional `regulatory_query` accepts the existing bounded query/section contract. Omission uses a public bank AML/SAR search phrase; it is a search intent, **not** a hardcoded passage/citation/result. Revoke/regrant cannot restore old queued authority; an explicitly new authorized request can bind a changed context without changing financial evidence.
3. Child claiming waits for the durable parent to finish. The worker revalidates its evidence packet, then retrieves through the existing approved-only G5 service.
4. The worker freezes exact packet/parent/case/actor/snapshot/query/selected source versions/grant revision/clock epoch and the existing 900-second deadline in `DraftRegulatoryBinding`.
5. Binding, retrieval audit and provider-attempt reservation share the existing preparation transaction. Failure rolls them back together; clock containment still commits independently as designed.
6. Dispatch, completion and protected reads reuse the stored binding and existing independent validators. Retries do not renew it, change passages, or extend expiry. A reserved/ambiguous live attempt keeps existing one-attempt recovery semantics.
7. Missing/unapproved context stops before provider reservation; the job fails for manual review with the allowlisted `regulatory_context_unavailable` verification reason in audit history. It does not silently become an evidence-only live result.
8. Pending status reads do not trigger retrieval or launch another job. Completed grounded results use the existing citation-bearing API projection; React can reopen them through protected history after refresh while authority remains current.

### Changed files

| Files | Responsibility |
|---|---|
| `backend/app/schemas/provider_live.py`, `schemas/draft_api.py` | Typed immutable query intents; optional start query; development v2 cannot acquire regulatory scope |
| `backend/app/services/draft_api.py` | Server-owned query admission through the existing one-action endpoint |
| `backend/app/services/investigation_drafts.py` | Deferred retrieval/freeze, schema fence, immutable reuse, pending/result reads and manual-review failure |
| `backend/app/services/investigation_draft_verifier.py` | Existing grounded response schema selection also applies to deferred intents |
| `backend/app/workers/investigation_provider_process.py`, `workers/live_provider_process.py` | Reuse typed config selection across existing isolated subprocess boundaries |
| `backend/alembic/candidates/0023_durable_regulatory_start.py` | Database requires matching frozen binding before a deferred attempt; refuses downgrade with retained deferred intents |
| `scripts/claude_migration_overlay.py` | Optional candidate-0023 test overlay; existing defaults unchanged |
| `scripts/native_regulatory_acceptance.py` | Refuses Windows/WSL; isolated native PostgreSQL clock/test procedure, no provider credentials or live activation |
| `backend/tests/test_deferred_regulatory_start*.py` | Offline contract/boundary coverage and native PostgreSQL acceptance targets |

Paths in abbreviated schema/service/worker entries are relative to `backend/app/`. The current application's migration head, configuration, navigation and scientific models were not changed. **Candidate code is not a deployed, accepted workflow.**

## 3. Candidate database boundary

- Revision: `0023_durable_regulatory_start`, after candidate 0022. No schema was upgraded here.
- No new queue or feature table: existing immutable configuration stores the retrieval intent, existing binding table stores the worker's frozen result.
- The attempt-insert trigger checks run/actor/case/parent/manifest, query, parent snapshot, packet identity and available grounding. Existing immutable binding triggers remain in force.
- New intent admission/preparation rejects databases lacking revision 0023. The trigger is not assumed present in the `0019` application or `0022` private probe.
- Empty upgrade/rollback, populated downgrade refusal, atomic rollback and concurrency require the prepared real PostgreSQL tests on the stable target. Syntax/lint checks do not establish PostgreSQL execution correctness.

## 4. Actual verification in this task

| Check | Actual outcome |
|---|---|
| Offline deferred admission/reuse/scope/native-refusal tests plus existing Claude contract/provider/approval regressions | **100 passed / 0 failed**; no network/database transport used |
| Native PostgreSQL acceptance targets | **10 skipped**; not executed against WSL or another database |
| Frontend/source changes | No navigation/component rebuild; existing primary action and protected result views reused |
| Live Claude, real official-grounded findings, Chromium end to end | **Not run** |
| Existing v2 request / approvals / `.env` | Must remain byte-for-byte unchanged; final preservation receipt retained privately |

Offline tests check configuration identity, server handoff, no retrieval/renewal on retry, missing source denial, no rebind after an attempt, source verification failure and worker proposal typing. They use explicit service-boundary fixtures; they do not prove case authorization or transaction isolation. Native tests exercise those real PostgreSQL boundaries, concurrent requests, source revocation, rollback, missing bindings, history refresh, recovery and downgrade protection once a runner exists. Fixtures are not official regulatory approvals or genuine Claude output.

The one read-only inventory of the identity-verified isolated local application found **0 official-version approvals**. It made no clock observations/guard updates, provider requests or database writes. This is distinct from executing acceptance on the unstable runtime.

The final offline command was:

```powershell
$env:PYTHONPATH = 'backend'
.venv\Scripts\python.exe -m pytest backend/tests/test_deferred_regulatory_start.py backend/tests/test_deferred_regulatory_start_postgres.py backend/tests/test_claude_grounded_compact.py backend/tests/test_claude_development.py backend/tests/test_claude_contract.py backend/tests/test_claude_provider.py backend/tests/test_claude_live_validation_approval.py -q -p no:cacheprovider
```

An initial new unit fixture incorrectly returned a UUID object instead of the established string job-ID projection; that fixture was corrected. No API contract was relaxed. Native-helper CLI help and changed-file lint/format checks were also verified; real migration/worker/browser acceptance remains pending. The native helper reads actual JUnit counts and refuses acceptance when any required case is skipped, fails, errors, or no cases execute; offline coverage checks that accounting.

## 5. Source and live-request approval dependency

Real historical text is already retained for 31 CFR 1020.210 and 1020.320 as of November 2, 2026. Existing source integrity evidence remains in [the source checklist](PHASE3_4_SOURCE_APPROVAL_CHECKLIST.md). No signed/accepted replacement review was found or invented.

The current research API exposes **metadata only**, explicitly marks `eligible_for_ai_grounding=false`, and does not grant passage access. `RegulatoryInvestigationService._origin` requires official curated versions with human review outside test fixtures. Consequently this task cannot use the conditional research exception to send unapproved official passages to Claude. Preserve that prohibition until genuine review/publication/grants are available.

The original 11,540-byte v2 SHA-256 remains `45cf3308e79f6bb86c932dba0e528cdba6b47b1c6b6f5c06d50c0880dcf935a9`. No approval was consumed. A grounded request requires different bytes and a separate exact-payload decision: full minimized synthetic packet plus actual permitted passage text/IDs/versions/digests, model `claude-sonnet-5-5`, plain HTTPS endpoint `https://api.anthropic.com/v1/messages`, schema/hash, token/size/deadline/one-outstanding limits and exactly-one/no-retry authority.

That new payload was **not prepared as authorized or dispatched**, because stable runtime and permitted source context do not yet exist. Do not fabricate an approved source envelope to fill it. Future controlled grounded validation must also fit a separately reviewed provider authorization scope; the old evidence-only development approval and general-analyst flag must not be reused as shortcuts.

## 6. Definition of done remains open

After infrastructure and review dependencies are supplied: execute native clock/PG acceptance; rehearse candidate services on a fresh isolated copy preserving historical records; prepare/show/approve one grounded request; record its actual HTTP/error/usage and verification; then exercise the real React generation → findings → citations → refresh → analyst review/audit journey. No unit-test count or source parser result substitutes for that outcome.
