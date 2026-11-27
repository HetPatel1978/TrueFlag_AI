# G3.1 — Case decision, authorization and audit contract

## Protected API

| Method/path | Contract |
| --- | --- |
| `GET /api/v1/cases/{case_id}/casework?limit=20&offset=0` | Current case-authorized, source-checked history; latest journal revision, open request/pending escalation counts, internal resolution and enabled outcomes. Limit 1–20; offset 0–1,000. |
| `POST /api/v1/cases/{case_id}/casework` | Strict discriminated human command; `Idempotency-Key` required. Returns **201** immutable entry, including safe idempotent replay. No worker/provider execution. |
| `GET /api/v1/supervisor-review-queue?limit=20&offset=0` | Active supervisor/admin only. Pending escalation/case IDs, author and timestamp; no rationale or source payload. Case drill-down performs current source checks. |

Every mutation requires `snapshot`, `expected_revision`, a meaningful 10–4,000-character `rationale`, and optional `supporting_records` (maximum ten exact typed references). Unknown fields are rejected. References are compared with current canonical source-bound records, including identity, source version, kind, version and SHA-256. No client-provided amounts, provider choices, model scores or actor identities are accepted.

| Command kind | Additional fields |
| --- | --- |
| `note` | Optional `parent_id` for an own-note addendum. |
| `information_request` | Typed `category`, responsible role, optional ISO calendar `due_date`. |
| `information_response` | Request `parent_id`, `status=resolved/cancelled`. Resolved requires a supporting record. |
| `finding_review` | `draft_run_id`, claim `reference_id`, `expected_draft_sha256`, typed human decision. |
| `escalation` | Rationale and optional supporting references. |
| `supervisor_response` | Escalation `parent_id`, `approve_resolution/return_for_investigation`, configured `proposed_outcome`. |
| `resolution` | Approval `parent_id`, matching `outcome`, literal `confirmed=true`. |

Failures: **401** anonymous; **403** role/separation denial; **404** case/reference/parent unavailable (no cross-case enumeration); **409** stale snapshot/journal/approval or unmet prerequisites; **413** oversized requests; **415** wrong media type; **422** malformed commands; **429** existing admission limits; **503** clock/integrity/database uncertainty. No private exception messages, raw SQL, feature values or tokens are returned.

## Authorization and revision fences

- All roles are reread from active DB users. Analyst scope is current assignment; supervisor/admin scope reuses existing case policy. Every read, write and replay obtains current case authority.
- Signed snapshots remain actor/case/revision/role/assessment/epoch-bound with the unchanged **900-second** lifetime. Persistent time floor/epoch guards and clock rechecks remain fail-closed across API/worker boundaries.
- Gate order is existing coordinator admission → actor → case; journal revision is serialized under the existing case lock. Assignment updates use the same case lock. Concurrent commands at one revision cannot both create consequential entries.
- Human commands do not increment case version merely for a note/review/escalation; this preserves the existing verified draft as evidence while casework progresses. Only confirmed resolution changes case status/disposition and increments case version, invalidating prior source snapshots/draft runs through existing checks.
- Supervisor approval must be independent of the escalation requester and bind current case/evidence/access revisions. Finalization is restricted to that approving supervisor and its exact proposed outcome, with no intervening casework. Admin cannot override these conditions.
- Draft review is requester-scoped and simulation-only. Finalization independently revalidates the original reviewer's current source-bound draft, selected claim and exact content digest. No broadened draft-history privilege or human-to-model proxy identity is exposed publicly.
- Only finding reviews bound to the current case/evidence/access revisions are approval inputs. Older reviews remain immutable history. Interim outcomes can progress through a new verified investigation and new review; stale escalations can be returned, but cannot be approved. This prevents a stale run from authorizing an outcome or permanently blocking legitimate renewed investigation.

## Immutable journal and atomicity

- `casework_entries`: case/actor, server author/time, monotonically increasing per-case revision, kind, scoped parent, hashed request key, normalized command digest, content digest, typed payload, snapshot/revision/assessment/finding provenance, unique audit FK.
- PostgreSQL rejects **UPDATE, DELETE and TRUNCATE**. Composite FK binds every parent to the same case; unique constraints enforce per-case revision and per-actor idempotency. Deferred audit trigger requires the exact case/actor/action/entry/content-hash envelope at commit.
- Service reads verify journal content hash and corresponding exact audit envelope before projection. This is application/DB integrity enforcement, not a cryptographic defense against a database owner who can replace triggers and recompute hashes.
- Audit details contain only entry ID, content hash, revision and policy version. Rationale/source records are not copied into logs or audit details. Authoritative journal and audit creation plus any human case-state change commit in one transaction; exceptions roll back all writes.
- Same actor/key/normalized command returns the existing entry after current proof validation. Different case/content is a conflict; different keys at a stale revision are conflicts. A fresh signed snapshot may be supplied on retry without changing the semantic command. Closed/stale-source replay never bypasses current snapshot authorization. A network-ambiguous finalization requires refreshed history/proof before retry; at most one resolution is recorded.
- Snapshot signature, expiry and epoch are checked again immediately before mutation publication/replay. No extension of the 900-second lifetime or monotonic-clock substitute was introduced.
- Evidence/access revisions changing suppress historical payload/binding while retaining bounded audit metadata. Previously authorized rationale cannot remain visible through stale UI state. Human text is rendered as text, never HTML. No notes or credentials are stored in browser local/session storage.

## Human versus model semantics

- Notes and decision rationale are human assertions. Source-link validation proves membership/authority; it does not certify every free-text sentence or determine criminal conduct.
- RF/Policy/SHAP and original verified simulation records remain immutable and separate. A finding review records acceptance for consideration, rejection, deferral or further investigation; it cannot call case resolution.
- Internal final outcomes do not file, approve or imply applicability of a SAR or regulation. Unapproved regulatory sources and live-provider generation remain inactive.
- Any final-resolution policy changes require explicit product/compliance review; configuration can restrict outcomes only. Open request, independent-review, clock, source, confirmation and numeric safeguards are not optional switches.
