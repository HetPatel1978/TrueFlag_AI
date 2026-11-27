# Phase 3.4.1 - Independent regulatory review guide

**Unreviewed research preparation only. No source approval, publication, legal certification or LLM evaluation.** Review scope: U.S. banks, English, historical **2026-11-02**, knowledge cutoff **2026-11-04 America/New_York**. Actual starting HEAD was `a24cbd9`, which already contains the evidence-only coordinator; it is preserved.

## Review artifacts and independence

| Artifact | Role |
|---|---|
| `contracts/regulatory_benchmark_v2.json` | 31 unique proposed questions/controls, information needs, executable fixtures and group definitions |
| `contracts/regulatory_provisional_answer_keys_v2.json` | Engineering hypotheses, exact source versions/locators, proposed relevance, qualifications and unresolved questions; **not independent ground truth** |
| `contracts/regulatory_independent_review_v2.json` | Blank independent labels, identities, qualifications, timestamps and adjudication fields; bound to benchmark/research SHA-256 |
| Original three v1 contracts | Immutable historical 19-case baseline; never overwrite or normalize their bytes |

- Copy the blank template to ignored `assets/local/regulatory/reviews/`. Keep identities/qualifications private. Review complete sources before consulting provisional answers to reduce anchoring; disclose any prior exposure.
- Confirm actual expertise and conflicts. A qualified AML/legal reviewer must assess applicability and exceptions; a separate adjudicator resolves disagreements. Software tests and engineering authors do not impersonate either role.
- Record `source-key:section` labels, exact reviewed hashes, reviewer/qualification/UTC time, rationale and disagreement. All committed independent fields remain null until actual reviewer work exists. Do not put customer data in this benchmark.
- Record a new review identity when sources, parser, benchmark, labels or scope change. Partial review cannot be overwritten by the generator. A completed template does not itself approve a source or release.

## Source verification checklist

| Source | Required review | Present boundary |
|---|---|---|
| Dated eCFR 1020.210 / 1020.320 | Complete paragraphs, source notes, bank category, exceptions and incorporated Chapter X/Title 12 requirements; verify official CFR/Federal Register/LSA amendment/effective-date evidence | Informational compilation of underlying binding regulations; exact November 2 snapshot only; no legal approval |
| Frozen mutable FinCEN SAR HTML FAQs | Complete FAQ 1/6/11/16 and document context; individual update markers, older cited guidance, filing specifications and historical continuity | Nonbinding guidance; whole-page issuance/effective interval unknown; excluded |
| Separately dated October 9, 2025 FinCEN/interagency SAR FAQ PDF | Official PDF/landing hashes, complete Questions 1-4 and footnotes; reconcile overlapping continuing-activity content and later amendments | New **research-only**, nonbinding candidate; issuance established, composite validity unreviewed; no PDF admission/parser support |

The PDF acquisition was **2026-11-05 03:51 UTC**, which is **November 4 in New York**, within the explicitly local knowledge-cutoff date. This is a real acquisition timestamp, not its issuance or legal effective date. The original HTML snapshot is not replaced or redated. No malware scanner or PDF intake safety is claimed.

Exact raw, extracted and selected-section hashes/UTF-8 byte locators for existing sources are carried in the provisional answer file. The PDF has an exact original-byte hash and page/question/footnote locators, **no claimed production text extraction/section hashes**. Private complete copies remain under ignored `assets/local/regulatory/`.

## Grading rubric

| Dimension | Reviewer grading | Required distinction |
|---|---|---|
| A: relevance/ranking | Per complete source section: 2 directly answers the information need, 1 contextual, 0 irrelevant; record final relevant set and rationale | Decide the binary relevant set explicitly; contextual grade 1 is not automatically counted as relevant |
| B: authority/applicability | Binding regulation/statute/nonbinding guidance; institution category, as-of validity, effective/amendment evidence: supported / unsupported / unresolved | A matching title, issue date or hash does not establish applicability or legal force |
| C: citation support | Claim-by-claim: fully supported / partial / unsupported; confirm exact source, section, paragraph and qualifications | Valid source references do not prove that the proposed answer follows from them |
| D: abstention | Correct complete answer / correct partial answer with explicit gaps / required full abstention / unsupported answer | Missing cross-references, excluded guidance or case facts cannot be invented |
| E: security/control | Explicit fixture/pass-fail assertion; retain the measured operation and its limitation | Authorization/filter/forgery/parser tests are not legal relevance or future LLM injection tests |

For each question, verify the exact information need rather than a convenient keyword match. Preserve reporting exceptions, suspect-identification conditions, filing-clock triggers, confidentiality qualifications and differences between initial deadlines and optional continuing guidance. No benchmark response may decide a real case, assert criminality or submit a SAR.

## Metric and adjudication rules

- Precision@5 = unique relevant returned **source:section** keys / 5, including missing slots. Recall@5 = relevant returned keys / complete relevant set, including proposed excluded sources; MRR uses the first relevant rank. Report population and label basis alongside each metric.
- The 7 original queries remain unchanged for a diagnostic comparison, but v2 proposed relevant sets may expand (notably retention). Do not misrepresent a label change as a ranking improvement. Controls are excluded from relevance denominators. Groups A-E overlap; never sum them into 31 twice or produce an unsupported aggregate acceptance score.
- Report lexical misses, legitimate unavailable coverage and partial coverage separately. Runtime unapproved-source withholding is separate from candidate diagnostics that intentionally omit the publication predicate in test code only.
- Source-reference hash/locator integrity and technical scope filtering are measurable now. Independent answer/citation support and legal applicability remain **unmeasured**. There is no answer generator; an empty passage list is not an evaluated generated abstention explanation.
- Independent scores remain null until reviewers supply labels and disagreements are adjudicated. Agree acceptance criteria after reviewing the benchmark's representativeness; no local threshold or production guarantee is invented.

## Approval sequence and remaining gates

1. Independently review source rights/provenance, acquisition precision, institution/date applicability, full exceptions and amendment chain; accept/revise/reject exact source identities.
2. Label and adjudicate all relevant benchmark dimensions in private, preserving exact benchmark/source/review identities and disagreements.
3. Separately authorize curator admission, exact release approval/grants/server context and a reviewed retrieval acceptance run. Filling this template never publishes anything.
4. Keep unapproved guidance excluded. Broader statutes, regulator rules, full CDD/beneficial-ownership provisions and date-specific amendments remain explicit expansion dependencies.

No LLM/provider integration, corpus publication or later-phase implementation is authorized by this review package.
