# Phase 3.4 - Source-by-source human approval checklist

**HUMAN GATE: no approvals or publication.** Scope: U.S. bank / English / historical 2026-11-02; knowledge cutoff 2026-11-04. Integrity and retrieval tests cannot establish legal applicability or independent relevance.

## 1. Frozen document identity

| Candidate | Publisher / exact canonical acquisition URL | Retrieved version / SHA-256 |
|---|---|---|
| eCFR bank provisions | OFR/GPO government service; [dated Title 31 Part 1020 XML](https://www.ecfr.gov/api/versioner/v1/full/2026-11-02/title-31.xml?chapter=X&part=1020) | Dated 2026-11-02; locally acquired 2026-11-04; 71,712 bytes. Original `2588950c5c16efb45a2a78369e08bda2174bf9a8be5afd634235a406f51924bb`; full extraction `c683ac7561aabaee6e8776dec4da92752725478577a7ff609524b4eeb4690b34` |
| FinCEN SAR FAQs | FinCEN/Treasury; [canonical HTML FAQ page](https://www.fincen.gov/resources/frequently-asked-questions-regarding-fincen-suspicious-activity-report-sar) | Mutable HTML retrieved 2026-11-04; 78,778 bytes. Original `c6a9c857bfc6bfc3a5f22049949bb3b6f190f66440e8978e5a185583dbaab50e`; full extraction `321f20f88411b6b376ddaf2e2e2775d86ad054f4bc3ec8710cdf4088f19ed13f` |

- Parser: `trueflag.reference-parser.v1`; complete section hashes and exact UTF-8 locators are frozen in [source proposals](../contracts/regulatory_source_proposals.json), SHA `832f42eafdc27a1e7847a8acf21c4b0615c8ca129f3117df969ec116fefc84c1`.
- eCFR Title 31 freshness metadata SHA `68fc6606201b8cccb96a285deb00555edd5a99f02925d99a88e6eada2d644d61` records verification through November 2, not November 4. Do not replace frozen bytes with a new download under the same identity.
- Original HTTP fetch timestamps were not captured precisely; only acquisition date is established. Fixed timestamps in test fixtures are explicitly test observation metadata, not reconstructed historical HTTP timestamps.
- Review copies and originals remain in ignored `assets/local/regulatory/proposed/`. Exact URL/hash proves neither rights nor legal force. No source text or PDF is newly admitted by this checklist.

## 2. Provision-level approval checklist

| Review item | 31 CFR 1020.210 | 31 CFR 1020.320 | FinCEN SAR FAQs |
|---|---|---|---|
| Classification | Underlying binding regulation; eCFR is an informational compilation | Underlying binding regulation; eCFR is an informational compilation | Nonbinding guidance; no regulation status inferred |
| Relevant complete coverage | Paragraphs (a)/(b), AML program requirements for banks with/without a Federal functional regulator | (a)-(g): reporting scope, filing, exceptions, retention, confidentiality, liability and compliance | Intro and full FAQs 1, 6, 11, 16; guidance topics only |
| Exceptions / context | Review both bank categories and incorporated cross-references, including 1010.610/.620 and CDD references | Preserve (c) exceptions plus all conditions, confidentiality restrictions and surrounding paragraphs | Review each whole answer and intro; do not detach qualifications or treat UI field instructions as legal obligations |
| Publication evidence | Stored section cites 85 FR 57137, 2020-09-15; supplemental final rule below | Stored section cites 75 FR 65812, 2010-10-26; amended at 76 FR 10517, 2011-02-25 | Page identifies four additional FAQs issued 2025-10-09; does not establish publication date of the whole page |
| Effective / historical dates | Dated snapshot only. Individual 2020 rule dates are known below; complete 2026 composite interval remains unadjudicated | Dated snapshot only; cited amendment publication dates are not effective dates. Effective/amendment chain remains reviewer work | Whole-page effective/issuance interval and historical validity unknown; null dates retained |
| U.S. banking applicability | Confirm actual charter, regulator and which paragraph applies; title alone is insufficient | Confirm reporting entity definition, transaction scope, exceptions and parallel regulator rules | Financial-institution guidance is not automatically applicable to every bank case or historic period |
| Amendment history | Cross-check the cited rule and all later relevant amendments/LSA through 2026-11-02 | Verify 2010/2011 references and all later relevant amendments/LSA; retrieval of complete 2011 HTML was unavailable during this gate | Check archived dated versions, amendments/replacements and issuance context; no continuity inferred from a mutable page |
| Current disposition | **Eligible for qualified human review; not approved or publication-ready** | **Eligible for qualified human review; not approved or publication-ready** | **Excluded from publication until historical validity is independently established** |

The [OFR/GPO legal-status explanation](https://www.ecfr.gov/reader-aids/understanding-the-ecfr/what-is-the-ecfr) describes eCFR as an editorial informational compilation and directs legal researchers to verify against official CFR editions, the Federal Register and LSA. The `binding_regulation` label describes the underlying provision; it does not certify the electronic compilation as an official legal edition.

Supplemental, unadmitted primary evidence: [GovInfo final rule 2020-20325](https://www.govinfo.gov/content/pkg/FR-2020-09-15/html/2020-20325.htm) was published 2020-09-15, states an effective date of 2020-11-16 and a compliance date of 2021-03-15 for the covered banks lacking a Federal functional regulator. These are **that rule's dates**, not invented commencement dates for every paragraph in the 2026 compilation. They do not silently populate the frozen source-version dates or approve it.

## 3. Required human actions and recording

- [ ] Qualified AML/legal reviewer identifies the exact institution/charter/regulator, permitted purpose, authority classification, complete provisions, cross-references, exceptions, rights and amendment/effective-date evidence.
- [ ] Accept, revise or reject each source against its exact original/extracted/section hashes. Keep FinCEN excluded while validity is unresolved; explain any coverage limitations and required abstention. No complete BSA framework is claimed.
- [ ] Resolve source-version timestamp provenance/precision before publication: precise original HTTP timestamps are absent. Supply a verifiable acquisition/curation event with its distinct meaning and approved knowledge cutoff, or explicitly review the interface needed for date-only precision. Never reuse fixed test timestamps as real provenance.
- [ ] Independent relevance reviewer labels all 19 cases in the [blank packet](../contracts/regulatory_independent_review.json), SHA `e3d8c4e4500e12c8fa8357b6121973b23cbbe3bf96e327397c1210378d184f1c`. All reviewer fields are null; engineering hints remain separate in the existing proposal file.
- [ ] Work in a private copy under ignored `assets/local/regulatory/reviews/`, not in the committed blank template. Record identity, qualifications, UTC review time, relevant `source-key:section` sets, authority, expected availability, rationale and disagreements; adjudicate before adopting ground truth. Do not commit reviewer PII.
- [ ] Bind final labels/approval to source/packet hashes and scope. Any source, parser, scope or label change creates a new review identity. Approve retrieval acceptance criteria after reviewing the dataset; no quality threshold is invented here.
- [ ] Only then authorize a curator's exact source-version and release manifests, permitted grants and server context; run reviewed acceptance before publication. Approval is not a customer violation finding, case disposition or SAR action.

## 4. Requirements traceability / residual gates

| Phase 3.1 requirement | Gate evidence / unresolved action |
|---|---|
| Controlled official-source provenance and immutable identity | Exact hashes verified; original and complete sections preserved; provenance/rights still require human approval |
| Jurisdiction, institution, dates, authority and exceptions before ranking | Private candidate SQL reuses production applicability/ranking predicates; wrong-scope/date controls passed; actual applicability and amendment chain remain unadjudicated |
| Independent relevance and authority labels | 19 concrete procedures, **zero independent labels**; diagnostic metrics are engineering-hypothesis measurements only |
| Approved-only, case-authorized citations and tool reads | Actual API and reusable service deny unapproved versions; forged version/context identifiers fail. No future investigator exists; future tools must reuse this boundary and never register the private test query |
| Immutable history, concurrency, withdrawal and rollback | Existing reference security suite rerun on the recovery clone; no official approvals/releases. Test-only supersession exclusion is separately labeled and is not proof of a real legal amendment |
| Recovery and no automatic live changes | Protected PostgreSQL archive restored twice; migration upgrade/empty rollback/re-upgrade/history refusal and legacy integrity verified on copies; live schema unchanged |
| Broader governance | No malware scanner, production legal certification, tenancy/least-privilege SQL-role acceptance, approved provider, LLM or Phase 3.5 implementation |

Stop at this human approval gate. [Measured acceptance and limitations](PHASE3_4_APPROVAL_ACCEPTANCE.md).
