# G5.1 — Retrieval evaluation and independent-review gate

## 1. What the benchmark measures

- Reuses `contracts/regulatory_benchmark_v2.json`: **31 unique cases**, comprising 19 information questions and 12 technical controls. Overlapping A–E groups are tags, not additive samples.
- Existing `regulatory_provisional_answer_keys_v2.json` contains engineering hypotheses. `regulatory_independent_review_v2.json` remains untouched: **zero nonblank independent labels**.
- Original 19-case baseline, 31-case expansion, source registries, earlier research files and their hashes are preserved. No generated independent labels or human expertise are claimed.
- `test_regulatory_benchmark_v2.py` still uses its explicitly test-only candidate query with the existing production applicability/ranking expressions. It is never registered as a public/investigator retrieval capability. Actual service/API checks retain approval filtering.

## 2. Separate evidence classes

| Evidence class | Permitted conclusion |
|---|---|
| Exact original/extracted/section hash checks | These stored source bytes and locators match the frozen proposal. Does not establish applicability or legal force. |
| Synthetic corpus publication/retrieval tests | Deterministic application controls work for explicitly marked test fixtures. No official approval occurs. |
| Unapproved official candidate diagnostics | Engineering observations about lexical results, availability and latency. Not expert relevance or legal-quality scores. |
| Independent human labels and adjudication | Pending. Needed before any expert-reference ranking metric or semantic support judgment. |
| Real LLM safety or legal conclusion | Not tested or authorized. Inert text/strict citations do not prove live-model injection resistance. |

## 3. New expert-metric gate

- `backend/app/evaluation/regulatory_review.py` replays every bound, hash-linked review transition. All 31 cases must reach `approved_for_evaluation` with `independent_human` basis under an owner-approved registry before expert metrics are computed.
- A reviewer cannot adjudicate or approve their own submission. Unreviewed, merely labeled, disputed, adjudicated-but-unapproved, stale-source/registry, forged-source and synthetic protocol histories cannot supply expert-reference metrics.
- The earlier `evaluate_reference_cases(..., review_status="human_reviewed")` path now rejects the unsupported claim. Existing `proposed` and `test_fixture` behavior remains available; current callers use those states. Expert evaluation uses the bound-history path.
- The checked-in reviewer registry is empty/unapproved. Actual `expert-evaluation.json` reports 31 unreviewed cases and **Precision@5 / Recall@5 / MRR = null**, not zero or a pass.

## 4. Metrics after genuine review

| Metric | Exact population / rule |
|---|---|
| Precision@5 | Unique relevant returned `source:section` keys divided by **5**, including absent slots; macro mean over labeled non-control questions with nonempty known relevance sets. |
| Recall@5 | Unique relevant hits divided by the reviewed known relevant-section set. Excluded sources remain visible misses; missing documents without verified identities are recorded separately, not invented as citations. |
| MRR | Reciprocal rank of first reviewed relevant key, zero when absent; same question population. |
| Negative-query outcomes | Empty relevance is not perfect recall. Unexpected returned passages and unavailable-result violations are counted separately. |
| Source-version integrity | Every returned row must match the frozen source original hash and section text hash; ≤5 unique results, exact case IDs, matching manifest. PDF passages without verified parser section hashes cannot be fabricated into observations. |
| Semantic citation support / exceptions / contradictions | Human labels with qualifications and rationale; separate from locator validity. No automatic entailment score or legal certification. |
| Latency | Monotonic local query elapsed time, explicit query sample count and p50/p95; no production SLO claim. |

Observation intake is operator-controlled and binds all 31 IDs plus the current review manifest; it is not authenticated telemetry or proof of source approval. The measurement path cannot grant access or publish a corpus. Inapplicable/missing/uncertain source findings require abstention and qualified review rather than generated legal answers.

## 5. Measured G5.1 results — no independent quality labels

Actual protected report: `regulatory-first-benchmarks.json`, in the directory referenced by `runtime/g5-1/current.json`.

| Measurement | Observed result |
|---|---|
| Existing 31-case benchmark | 19 questions + 12 controls executed in real PostgreSQL. |
| Approved-only official runtime | **19/19 unavailable; zero passages disclosed**. |
| Technical security controls | **12/12 passed**; zero unauthorized disclosures, wrong-scope results or accepted forged citations. |
| Candidate source-reference checks | **13 checked, zero hash/locator integrity errors**. These are not semantic-support labels. |
| Candidate filter violations | **0**; historical institution/date/authority and exclusion predicates reused. |
| Candidate operations | **28** timed queries, p50 **4.982 ms**, p95 **6.635 ms**; 78 SQL cursor executions, 2–3/query. |
| Approved-only runtime operations | **19** timed queries, p50 **3.002 ms**, p95 **4.866 ms**; 152 cursor executions, 8/query. |
| Controlled synthetic retrieval fixture | Four queries; p50 **13.194 ms**, p95 **22.860 ms**. Fixture relevance is engineering-only. |
| Independent expert-reference P@5 / R@5 / MRR | **Not measured — all null**. |
| Independent semantic/claim support | **Not measured**. |
| Live LLM calls / official publications | **0 / 0**. |

Candidate/provisional relevance diagnostics remain in the private test report under `UNREVIEWED_ENGINEERING_DIAGNOSTICS_ONLY`; they are not promoted to expert quality scores. Earlier phase results are not re-labeled as newly reviewed ground truth.

## 6. Technical/adversarial coverage

| Boundary | Actual tests |
|---|---|
| Unapproved source, approval hash, same-account source approval | Existing reference tests plus `test_actual_official_source_cannot_self_approve_or_omit_review_reference`; actual official candidates remain unapproved. |
| Institution/authority/date/future-effective filters | Existing `test_scope_and_authority_filtered_before_ranking`, `test_date_filters`; new future-effective handoff test. |
| Supersession/withdrawal | Existing immediate/multigeneration successor and saved-citation tests; new saved selection fencing for source/version/release and successor. |
| Forged citations/version mismatch | New selection tests alter version/context/release/reference identity, text/hash, section and authority; all denied. |
| Cross-case/user/assignment/grant isolation | Existing API/service tests and new selection tests recheck current permissions. |
| Injected regulatory text | Existing parser/service test plus actual synthetic corpus handoff; instruction remains inert `untrusted_reference_data`. No live-model safety claim. |
| Missing/conflicting regulatory context | Existing `cdd-coverage-boundary`, `continuing-guidance-conflict`, empty/ambiguous/unapproved cases; new label fields record missing sources, contradictions and abstention. No automated resolution of a legal disagreement. |
| Audit failure | New handoff audit-failure test verifies both retrieval/selection audit writes roll back; no context returned. |
| Independent-review tampering/self-approval | New strict submission/roster/source bindings, role separation, sequence/hash checks and frozen history tests. |
| Concurrent review requests | Actual CLI duplicate submissions create exactly one synthetic protocol event; the second is rejected. No real human label is created. |

## 7. Reproduction

```text
python scripts/verify_reference_proposals.py
python scripts/regulatory_review_workflow.py prepare --output runtime/<private>/human-review-packet.json
python scripts/regulatory_review_workflow.py evaluate --registry contracts/regulatory_reviewer_registry_v1.json --journal runtime/<private>/independent-journal --output runtime/<private>/expert-evaluation.json
python -m pytest backend/tests/test_regulatory_review_workflow.py backend/tests/test_investigation_evaluation.py -q
python runtime/g5-1/run.py --mode materialize --label regulatory-first
python runtime/g5-1/run.py --mode regression --label investigation-security
python runtime/g5-1/check_workflow.py
```

- Owner-local `runtime` runner/state are ignored, private environment orchestration; do not publish credentials. For another approved isolated runner, supply `TRUEFLAG_TEST_POSTGRES_URL` pointing only to a disposable database and run the listed checked-in tests. Each `platform` fixture creates/drops its own random schema. New PostgreSQL tests explicitly skip when not opted in.
- Candidate source tests require privately staged hash-matched assets in `assets/local/regulatory/proposed/` and `research_v2/`. Missing official bytes are skipped/unavailable, never substituted with synthetic legal text. The measured G5.1 Linux run had **zero skips**.
- See `G5_1_REGULATORY_RAG_FOUNDATION.md` for complete suite results, exact clock-failure classification, preserved scientific parity and release limitations. No capacity benchmark, legal certification or production acceptance follows from these local results.
