# Phase 3.4.1 - Proposed benchmark enhancement and measured diagnostics

**Engineering proposals, not independent ground truth. No official source approval/publication.** Starting branch `codex/project-initialization`, actual HEAD `a24cbd9`; original `e7a954c` regulatory gate and subsequent deterministic foundation preserved. Historical U.S. bank scope remains November 2, 2026, knowledge cutoff November 4, 2026 in New York.

## Previous versus proposed evaluation

| Dimension | Preserved v1 | Proposed v2 |
|---|---|---|
| Unique cases | 19: 7 questions + 12 controls | **31: 7 questions + 12 controls + 12 new scenarios** |
| Question keys | Sparse engineering relevant-section hints | Research paraphrases, exact versions/locators, authority, historical caveats, exceptions, partial/unavailable coverage and reviewer questions |
| Control boundary | 12 explicit procedures; some candidate/parser-only simulations | Same IDs/procedures retained; explicit assertions plus existing full synthetic API/supersession/revocation/rollback suite; limitations remain visible |
| Labels | Original blank independent packet | Separate new blank review packet; **all independent fields null**, including adjudication statuses |
| Source identity | Frozen two-source proposal | Frozen originals plus separately identified research-only October 2025 PDF; no admission, replacement, redating or publication |
| Relevance metrics | 7 question diagnostics; 3 eCFR subset | 19 question diagnostics; original-query and eligible-candidate subsets explicitly identified; no control/overlapping-group double counting |
| Citation/applicability | Engineering retrieval/filter checks | Source-reference integrity and technical applicability measured separately from unreviewed claim support/legal applicability |
| Operations | Local latency | Local p50/p95, SQLAlchemy statement counts, bounded query/container resources and explicit failure tests |

Groups: A relevance/ranking, B historical applicability/authority, C citation/factual support, D abstention/missing coverage, E security/adversarial behavior. These are overlapping tags, not additional cases or a combined legal/security score.

## Twelve new distinct scenarios

| ID | Information need / source boundary |
|---|---|
| `threshold-with-conditions` | Attempted/aggregated transactions and suspicion conditions; 1020.320(a) |
| `below-threshold` | Voluntary reporting versus universal no-filing claims; 1020.320(a)/(g), parallel rules missing |
| `identified-suspect-clock` | Initial-detection clock, identified suspect and urgency; 1020.320(b)(3) |
| `unidentified-suspect-clock` | Conditional extension and outer deadline; 1020.320(b)(3) |
| `continuing-guidance-conflict` | Internal assertion versus optional continuing guidance; excluded dated PDF/FAQ16; full answer unavailable |
| `sar-confidentiality-request` | SAR existence/private request, qualified disclosures and underlying records; 1020.320(e) |
| `qualified-reporting-exception` | Prerequisites for robbery/securities exceptions; 1020.320(c), securities cross-reference absent |
| `bank-category-program` | Bank without Federal functional regulator; 1020.210(a)/(b) |
| `cdd-coverage-boundary` | Ongoing CDD versus complete beneficial-ownership exemptions; 1020.210, full 1010.230/amendments absent |
| `supporting-document-request` | Retention versus requester authority/confidentiality; 1020.320(d)/(e) |
| `historical-not-current` | November 2 snapshot cannot certify November 4 law; date-filter abstention |
| `near-ctr-insufficient-facts` | Amount alone, unknown entity/purpose; excluded dated PDF Q1 plus conditional 1020.320(a); abstention |

## Preliminary source verification and unresolved research

- Existing source/evaluation/review contract bytes and hashes remain unchanged. No provisional key is an independent answer or legal finding. The exact source registry and reviewer questions are in [provisional keys](../contracts/regulatory_provisional_answer_keys_v2.json).
- New [FinCEN/interagency October 9, 2025 FAQ PDF](https://www.fincen.gov/system/files/2025-10/SAR-FAQs-October-2025.pdf): **284,868 bytes**, SHA-256 `5ed61b76f65ca1640f2d40e1afe3db40c77622620e81aefd08bc5273e0de4cac`. Its [official landing page](https://www.fincen.gov/resources/statutes-regulations/guidance/frequently-asked-questions-regarding-suspicious-activity) identifies issuance; landing SHA `371aa3f12a3d1ac661ebf910fe36591bc8ce7c5638b84e64c294ebe4a64eb36f`.
- It is a distinct nonbinding research candidate, not a date assigned to all mutable FAQs. Original PDF/page copies and actual acquisition timestamps are ignored/private. No new production extraction or historical validity interval is asserted; PDF parser/intake support is absent. It remains outside candidate SQL and public retrieval.
- Dated eCFR is useful for proposed historical review, not full official-law certification. FinCEN HTML remains excluded. Institution categories, cross-references, source-use rights, acquisition precision, effective/amendment history and applicability require qualified review. No malware scanning is available.

## Reproducibility and measurements

```powershell
.venv\Scripts\python.exe -B scripts/prepare_regulatory_benchmark_v2.py --check
.venv\Scripts\python.exe -B scripts/verify_reference_proposals.py
.venv\Scripts\python.exe -B scripts/prepare_regulatory_review_packet.py --check
.venv\Scripts\python.exe -B scripts/run_regulatory_approval_gate.py --benchmark-v2
```

The v2 flag extends the existing pinned Linux runner, using read-only code/research mounts, a protected recovery clone and disposable migrated PostgreSQL schemas. No running demo migration, corpus setting, approval or release is changed. The default v1 runner remains supported; its original contracts/results are not overwritten by v2 mode.

The test-only candidate query uses existing scope/date/authority predicates and PostgreSQL English lexical ranking but deliberately omits publication filtering to inspect **unapproved** candidates. Production API/direct tools retain approval/grant checks. The dated PDF is not parsed/admitted. Tests do not repair lexical ranking or reference labels to improve scores.

### Actual local results - November 4, 2026 (New York)

Machine-readable observations: [v2 results](PHASE3_4_V2_RESULTS.json). Labels below are **engineering proposals, not independent ground truth**.

| Question population | Count | Precision@5 | Recall@5 | MRR |
|---|---:|---:|---:|---:|
| All original/new questions, excluded sources retained in denominators | 19 | 0.126316 | 0.631579 | 0.631579 |
| Original seven queries under v2 proposed relevant sets | 7 | 0.085714 | 0.428571 | 0.428571 |
| Candidate-eligible questions, including partial needs | 13 | 0.184615 | 0.923077 | 0.923077 |

| Dimension | Actual observation | Limitation |
|---|---|---|
| Source-reference integrity | 13 returned references checked; 0 hash/section errors | Includes a top-five result irrelevant to its question; syntactic integrity is not relevance or claim support |
| Applicability | 0 technical filter violations | Independent legal applicability remains unmeasured |
| Candidate coverage | 6 correctly unavailable queries; 0 unavailable queries returning passages; 12 eligible queries with relevant passages; **1 false abstention** | The unchanged `recordkeeping` query ANDs `recordkeeping`, which is absent from the eligible complete section; no query/reference tuning performed |
| Runtime approval boundary | 19/19 question reads unavailable, 0 passages disclosed | No approved corpus; this measures safe withholding, not useful legal answers |
| Controls | 12/12 passed; 0 unauthorized disclosures, wrong-scope results, accepted forged citations or parser instruction-boundary violations | Supersession simulation and parser-only limitations remain; full synthetic successor tests run separately |
| Candidate operations | 28 queries; p50 **4.710 ms**, p95 **6.067 ms**; **78 SQL statements**, 2-3/query | SQLAlchemy executions include `SET LOCAL` timeout statements; local sequential microbenchmark |
| Runtime operations | 19 queries; p50 **2.678 ms**, p95 **4.035 ms**; **152 SQL statements**, 8/query | Unconfigured corpus path only, not published-corpus capacity |
| Resources | 2 CPUs / 3 GiB container caps; top-five results, 256 characters/40 words; 5-second statement timeout | Caps, not measured resource utilization or production guarantees |
| Independent answer/citation support | **Not measured; 0 independent labels** | No answer generator; incorrectly generated answers/answer-level abstention are not measurable |

| Verification run | Passed | Failed | Skipped |
|---|---:|---:|---:|
| Pinned Linux/PostgreSQL parser, references, v1 gate and v2 benchmark | 108 | 0 | 0 |
| Native Windows/PostgreSQL v2 benchmark | 17 | 0 | 0 |
| SQLite/local v2 compatibility | 15 | 0 | 2 PostgreSQL-only |

These runs overlap; do not sum them into unique tests. PostgreSQL acceptance includes Alembic head/drift, empty upgrade/downgrade and retained-history protection through the existing reference suite. API strict bounds, anonymous/cross-analyst denial, permission revocation and sanitized audit failure are tested. Existing Starlette/httpx deprecation remains nonblocking. Source/template hash checks, lint/format and publication checks are part of final verification. Frozen ML replays were not rerun for this evaluation-only change; scientific files/services are unchanged.

**Engineering preparation PASS; independent retrieval/legal acceptance BLOCKED.** No relevance threshold or legal acceptance is inferred from passing technical assertions. Adding narrower scenarios changes benchmark difficulty; the higher all-question diagnostic is not evidence of improved ranking or generalization.

## Interpretation and residual limitations

- Original v1 diagnostics: 3 eCFR questions P@5 0.2 / Recall@5 1 / MRR 1; all 7 P@5 0.085714 / Recall@5 0.428571 / MRR 0.428571. These remain historical, unreviewed measurements.
- New source-qualified relevance keys disambiguate document/section identity. Retention now proposes both the regulation and FAQ, while the original query is unchanged. Result differences may reflect changed relevance hypotheses, not service/ranking improvements.
- Independent claim support, legal applicability and answer correctness remain null. Proposed answer text is not fed into an LLM; generated-answer failure/abstention rates cannot be measured without an answer generator. Returned-source integrity and safe runtime withholding are narrower engineering checks.
- Supersession candidate exclusion is explicitly simulated; real successor/revocation behavior is covered separately with synthetic, non-authoritative published fixtures. Parser inertness is not future prompt-injection certification.
- No production code, model/features/policies/SHAP, transaction evidence, frontend or scientific assets change. Preserve the seven pre-existing branding/startup edits. No source self-approval, reviewer impersonation, GitHub push or later-phase implementation.

Reviewer instructions: [independent review guide](PHASE3_4_REVIEWER_GUIDE.md). The evidence-only coordinator already exists; approved sources, independent legal/relevance adjudication and provider/data-governance approval remain gates for any separately requested LLM work.
