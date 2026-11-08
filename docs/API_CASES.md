# Secure case retrieval and assignment

Scope: one synthetic-data workspace. No tenant/team boundary or enterprise IAM is implied. Existing ingestion/authentication contracts are unchanged; `supervisor` is an additional database-backed role.

| Permission | Analyst | Supervisor | Admin |
|---|---|---|---|
| List/detail | Only own assigned cases | All workspace cases | All workspace cases |
| View unassigned cases | No | Yes | Yes |
| Assign/reassign/unassign | No | Yes | Yes |
| Ingest alerts / global audit endpoint | No | No | Yes |

`GET /api/v1/cases` returns `{items,total,limit,offset}`. Items preserve `id, alert_id, assigned_to, status, disposition, version, created_at` and add safe workbench metadata: `source_id`, `priority` (Standard/High), `assessment_status` (not_requested/pending/running/succeeded/failed) and nullable `latest_job_id`. No raw customer predictors are returned. Filtering is applied **inside authorization scope**, including `total`.

| Query | Allowed values |
|---|---|
| limit / offset | 1–100 (default 25) / 0–10000 (default 0) |
| status | open, in_review, awaiting_approval, closed |
| assigned_to | UUID; intersects the caller's authorized scope |
| assignment | all (default), assigned, unassigned |
| search | Up to 128 characters; literal case-insensitive source/case/alert ID substring, wildcard-escaped and scoped |
| priority | Standard or High, existing frozen KYC grouping |
| assessment_status | not_requested, pending, running, succeeded, failed; latest requested job |
| sort_by / sort_order | created_at (default), status, version / asc, desc (default) |

Sorting uses a fixed column allowlist and UUID tie-breaker. Unknown parameters, contradictory assignee/unassigned filters and invalid bounds return 422. Counts/pages can change during concurrent work; this is bounded offset pagination, not an immutable snapshot/export.

`GET /api/v1/cases/{case_id}` adds `alert: {source_id, data_classification, feature_contract_version, features}`. The feature projection contains only the approved 27 predictors. Passwords, notes, source SAR labels, idempotency keys, stored model paths and arbitrary JSON metadata are never projected. Active role, assignment and protected data are checked in the same SQL statement. Hidden and nonexistent UUIDs both return **404, `Case not found`**; invalid UUID syntax returns 422.

`GET /api/v1/cases/{case_id}/overview` returns the enriched list summary without `alert.features`. Current role/assignment is checked in the same data query; hidden/missing returns 404. `case.overview_read` audit commits before disclosure; audit failure returns sanitized 503. The React workbench uses this route instead of the full predictor-bearing detail route. Overview is a single-record read and does not use pagination parameters.

`PUT /api/v1/cases/{case_id}/assignment` requires a current active supervisor/admin and the JSON body:

```json
{"assigned_to":"00000000-0000-4000-8000-000000000001","expected_version":1}
```

Use a real provisioned **active analyst** UUID, or JSON null to unassign. Both fields are required. `expected_version` is a strict integer (not a string/bool), between 1 and 2147483646. Caller actor/role, case status/disposition, alert IDs and other fields are forbidden.

- Success: 200 with updated case summary; version increments once for an actual assignment change. Status/disposition remain unchanged.
- No-op: matching current assignment/version returns 200 without a version increment or creation of a change audit event. It still executes a database version predicate, preventing a stale no-op from bypassing concurrency checks.
- Stale version or closed case: 409. Reload before making a new request; after an ambiguous network result, GET the case to confirm the current version/assignment.
- Unknown/inactive/non-analyst assignee: neutral 422 without echoing the target or revealing its account status.
- Missing case: 404; missing/inactive/invalid credentials: 401; analyst assignment attempt: 403, regardless of case identity.
- Update, version and `case.assignment_changed` audit commit together. Database failures return neutral 503 and roll back uncommitted changes. PostgreSQL shared locks preserve manager/assignee eligibility until commit; compare-and-set versioning arbitrates concurrent case changes.
- Audit details contain previous/new assignee UUIDs and versions, with the actual database actor; no customer fields or client-supplied identity. No assignment action scores, dismisses, closes, files or changes source labels.

Provision a supervisor locally with the existing interactive CLI:

```powershell
docker compose exec backend python -m app.security.bootstrap --username supervisor --role supervisor
```

New endpoints return server-generated `X-Request-ID` and no-store headers. The API is rate/body bounded as documented in SECURITY_PLAN. Phase 2.9 case dashboard/details and assessment workflow are implemented; frontend assignment editing remains pending. See [workbench contracts and acceptance](PHASE2_9_FRONTEND.md).

## Assessment integration

Protected asynchronous assessment APIs reuse this exact current-role/assignment scope. See [assessment contracts](API_ASSESSMENTS.md). Ingestion and assignment contracts remain unchanged; no model result changes human case state.

## Phase 3.2 internal evidence boundary

- Existing HTTP contracts are unchanged; no evidence endpoint is published. `app.services.evidence.EvidenceService` is an internal PostgreSQL-only boundary, accepting server-authenticated UUID identities and rechecking current SQL role/assignment/source grants.
- Manifests expose bounded version/hash/coverage metadata, not raw predictors or customer observations. New synthetic case creation reuses existing atomic ingestion and requires all 27 explicit declared inputs. It does not start assessment jobs.
- Public evidence retrieval belongs to separately scoped Phase 3.3. [Interfaces, limits and security](PHASE3_2_EVIDENCE_FOUNDATION.md).

## Phase 3.3 authorized evidence reads

- `GET /api/v1/cases/{case_id}/evidence` returns typed context/coverage and a signed snapshot, with optional explicit stored `assessment_id`.
- Protected read-only POST projections under the same base: `/transactions`, `/customers`, `/related`, `/model`, `/activity`. JSON includes the snapshot and allowlisted typed parameters; no actor, arbitrary SQL/path/URL, feature overrides or generic tools.
- Current case/source/version predicates, snapshot-bound cursors, audited disclosure, shared rate budget and body/response/scan limits apply. Source observations, deterministic facts and existing model signals remain separate. [Full contracts, limits, arithmetic and errors](PHASE3_3_RETRIEVAL_ANALYTICS.md).
- No public evidence upload, raw legacy URI/document retrieval, corpus, LLM, frontend or automatic case action.
## Phase 3.4 protected regulatory reference reads

| Route | Request / response |
|---|---|
| `POST /api/v1/cases/{case_id}/references/search` | Exactly one bounded `query` or exact `section`; optional strict `limit` 1-5; typed availability outcome and <=5 immutable citations |
| `GET /api/v1/cases/{case_id}/references/{reference_id}` | Resolve exact stored citation through current case/context access and validity, or hidden 404 |

- Server selects fixed U.S.-bank historical scope and configured approved corpus; clients cannot supply release, jurisdiction, dates, source URLs or permissions. No configured corpus returns authorized `unavailable`, never invented legal text.
- Citations expose regulatory text/metadata, not customer features: authority class, immutable IDs, publisher URL, exact section/locator/UTF-8 offsets, hashes, dates, parser/release identity and limitations. Regulatory context is not evidence of a customer violation.
- Current role/assignment plus explicit corpus grant; source/release withdrawal and supersession invalidate saved references. Shared auth rate budget, read slots, no-store, 12 KiB JSON and bounded output. Errors: 401/404/413/415/422/429/sanitized 503. Curator admission/publication APIs are not exposed.
- [Full contracts and operational limits](PHASE3_4_REGULATORY_KNOWLEDGE.md). Official corpus publication and reviewed legal retrieval evaluation remain pending [human approval](PHASE3_4_APPROVAL_DOSSIER.md).
## Phase 3.5.1 investigation foundation

No new HTTP route is exposed. The deterministic investigation coordinator is an internal authenticated-identity service plus bounded purpose-token Linux worker. Existing case/evidence/assessment APIs are unchanged. Future API/tool gateways must bind actor/case scope on the server; they cannot forward arbitrary model-selected identities, source contexts or SQL. [Interfaces, output separation, authority and acceptance](PHASE3_5_1_EVIDENCE_COORDINATOR.md).

## Phase 3.5.2 simulation-only draft service

- No new HTTP endpoint or frontend. Trusted internal `InvestigationDraftService.request(actor, case, key, InvestigationRequest, ProviderConfig)` atomically reuses parent packet admission and creates an explicitly requested child draft job. `get(actor, case, draft_run)` rechecks current requester/case/source scope; worker methods require the existing purpose-bound token and fenced claim.
- Simulation is disabled by default; real provider configuration/credentials/egress are not supported or approved. Inputs contain no client-supplied scores, provider-selected case IDs, arbitrary tools, URLs or SQL. Output is an immutable, explicitly simulated, structurally checked draft with server-rendered facts and mandatory human semantic review. [Contracts, limits and remaining live-provider gates](PHASE3_5_2_LLM_INVESTIGATOR.md).
