# G2.3 — Analyst workflow completion

## 1. Scope

- Working tree on `codex/project-initialization`, HEAD `a3b2ba49cd92c4aa0401842fa4999897fdc28713`. No commit, push, deployment or live migration.
- Preserves G2.1 evidence-only investigation and G2.2 presentation, authentication, assessment and batch workflows. No G3 decisions, G4 provider calls or G5 publication.
- Local Docker/Linux PostgreSQL acceptance is **not** independent clock-stable runner acceptance. G0/G1 release blockers remain.

## 2. Implementation and reuse

| Component | Change / existing authority |
|---|---|
| `backend/app/services/cases.py`, `schemas/cases.py` | Adds optional queue predicate to existing scoped listing. Existing listing/assignment contracts and CAS/audit transaction remain authoritative. |
| `backend/app/{api,schemas,services}/case_workflows.py` | New bounded projection gateways; current active-role and case locks, stored assessment integrity checks, allowlisted historical events. No schema change or duplicated scoring/assignment service. |
| `frontend/src/workflow-api.ts` | Typed client using existing no-store transport, abort/session and denial cleanup. |
| `frontend/src/workbench.tsx` | Real queue filters, assigned name, stored recommendation/version, investigation link and case Activity History route. |
| `frontend/src/case-workflows.tsx`, `.css` | Searchable assignment dialog and paginated activity; shared design tokens, native modal focus/Escape, stale mutation fencing. |
| `frontend/src/App.tsx` | Session-scoped client, contextual Activity History navigation, existing permission/visibility guards. |

## 3. APIs

All paths below are under `/api/v1`. Current analyst assignment or supervisor/admin scope applies on every case read.

| Endpoint | Contract |
|---|---|
| GET `/case-queue` | Existing search/status/priority/assignment/sort/page filters plus `queue=all|my|unassigned|review|processing`; limit 20 default/50 maximum, existing offset bound 10,000. Assigned username, latest verified stored route and assessment version; no predictors. |
| GET `/cases/{id}/workflow` | Existing workbench summary plus the same assignment/recommendation enrichment. Original `/overview` and `/cases` response fields unchanged. |
| GET `/cases/{id}/assignment-options` | Supervisor/admin only, active analysts only. `search` <=100 chars, escaped literal matching; limit <=20, offset <=1,000. Returns ID/username and case version, no passwords/contact/profile. |
| PUT `/cases/{id}/assignment` | **Existing** mutation: `expected_version`, `assigned_to` (UUID/null). Active manager and eligible target rechecked; changed assignment increments version and writes audit atomically; stale/conflicting/closed cases rejected. |
| GET `/cases/{id}/activity` | `category=all|assignment`; limit 20 default/50 maximum, offset <=1,000. Historical event type/time, redacted actor, outcome and permitted versions. No raw audit details. |

New reads reuse shared authenticated rate admission and four evidence-read slots; PostgreSQL lock/statement/idle timeouts remain 2/5/15 seconds. These are bounded queries, not a newly claimed production capacity guarantee.

## 4. Queue semantics

| UI queue | Persisted predicate |
|---|---|
| My Assigned Cases | `assigned_to = current actor`, intersected with current access |
| All Accessible Cases | Existing server authorization; analysts still see only assigned cases |
| Unassigned Cases | Null assignment; supervisor/admin only |
| In review / awaiting approval | Existing `in_review` / `awaiting_approval` state; no invented “awaiting review” decision |
| Assessment processing | Latest recorded assessment job Pending/Running; not an investigation outcome |

- Analyst defaults to My Assigned Cases; managers default to All Accessible Cases. Filters intersect and reset paging. Recommendations are from the latest immutable saved assessment, never recalculated in React.
- Assessment job status and saved recommendation are separate signals; an older stored assessment can coexist with a newer pending/failed job.

## 5. Mutation and history safety

- No arbitrary UUID-entry UI. Manager selects a current directory result or explicitly leaves the case unassigned. Server still revalidates the target on PUT.
- Double-click guard; no automatic consequential retry. Conflict, rate denial or lost mutation response requires fresh case state before another mutation. Successful refresh unmounts old version-dependent assessment/evidence/history state.
- Case authorization rechecked every 10 seconds and after visibility restoration; role/deactivation checks remain in the global shell. Denial unmounts protected views. This is bounded polling, not instantaneous push revocation.
- Activity joins canonical alert/job/run foreign keys, never JSON `case_id` claims. Only supported recorded actions appear. Other actor identities and source IDs are withheld; own actor is “You.” No generic audit browser.
- Historical outcomes use the recorded event, not a job's present status. Event time is historical wall time, not a guarantee of causal ordering. Missing events imply no conclusion. Requester-scoped packet history remains separate.

## 6. Acceptance and limitations

- Test/visual evidence: [G2.3 QA](G2_3_VISUAL_AND_FUNCTIONAL_QA.md). Full capability mapping: [integration audit](G2_3_FRONTEND_INTEGRATION_AUDIT.md).
- Approval/publication/provider boundaries remain closed. Malware scanning remains unavailable.
- No tenant model added: current manager scope is the repository's existing workspace scope.
- History projection has no new audit-resource index; count/query cost and queue enrichment must be measured before large-scale use. Current database timeouts fail safely rather than claiming scale.
- **G2.3 local functional/visual acceptance: PASS**, with final 87 PostgreSQL, 85 React and 21 Chromium tests passing; lint, formatting, TypeScript/build and publication checks passed. No skipped tests in these final runs. Earlier failures and fixes remain recorded in QA.
- **G2 release acceptance remains blocked** by the independent clock-stable runner requirement and residual reliability investigation. The earlier unexplained analytics 503 is not declared resolved by the passing rerun.
- **G4/G5 activation: not approved.** Separate provider/data-handling/egress and evaluation gates, qualified source approval and independent regulatory labels remain necessary; G0/G1 acceptance must be addressed before release. No later phase starts automatically.
