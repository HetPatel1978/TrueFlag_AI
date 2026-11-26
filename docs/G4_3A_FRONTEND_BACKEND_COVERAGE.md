# G4.3A — Frontend/backend capability and boundary matrix

## 1. Workflow integration

| Analyst capability | Existing authority / new thin projection | UI |
|---|---|---|
| Assigned case and supporting evidence | Existing case workflow and `/cases/{id}/evidence` | Existing Investigation view; unchanged permission guard. |
| Verified parent summary | Existing `/cases/{id}/investigations` request/history/detail and source packet verifier | Existing summary generator/history reused in the new Findings tab. |
| Generate simulated draft | New POST `/cases/{id}/investigation-drafts`; existing `InvestigationDraftService.request` | Exact simulation label; stable parent-bound key; double-submit lock; explicit user action only. |
| Durable processing | Existing draft jobs, constrained fake-provider runner, attempt/reservation/receipt, bounded retry/lease recovery | Pending/Processing/Completed/Abstained/Failed/Invalidated; bounded 40 checks, manual status refresh. |
| Review findings | New strict GET projection over existing independently revalidated immutable draft | Facts, calculations, stored model signals and hypotheses clearly separated. Human review remains pending. |
| Customer/account/transaction inspection | Existing customers/related/transactions APIs with signed snapshot, cursor limits and source filters | Claim-specific links and authorized-record chooser; no raw predictor snapshot. |
| History/resume | New requester-owned, bounded GET history; existing parent manifest/config identities | Open historical result without a new POST; recorded status does not imply current validity. |
| Stale/source/assignment denial | Existing current actor/case/source/version/assessment checks and snapshot clock controls | Clear/hide protected result, refresh guidance or denied case view. |
| Regulatory guidance | Existing G5.1 remains unapproved/inactive | Explicit unavailable state; no citations or research-only summaries. |

## 2. Authorization and projection

- Admin/supervisor case scope does **not** authorize another requester's draft history/detail. All roles use the requester's own runs; an authorized reader must generate/open their own verified parent.
- Server reconstructs the request from the selected immutable parent's manifest. Source-bound packet digest must match; core manifest deduplication must return that exact parent identity. No uploaded model, client-supplied feature/score or selectable provider can enter this path.
- Existing draft worker rechecks authorization before preparation, dispatch and publication. Gateway retrieval rechecks current source/permission state; immutable stored history is preserved when an active result becomes invalidated.
- Result projection accepts only simulation identity and typed transaction/calculation/assessment summaries. Credentials, arbitrary provider payloads, reservations, worker tokens, usage estimates and raw predictor values are omitted.
- API logs/audits use IDs, hashes, bounded counts and sanitized codes. Browser state is memory-only, request signals abort on unmount/logout, old responses are fenced and source-version/hash mismatches are withheld.

## 3. Verified versus pending capabilities

| Capability | G4.3A status |
|---|---|
| Deterministic offline draft workflow | Implemented; actual test/browser results in QA report. |
| Source/numeric/reference verification | Existing independent checks preserved and invoked; not full semantic entailment. |
| Human-reviewed/adopted findings | **Not implemented**; UI explicitly reports pending human review. No fabricated reviewer state. |
| Real LLM generation/quality | **Disabled / unmeasured**; no live inference. |
| Approved regulatory integration | **Inactive**; zero approved sources/independent labels at the G5.1 boundary. |
| Autonomous case action or SAR filing | **Absent**; human dispositions remain separate. |
| Stable Linux release acceptance | **Blocked from prior work**; a passing local/browser run does not resolve Windows/WSL clock instability. |
| Original demo deployment/schema upgrade | **Not performed**; original database must remain untouched without separate authorization. |

## 4. Test coverage

- `backend/tests/test_draft_api.py`: real HTTP 202/status/history, actual constrained Linux simulation subprocess, duplicate/concurrent/conflicting requests, missing/foreign requester cases, assignment/source/revision fencing, disabled provider controls, bounded history, invalid numeric output and atomic rollback.
- Same file adds a deterministic API/worker lock-order regression plus actual analyst-assignment revocation and explicit clock-uncertainty HTTP 503 assertions.
- `frontend/src/drafts.test.tsx`: disabled parent, processing/completion, double-click/idempotency, record inspection/focus, denial/clock cleanup, disabled-mode isolation, unsupported results, terminal failures, 40-poll limit, unmount/storage and history resume; typed no-store request projection.
- `frontend/e2e/drafts.spec.ts`: real API/PostgreSQL/worker, assigned analyst login, verified source inspection (transaction/customer/account), generation/status/result, history/refresh/logout, abstention, wrong-user access, revocation, controlled clock failure and desktop/tablet/mobile captures.
- Existing draft/coordinator/security/evaluation/regulatory suites and pinned ML checks are run separately; exact counts/failures must be read from the QA ledger, not inferred from this capability list.
