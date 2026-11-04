# Phase 3.4 - Human source and evaluation approval dossier

**Status: PROPOSED; no source approved, no official corpus published, no reviewer labels accepted.** The user approved November 2, 2026 as a clearly historical development boundary, with knowledge cutoff November 4. That scope approval does not approve these sources or their applicability.

## Exact review identity

| Artifact | SHA-256 |
|---|---|
| [Source proposals](../contracts/regulatory_source_proposals.json) | `832f42eafdc27a1e7847a8acf21c4b0615c8ca129f3117df969ec116fefc84c1` |
| [Evaluation proposals](../contracts/regulatory_evaluation_proposals.json) | `1eab4b7feba0d4a1f0a74d711999b51e028c209f9412b04ec20b8cab344c1801` |
| eCFR original dated XML | `2588950c5c16efb45a2a78369e08bda2174bf9a8be5afd634235a406f51924bb` |
| eCFR full extracted text | `c683ac7561aabaee6e8776dec4da92752725478577a7ff609524b4eeb4690b34` |
| FinCEN original HTML | `c6a9c857bfc6bfc3a5f22049949bb3b6f190f66440e8978e5a185583dbaab50e` |
| FinCEN full extracted text | `321f20f88411b6b376ddaf2e2e2775d86ad054f4bc3ec8710cdf4088f19ed13f` |
| eCFR Title 31 freshness metadata | `68fc6606201b8cccb96a285deb00555edd5a99f02925d99a88e6eada2d644d61` |

Hashes identify these exact bytes, not future downloads from mutable official URLs. Parser: `trueflag.reference-parser.v1`. Extracted-text coordinates are UTF-8 byte offsets in the stored normalized full extraction; source locators identify complete sections. Per-section hashes and locators are in the source proposal.

## Proposed coverage and publication disposition

| Source | Complete selected sections | Temporal support | Requested review |
|---|---|---|---|
| [Official eCFR XML, 31 CFR Part 1020, dated November 2](https://www.ecfr.gov/api/versioner/v1/full/2026-11-02/title-31.xml?chapter=X&part=1020) | 1020.210; 1020.320, including exceptions and nested paragraphs | Official dated snapshot; [Title 31 metadata](https://www.ecfr.gov/api/versioner/v1/titles.json) verified through November 2. Exact commencement/publication dates remain unknown | Review provenance, rights, bank applicability, selected scope and exact hashes; eligible for that date only after approval |
| [Official FinCEN SAR FAQs](https://www.fincen.gov/resources/frequently-asked-questions-regarding-fincen-suspicious-activity-report-sar) | Intro; FAQ 1 critical items, 6 corrected/amended, 11 recordkeeping, 16 continuing SAR | Historical validity/issuance not established for the whole page; dates remain null | Review-only candidate; **exclude from publication** until dated validity is established |

- eCFR original: 71,712 bytes, 24 full sections parsed; only the two listed sections proposed. FinCEN: 78,778 bytes, intro plus 23 FAQ chunks parsed; five chunks proposed. No replacement characters or C1 controls detected in extraction.
- Local full-text review copies: `assets/local/regulatory/proposed/ecfr-us-banks-review.json` and `fincen-sar-faqs-review.json`. Originals and acquisition metadata are beside them. They are ignored, private, and not committed; no document text is substituted when unavailable.
- Source-use rights remain pending human review. This is not a complete BSA corpus: statutory authority, cross-referenced Chapter X requirements, regulator-specific provisions and independent bank applicability are not fully covered. Binding regulations and FAQ guidance remain distinct; RF routing policies are never legal authority.

## Evaluation approval package

- Seven proposed positive questions cover SAR, AML program, exceptions and four FAQ topics. Twelve proposed negative/adversarial cases cover scope, dates, supersession/withdrawal, exceptions, embedded instructions, forgery, unauthorized access, empty/ambiguous retrieval and unapproved guidance. **All 19 require human label review.** FinCEN positive questions cannot run as approved-authority acceptance while that source is excluded.
- Human reviewer must confirm relevant complete sections, authority class, temporal/applicability limitations and expected abstention behavior, and record identity/time plus the approved source/evaluation hashes. Changes require a new proposal hash and renewed review. No application user is impersonated as a human reviewer.
- Precision@5 uses denominator five, Recall@5 uses reviewed relevant sections, ranking uses MRR; measure local p50/p95 wall latency and filter violations. No production performance target or legal-quality threshold is invented.
- Controlled synthetic PostgreSQL tests measure parser/retrieval/security behavior separately. They do not satisfy reviewed real-corpus retrieval acceptance. Official quality metrics remain **not measured / approval blocked**, rather than zero or passing.

## Approval boundary

Next human action: approve or revise the exact eCFR source proposal and relevant evaluation labels; leave FinCEN unpublished unless dated validity is independently established. Then an authorized curator must admit the reviewed bytes, obtain their persisted version/release manifests, explicitly approve the release and grants, and run measured reviewed-case evaluation. Source proposal approval alone does not silently publish/configure a runtime corpus or start Phase 3.5.
