# G5.1 — Regulatory frontend and investigator integration contract

## 1. Implemented versus proposed

| Existing / implemented | Proposed after explicit approval |
|---|---|
| Case-scoped reference search/citation APIs, backend authorization and immutable audits. | Regulatory Guidance panel within the existing case workbench. |
| New internal typed, source-revalidated regulatory-context envelope. | G4 investigator adapter consuming that envelope after source/publication and provider gates. |
| Owner-operated offline source/benchmark review artifacts. | Authorized source-review UI only after dedicated backend review/curation APIs exist. |

**No frontend feature, source-review HTTP endpoint, live model call or investigator prompt change is introduced.** Existing APIs provide approved reader context; they cannot support a curator approval screen. Inventing such a screen would misrepresent the approval boundary.

## 2. Existing reader API contracts

| Operation | Contract |
|---|---|
| `POST /api/v1/cases/{case_id}/references/search` | Existing authenticated body: exactly one bounded `query` or `section`, optional strict `limit` 1–5. Server selects historical scope, corpus and actor. |
| `GET /api/v1/cases/{case_id}/references/{reference_id}` | Existing authenticated citation resolution; rechecks current case/context grant, publication, applicability and source/version/release lifecycle. |
| Result | `ReferenceResult`: available/empty/ambiguous/unavailable/outdated/withdrawn/inapplicable; immutable context/release/hash, ≤5 full-section citations and limitations. |
| Errors | 401 anonymous; 404 inaccessible case/grant/citation; 413 oversized; 415 media; 422 malformed; 429 capacity; sanitized 503 integrity/unavailable. No client scope, arbitrary URL, provider or source-approval override. |

Reference source IDs are shared legal-document identities, not proof of case authorization. Resolve them through case-scoped endpoints on each disclosure. No query/body/customer features are logged; existing hashed read auditing commits before disclosure.

## 3. Dormant investigator handoff

- `backend/app/schemas/regulatory_context.py`: `RegulatoryContext` version `trueflag.regulatory-investigation-context.v1`.
- `ReferenceService.validate_regulatory_selection(actor_id, case_id, tuple[Citation, ...])`: internal service only, ≤5 unique selections. Reuses existing predicates, locks and integrity verifier; compares every supplied citation field to current stored approved data.
- Each passage carries source ID/key, publisher/title/URL, exact section/locator/excerpt and byte/hash identity, approved version/manifest, release/context identity, review identity/dossier hash, authority, historical applicability, dates and limitations. Synthetic fixtures are explicitly marked and remain unavailable in ordinary official runtime contexts.
- Case identity and the exact ordered result/provenance payload bind the context digest. The digest is not authorization, a signed legal opinion or a replacement for final source/permission revalidation.
- Source/context/assignment withdrawal, supersession, forged identifiers, altered excerpts, scope/version mismatch or audit failure prevents return. Both read and selection audit writes share one PostgreSQL transaction; no partial handoff survives failure.
- Text is `untrusted_reference_data`; `can_execute_instructions=false`, `can_establish_customer_violation=false`, and `must_revalidate_before_publication=true`. Regulatory instructions are inert text, not model/tool instructions. No actual LLM injection resistance is measured here.
- Empty, uncertain or unavailable retrieval must preserve abstention/limitations; do not construct citations or invent applicable requirements. The caller may use the existing empty result but cannot validate an empty citation tuple as a successful handoff.
- Future G5.2 must revalidate all sources and permissions immediately before model dispatch and final publication, freeze evidence/assessment/context versions, fence revocation, and reject any model reference outside the server-supplied set. G5.1 does not connect this envelope to G4 or activate regulatory RAG.

## 4. Future workbench presentation

- Reuse `frontend/src/design-system.css`, `ui.tsx`, G2.2/G2.3 navigation, typography, focus states and responsive layout.
- Labels: **Regulatory Guidance**, **Supporting Regulatory Sources**, **Source Details**, **Effective Date**, **Guidance Requiring Review**, **Regulatory Context**. Use **Applicable Requirements** only with clear conditional scope and human-review wording; never imply a transaction violates a regulation.
- Display source authority separately from retrieval rank, and historical as-of separately from effective/publication dates. Render unknown dates as unavailable, not the acquisition date. Explain incomplete corpus coverage without fabricated summaries.
- Excerpts render as escaped text; never HTML/Markdown execution or instruction-bearing links. Official URL allowlists remain server-enforced.
- Unapproved content belongs only in a separately authorized review surface and must never look like validated analyst guidance. A reader with no approved corpus sees “Regulatory guidance unavailable — source review required,” not placeholder citations.
- Bounded searches, loading/empty/failure states, request cancellation and stale-response fencing. Clear source/case state after logout, 401/403/404, assignment/source revocation or context changes. No persistent customer/source caches.

## 5. Future UI acceptance

Before any frontend addition: actual approved synthetic/official runtime API integration, React tests and real Chromium coverage for authorized retrieval/citation details, empty/uncertain results, date/authority presentation, revocation/logout, forged URLs, inert injection text, error handling and accessibility. G5.1 has no changed UI requiring new Chromium tests; existing React/build checks are recorded in the foundation report.
