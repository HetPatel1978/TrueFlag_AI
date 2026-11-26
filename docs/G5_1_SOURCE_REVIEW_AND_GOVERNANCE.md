# G5.1 — Regulatory source review and governance

## 1. Publication status

- **No official source approved or published.** No new official document was acquired in G5.1; frozen source bytes, earlier approvals, proposal files and blank independent labels are preserved.
- Scope remains the previously authorized **historical November 2, 2026** U.S.-bank / English context, with knowledge cutoff November 4 in America/New_York. It is not current-law coverage as of November 16.
- Source identity, parser integrity and retrieval success do not establish legal applicability, reviewer expertise, rights or a customer violation.

## 2. Frozen source inventory

| Source / official publisher | Canonical URL / version | Authority and dates | Current disposition |
|---|---|---|---|
| OFR/GPO eCFR: selected complete bank AML/SAR provisions | [Dated Part 1020 XML](https://www.ecfr.gov/api/versioner/v1/full/2026-11-02/title-31.xml?chapter=X&part=1020); §§ 1020.210 and 1020.320 | Informational compilation of underlying binding regulations. Snapshot and verified-through 2026-11-02; acquired 2026-11-04. Composite publication/effective dates remain null. | Proposed; eligible for qualified review of that historical snapshot only. Not approved. |
| FinCEN SAR HTML FAQs | [Frozen HTML page](https://www.fincen.gov/resources/frequently-asked-questions-regarding-fincen-suspicious-activity-report-sar); context + FAQs 1/6/11/16 | Nonbinding guidance. Acquired 2026-11-04; whole-page issuance/effective interval and historical continuity unknown. | **Excluded from publication** pending dated validity and independent review. |
| FinCEN/Federal Reserve/FDIC/NCUA/OCC October 2025 SAR FAQs | [Research-only PDF](https://www.fincen.gov/system/files/2025-10/SAR-FAQs-October-2025.pdf); questions 1–4 | Nonbinding guidance; stored issuance evidence 2025-10-09. Acquisition 2026-11-05 03:51:23.098334 UTC = November 4 New York. Effective interval and subsequent validity unreviewed. | Research-only; production parser does not support PDF. Not admitted or approved. |

| Exact original bytes | SHA-256 |
|---|---|
| eCFR XML | `2588950c5c16efb45a2a78369e08bda2174bf9a8be5afd634235a406f51924bb` |
| FinCEN HTML | `c6a9c857bfc6bfc3a5f22049949bb3b6f190f66440e8978e5a185583dbaab50e` |
| FinCEN dated research PDF | `5ed61b76f65ca1640f2d40e1afe3db40c77622620e81aefd08bc5273e0de4cac` |

- Full extracted identities, locators, section hashes, publication/effective-date uncertainties and earlier amendment research remain in `contracts/regulatory_source_proposals.json`, `contracts/regulatory_provisional_answer_keys_v2.json`, `docs/PHASE3_4_SOURCE_APPROVAL_CHECKLIST.md` and `docs/PHASE3_4_REVIEWER_GUIDE.md`.
- G5.1 rechecks the existing staged bytes; it does not assert these mutable URLs still serve identical content or independently establish present-day law. Replace/retrieve a document only under a new version/review identity.
- No complete BSA corpus exists. Statutory BSA coverage, full Chapter X/CDD cross-references, institution-specific regulator rules, amendment chains and withdrawal/supersession research remain incomplete. Missing sources must be recorded, never synthesized.

## 3. Source approval requirements

1. Qualified independent AML/legal reviewer checks exact original/extracted/section hashes, publisher, official status, use rights, institution/charter/regulator, binding versus nonbinding classification, full provisions/exceptions and cross-references.
2. Establish publication, effective and historical intervals from evidence; preserve unknown dates. Original eCFR/HTML precise HTTP fetch times were not captured. Fixed fixture timestamps remain test observations; they cannot replace actual acquisition provenance. A distinct, verifiable curation event needs explicit reviewer acceptance before publication.
3. Record reviewer identity/qualifications/conflicts, review time, conclusions, applicability notes, missing coverage and amendment/supersession/withdrawal findings in a private dossier bound to the exact version manifest. Retain its SHA-256.
4. Existing internal `approve_version` now requires an official-source approver account distinct from `admitted_by`, plus `Approval.review_reference_sha256`. The dossier hash is written into immutable audit metadata. Same-account approval or missing reference fails closed. Synthetic test approvals remain test-only.
5. Separate explicit release-manifest approval, access grants and server context selection remain required. No reviewer label, metric, source acquisition or context envelope executes this sequence automatically.

Account separation and a hash **do not authenticate expert qualifications or prove dossier authenticity**. They are minimum application controls around a trusted operator process. Independently signed approvals, verified identity/qualification registries, least-privilege SQL roles and external immutable audit retention remain release work. No database roles or credentials are changed here. Existing approval records are not rewritten.

## 4. Independent benchmark review

- New `backend/app/evaluation/regulatory_review.py` and `scripts/regulatory_review_workflow.py` extend the earlier 31-case review package; no second retrieval engine.
- States: **Unreviewed → Reviewer-labeled → Disputed (when needed) → Adjudicated → Approved for evaluation**. Differing submissions automatically preserve a dispute; only independent adjudication resolves it.
- Every event binds the benchmark, original blank review packet, provisional source registry and exact source-version hashes through the manifest digest, plus the approved reviewer-registry digest. Source/scope/registry edits invalidate the old binding and require a new review identity.
- Separate reviewer, adjudicator and evaluation-owner actors are required for each approved case. The original reviewer cannot adjudicate or approve their own label. Roles and qualification references must match the external registry; excluded authors/model identities are rejected.
- `contracts/regulatory_reviewer_registry_v1.json` starts empty/unapproved. A qualified human owner must approve a private copy; this phase supplies no human identities, independent labels or approvals.
- Submission fields: relevance, exact `source:section` set, preferred ranking, expected availability, authority classes, institution applicability, missing sources, citation support, exceptions, abstention, contradictions and rationale. Unknown sources cannot masquerade as known citations; describe missing sources separately.

## 5. Operator commands — no publication

```text
python scripts/regulatory_review_workflow.py prepare --output runtime/<private>/review-packet.json
python scripts/regulatory_review_workflow.py record --registry <approved-private-registry.json> --journal runtime/<private>/journal --submission <independent-submission.json> --output runtime/<private>/status-001.json
python scripts/regulatory_review_workflow.py status --registry <approved-private-registry.json> --journal runtime/<private>/journal --output runtime/<private>/status.json
python scripts/regulatory_review_workflow.py evaluate --registry <approved-private-registry.json> --journal runtime/<private>/journal --observations <version-bound-observations.json> --output runtime/<private>/evaluation.json
```

- Run commands only in an owner-restricted local directory. Outputs are exclusive-create, never overwrite old events or submitted work. The next numbered event path prevents two concurrent writers from creating accepted forks; partial files or broken chains fail closed and need operator recovery.
- Strict JSON limits: 4 MiB per intake artifact, 64 KiB per event, 16 MiB total journal, 500 events maximum, bounded typed fields; stale/future ordering is not inferred from machine wall time. Submission times must be aware and nondecreasing within the journal. They are reviewer assertions, not trusted server clocks.
- Local hashes are tamper evidence, not signatures or WORM storage. Operator authentication, registry authorization and reviewer identity validation are procedural; this CLI is not a public approval API. Preserve original submissions, roster, events and adjudication dossiers privately.
- Expert metrics remain null until all 31 cases have legitimate independently adjudicated and evaluation-approved human labels. Synthetic protocol fixtures can exercise transitions but cannot produce expert-reference metrics. Source publication remains a separate gate regardless of review state.

## 6. Residual source-governance gates

- Qualified human review, rights, original timestamp precision, dated amendment/effective intervals and institution applicability.
- FinCEN HTML historical validity; research PDF production parsing and reviewed validity.
- Complete statutory/CDD/regulator-specific coverage and documented conflict handling. The system does not resolve legal interpretation conflicts by ranking alone.
- No malware scanner, external identity attestation, signed source approvals or legal certification. No live LLM/RAG publication is activated.
