# Phase 3.4 - Regulatory knowledge and controlled lexical retrieval

Implementation contract recorded before migration, starting at `546e61f` on 2026-11-04. User-confirmed scope: United States / U.S. bank / English / BSA-FinCEN reference context / **historical legal as-of 2026-11-02**, knowledge cutoff 2026-11-04. No LLM, provider, embeddings, frontend or consequential case action.

## Publication and validity gates

- Proposed sources are **not approved**. Complete 31 CFR 1020.210 and 1020.320, plus HTML FinCEN SAR FAQs, are candidates. Official [eCFR Title 31 metadata](https://www.ecfr.gov/api/versioner/v1/titles.json) reported `up_to_date_as_of=2026-11-02`; November 4 validity cannot be asserted. Dated section HTML redirects were rejected. Fixed dated official XML initially returned 406; negotiating gzip and bounded decompression succeeded. No third-party substitute or PDF is accepted.
- An official FinCEN FAQ HTML snapshot and eCFR metadata are privately staged in ignored `assets/local/regulatory/proposed/`. SHA-bound source proposals, extracted sections, applicability/dates/rights and proposed evaluation labels require human review. No legal retrieval-quality success is inferred from synthetic fixtures.
- Human source approval and explicit corpus-manifest approval are separate from acquisition. Publication rejects unapproved versions or an unestablished temporal basis. Retrieval excludes insufficiently current, future-published and inapplicable versions before ranking; source/release withdrawal remains authoritative on search and citation resolution.
- The [approval dossier](PHASE3_4_APPROVAL_DOSSIER.md) binds exact source and evaluation proposal hashes. A dated eCFR snapshot establishes text for that day only, not an invented commencement/publication date. Unknown dates remain null and are cited as limitations. FinCEN historical validity remains unestablished and cannot pass approval until reviewed.

## Selected minimum additive schema

Ten tables: `reference_sources`, `reference_documents`, `reference_versions`, `reference_chunks`, `reference_approvals`, `corpus_releases`, `corpus_members`, `reference_contexts`, `reference_grants`, `reference_events`.

- Registry/document/version/chunk, approvals/releases/membership/context and lifecycle events are immutable; grant active state/revision may change with immutable audit. UUIDs, same-document/version FKs, unique release/document and exact chunk locators; bounded original UTF-8 bytes and extracted text with separate SHA identities.
- Complete section chunks preserve headings, nested paragraphs, exceptions and notes. PostgreSQL GIN full-text index uses a fixed English configuration; exact section lookup is separate. Binding regulation/statute/guidance/internal-policy classes remain distinct; RF routing policies are rejected and internal policies are excluded from this MVP retrieval context.
- Existing Case, evidence, assessments and scientific contracts are unchanged. Reuse active actor/case locks, shared API budget, value-free errors, atomic audit and private staging boundaries.
- Empty downgrade is supported; retained corpus/source/approval/event/read-audit history blocks destructive downgrade. PostgreSQL fixtures verify fresh head, 0012 upgrade/empty rollback, preservation and no schema drift; SQLite is compatibility only.

## Controlled intake and retrieval

- Runtime intake is curated local XML/HTML/plain text only: no fetch, redirects, uploaded filenames, arbitrary URL/path, PDF/Office or binary execution. Canonical publisher metadata must use an exact approved HTTPS host with no credentials/custom ports; source hashes and a human manifest bind provenance. A host name/hash does not itself prove authenticity, rights or applicability. Malware scanning remains unavailable.
- Publication and grants are internal admin-curation operations, unavailable to read APIs. Synthetic test text/approvals are accepted only in an explicit test environment and are always marked as fixtures without legal authority. They never replace unavailable official regulations.
- Server-selected immutable context binds jurisdiction/entity/language/as-of/knowledge cutoff and approved corpus release. Clients/LLMs cannot override scope. Current case permission, context grant, source/version/release access, publication and effective-date predicates precede ranking and limits.
- Context grants authorize the complete approved legal-source bundle. This MVP does not implement separate per-source/per-tenant reader ACLs for future proprietary internal policies; those policies remain excluded from retrieval.
- Top five default, bounded plain lexical queries and exact section lookup; deterministic score/section/UUID tie-breaking. No generic tool executor or pagination outside the small result bound. Citations resolve only through the same current authority and exact immutable release/version/chunk.
- Sensitive search/citation audit commits before disclosure; raw query text, source text and customer information are not logged. Retrieved malicious instructions remain untrusted text, never executable instructions.

## Acceptance status

**Technical implementation: PASS for local development. Official corpus publication and reviewed legal retrieval quality: BLOCKED pending human review.** No actual regulation or guidance has been approved/published. Actual official bytes were admitted and hash-verified only inside disposable PostgreSQL acceptance schemas, without approvals or disclosure. No application deployment or live-schema migration was performed.

## Implementation map and APIs

| Component | Files / responsibility |
|---|---|
| Additive persistence | `backend/app/models/references.py`, migration `0013_reference_corpus.py`; 10 tables, immutable history and expression GIN |
| Typed scope / citations | `backend/app/schemas/references.py`; fixed historical scope, five passages, authority labels, exact UTF-8 locators |
| Curated extraction | `backend/app/services/reference_parser.py`; explicit host validation, bounded complete-section XML/HTML/plain text, no runtime network |
| Curation / reads | `backend/app/services/references.py`; expected-hash source approval, release approval, access grants, lifecycle events, current authorized lexical reads |
| Minimum API | `backend/app/api/references.py`; case-scoped search and citation resolution only |
| Evaluation | `backend/app/services/reference_evaluation.py`, proposed manifests in `contracts/`; measured fixtures separate from unreviewed legal labels |
| Acceptance | `backend/tests/test_reference_parser.py`, `backend/tests/test_references.py`; real PostgreSQL plus compatibility checks |

- `POST /api/v1/cases/{case_id}/references/search`: exactly one `query` (1-256 chars, <=40 words) or `section` (1-120 chars), optional strict integer `limit` 1-5. No client scope/release/actor/URL override. Empty/ambiguous/unavailable/outdated/withdrawn/inapplicable are typed outcomes, not fabricated passages.
- `GET /api/v1/cases/{case_id}/references/{reference_id}`: resolve current authorized immutable citation, or hidden 404 after forgery, case/grant revocation, withdrawal or supersession. References identify shared legal context, never confer case access.
- Shared authenticated budget, four per-process read slots, 12 KiB JSON body, <=256 KiB result, statement/lock/idle transaction limits and immutable hashed read audit apply. 401 anonymous; 404 inaccessible; 413 oversized; 415 media; 422 malformed; 429 capacity; sanitized 503 integrity/unavailable errors. No new upload or curator HTTP endpoints.
- Default `REGULATORY_CONTEXT_ID` is unset. Authorized retrieval then returns `unavailable`; unauthorized cases still return 404. Publishing a corpus does not configure production or grant readers implicitly.
- Minimum internal sequence: `register_source -> admit -> inspect version manifest -> approve_version -> proposed_release -> publish -> grant -> server configuration`. A trusted human approval must cover provenance, rights, scope, dates, complete exceptions and the exact hash. No real human approvals have been executed here.

## Reliability and remaining boundaries

- Existing actor/case row locks plus context locks serialize sensitive read disclosure against curation/revocation. Curation is serialized using a PostgreSQL advisory transaction lock; duplicate manifests are idempotent. Audit failure rolls back the operation and prevents disclosure. Successful disclosure is linearized at transaction completion.
- An approved applicable later version invalidates earlier versions even across an intervening stale version and an older release: fail closed until a new release is explicitly approved. Versions acquired after the historical knowledge cutoff cannot invalidate that history. Withdrawal never rewrites history. Grant revocation preserves the original grant identity and immutable change audit.
- Shared context locking serializes this small MVP corpus's readers; registry <=100 sources, <=100 versions/document, release <=50 documents/1,000 chunks. Citation resolution scans at most 1,000 eligible chunks. This is bounded development infrastructure, not demonstrated enterprise throughput.
- The app SQL principal can perform trusted direct inserts; triggers prevent ordinary updates/deletes/truncates, not superuser tampering. Least-privilege SQL roles, independently signed approvals, external audit retention and tenant governance remain deployment work. No malware scanner, semantic search, scheduler or freshness watchdog was added.

## Repeatable verification

```powershell
.venv\Scripts\python.exe -B scripts/verify_reference_proposals.py
.venv\Scripts\python.exe -B scripts/run_assessment_verification.py --references-only
.venv\Scripts\python.exe -B scripts/run_assessment_verification.py --full-backend --reference-report
```

The first command needs ignored official review assets; it validates hashes and explicitly cannot approve sources. PostgreSQL tests use disposable schemas and synthetic legal-like text, marked `synthetic_test` and accepted only in `APP_ENV=test`. No synthetic corpus is published into the application database.

## Actual verification - 2026-11-04

Counts below are distinct runs, not additive totals across overlapping suites.

| Environment / check | Passed | Failed | Skipped | Evidence |
|---|---:|---:|---:|---|
| Full pinned Linux/PostgreSQL backend | 736 | 0 | 0 | 568.91 s; 14 recovery scenarios PASS; before final narrow hardening additions |
| Final Linux/PostgreSQL references | 87 | 0 | 0 | 46.59 s; final code, actual official intake, multi-generation supersession, knowledge cutoff, UTC and publisher-bound manifests |
| Native Windows/PostgreSQL relevant backend | 237 + 5 | 0 | 0 | 131.81 s broad suite, then 3.56 s final official-intake/supersession/manifest checks |
| SQLite compatibility runs | 428 + 2 | 0 | 311 + 2 | 258.01 s broad suite; two final manifest units passed and two opt-in PostgreSQL cases explicitly skipped |
| Pinned Linux ML unit/regression tests | 178 | 0 | 0 | Actual private fitted artifacts; no replacement mocks |
| Frozen RF / policy / SHAP | 4,000 / 12,000 / 4,000 | 0 mismatches | 0 | RF maximum absolute error 0; SHAP residual 3.1086244689504383e-15, original encoded/grouped/base deltas 0 |

- Fresh/0012 roundtrip migration, retained-history downgrade refusal, no PostgreSQL schema drift, full 46-table SQLite compatibility and preservation of existing fixture users verified. Immutable update/delete/truncate guards, approval/hash conflicts, duplicate publication, current case/grant/role revocation, forged/foreign references, source/version/release withdrawal and audit rollback verified.
- Actual official XML/HTML bytes, full extraction hashes and eCFR freshness metadata reverified with `verify_reference_proposals.py`; actual intake produced unapproved versions only in isolated tests. All 25 frozen private asset hashes and all seven initial branding/startup file hashes unchanged.
- Ruff lint/format, publication ignore boundaries and host/pinned Linux dependency consistency passed. Existing Starlette/httpx deprecation warning remains. No new dependency, teammate modification, private asset commit or GitHub push.
- Initial focused run: 75 passed / 1 failed because a test used a forbidden role value. Corrected to a permitted admin-to-analyst demotion; production authorization was unchanged. Final review additionally rejected incomplete HTML and corrected non-immediate supersession/knowledge-cutoff handling; retrieval timestamps were normalized to UTC before hashing and registry key/publisher/host bound into the version manifest; final affected-suite checks passed.

## Measured retrieval evaluation

| Measurement | Controlled fixture result | Official reviewed legal corpus |
|---|---|---|
| Cases | 4 (2 positive, 2 empty/ambiguous) | 7 positive + 12 negative/adversarial proposals; reviewer labels pending |
| Precision@5 / Recall@5 / MRR | 0.20 / 1.00 / 1.00 | Not measured; approval blocked |
| Filter violations / expected-empty failures | 0 / 0 | Not measured |
| Service latency p50 / p95 | Final focused run 11.77 / 19.16 ms; earlier full-suite run 12.67 / 1,513.54 ms | Not measured |

Precision uses denominator five even when only one passage is relevant; empty slots are not silently discarded. These four synthetic queries and different observed runtimes are not a capacity benchmark, legal-quality certification or production SLO. Source authenticity/rights, section applicability and semantic relevance require independent human review. No generated legal/customer findings are produced.

## Local deployment boundary and next action

- Read-only local check: running backend `/ready` returned 200, live database remains `0012_evidence_foundation`, no regulatory context selected. Existing demo services and records were left intact. Migration 0013 and new APIs were verified in isolated environments; restart/rebuild and migrate through the existing Compose setup when deploying this code.
- Next human action is review of the [exact-hash source/evaluation dossier](PHASE3_4_APPROVAL_DOSSIER.md). Publication, explicit access grants, server context selection and reviewed real-corpus evaluation must finish before claiming Phase 3.4 regulatory acceptance. FinCEN remains excluded until validity is established. Phase 3.5 has not started.
