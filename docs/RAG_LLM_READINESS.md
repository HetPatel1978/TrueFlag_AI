# TrueFlag AI - regulatory RAG and LLM readiness

**G4.1 development update:** A disabled, fixed-host Luminal candidate adapter is now integrated with the existing draft stage. [Implementation and exact tests](G4_1_REAL_LLM_PROVIDER_INTEGRATION.md), [activation gate](G4_1_PROVIDER_SECURITY_AND_ACTIVATION.md), [output contract](G4_1_AI_OUTPUT_CONTRACT.md). Offline transport acceptance is not real-provider verification; live calls/source publication remain unauthorized and clock-related acceptance is still blocked. The November 13 audit below is retained as historical evidence.

**November 13, 2026; HEAD `a3b2ba4`.** Source audit, existing local evidence and isolated tests only. No government-site refresh, provider call, source approval or publication was performed. Historical source validity is not legal certification.

## 1. Readiness decision

| Capability | Actual state | Acceptance boundary |
|---|---|---|
| Authorized evidence/analytics | BACKEND ONLY | Typed records, current source/case authorization and deterministic arithmetic; no analyst evidence UI |
| Investigation packet | BACKEND ONLY | Durable coordinator, immutable manifest, independent verification; no protected HTTP workflow/deployed worker/UI |
| Draft orchestration | SIMULATED | Real queues/storage/verifier around a deterministic fake provider |
| Real provider | MISSING / activation BLOCKED | No real adapter, approved egress/configuration, measured model quality or live usage |
| Regulatory retrieval engine | BACKEND ONLY | Approved-only PostgreSQL lexical retrieval/search and reference resolution APIs |
| Official corpus | BLOCKED | Proposals are not approvals; no reference tables in current demo |
| Independent relevance/semantic quality | BLOCKED / UNKNOWN | Reviewer fields remain blank; no real-model semantic acceptance |
| Combined investigator + RAG + human review | MISSING | No coordinator join, reference UI or adoption/disposition workflow |

Current packet financial facts cover count/totals and concentration for the selected currencies; the broader evidence activity API is not automatically copied into packets. Verification is source/numeric/reference checking, not semantic or legal validation.

## 2. Regulatory source/version state

Exact original URLs, raw/extracted SHA-256 and section hashes are in `contracts/regulatory_source_proposals.json`, with review details in `docs/PHASE3_4_SOURCE_APPROVAL_CHECKLIST.md` and `docs/PHASE3_4_APPROVAL_DOSSIER.md`. Their existence does not approve publication.

| Candidate | Verified repository evidence | Publication state / unresolved questions |
|---|---|---|
| eCFR 31 CFR 1020.210 | Official dated Title 31/Part 1020 XML snapshot **2026-11-02**; complete selected section; raw hash `2588950c5c16efb45a2a78369e08bda2174bf9a8be5afd634235a406f51924bb` | Proposed binding regulation for historical US-bank context; publication/effective start/end fields remain null, rights review pending. Qualified reviewer must verify scope, dates, exceptions, amendment history and source completeness |
| eCFR 31 CFR 1020.320 | Same exact dated XML; separate complete section/reference/hash | Same gate; no inference that a snapshot date is an enactment/effective date, or that this is current November 13 law |
| FinCEN SAR FAQ HTML | Official curated URL; document context and FAQ 1/6/11/16 extracted; raw hash `c6a9c857bfc6bfc3a5f22049949bb3b6f190f66440e8978e5a185583dbaab50e` | **Excluded from historical publication**: mutable page has unknown temporal validity. Nonbinding guidance is not regulation; do not invent dates |
| Dated FinCEN 2025-10-09 PDF research item | Separate v2 research/answer-key registry under `assets/local/regulatory/research_v2/` | Research only, not an approved corpus member. Does not establish historical validity of the whole FAQ HTML; runtime has no PDF admission parser |

The user authorized a **historical development scope** (as-of November 2, knowledge cutoff November 4), not source approval, independent labels or legal certification. No new external validation was performed for this audit.

## 3. Actual retrieval and citation controls

| Stage | Implemented evidence | Limitation / missing connection |
|---|---|---|
| Admission | `reference_parser.py`: curated publisher/URL contracts, SHA binding, bounded XML/HTML extraction, complete section text | No general web crawler or arbitrary uploaded document/Office/PDF parser |
| Version history | Ten `reference_*`/`corpus_*` tables; immutable source/document/version/chunk metadata, approvals/releases/members/grants/events | Running demo schema 0012 has none of these tables |
| Publication | `services/references.py`: approval records, release membership, enabled context, grants | Internal admin methods can record approval; software identity alone does not establish qualified independent review |
| Retrieval | PostgreSQL lexical `websearch_to_tsquery` / `ts_rank_cd`, GIN index; bounded top-5/exact-section lookup | Not vector search or answer generation. A known lexical AND query misses one recordkeeping question in provisional evaluation |
| Scope enforcement | Current case/user/source access, jurisdiction US, `us_bank`, language, as-of/cutoff, withdrawal/supersession and context checks | Single-workspace model; application authorization is not tenant RLS or legal applicability certification |
| Citation resolution | Authorized opaque reference IDs resolve only current admissible version/chunk with hash/locator metadata | Reference membership is not semantic support for a generated claim |
| Coordinator/provider | Investigation packets and simulated drafts contain no approved regulatory context; regulatory citations remain unavailable/empty | No conditional legal-context join, model citation contract or grounded regulatory answer pipeline |
| Frontend | No reference client, source/citation component or applicability display | Users cannot inspect retrieved passages or approve sources through current React routes |

**Unapproved versions must stay unreachable through production search/resolve and future investigator tools.** Candidate evaluation intentionally uses an isolated corpus path; it is not permission to expose proposals to users or providers.

## 4. Evaluation: what the numbers establish

| Evidence | Status / result | What it does not prove |
|---|---|---|
| Original independent-review template | 19 proposed cases; reviewer fields blank | Independent ground truth does not exist |
| V2 review template | 31 cases; reviewer fields blank; engineering keys separate | Labels are neither human-adjudicated relevance nor legal correctness |
| `docs/PHASE3_4_V2_RESULTS.json` | **Historical** isolated candidate run, not rerun as a retrieval benchmark by this audit | Cannot present these timings/quality as new November 13 measurements |
| Historical all-19 question metrics | P@5 **0.126316**, Recall@5 **0.631579**, MRR **0.631579**; 1 false abstention | Engineering labels, mixed answerable/unavailable queries and whole-section granularity limit interpretation |
| Historical applicable-candidate subset | 13 questions: P@5 **0.184615**, Recall@5/MRR **0.923077** | Subset selection changes denominator; not a replacement for the all-question report |
| Historical technical checks | 0 filter violations; 12/12 security controls; approved-only runtime disclosed 0 passages for 19 queries | Technical scope integrity is not independent legal relevance, future prompt-injection safety or answer accuracy |
| Historical candidate latency | p50 **4.710 ms**, p95 **6.067 ms**, 28 timed queries; SQL counters include timeout statements | Local small-corpus baseline, not production capacity/SLO |
| Current test execution | Reference/parser/approval/filter regression cases are included in the current full backend run; exact outcome in [ledger](CURRENT_SYSTEM_AUDIT.md#6-validation-ledger---november-13) | Aggregate test success cannot turn proposed labels into independent labels |

`reference_evaluation.py` explicitly blocks adjudicated quality metrics for `review_status="proposed"`. No legal-answer generator is implemented; answer-support/semantic metrics remain null. The 31 cases include overlapping group reports: do not sum groups as unique cases.

### Required regulatory acceptance, in order

1. Qualified human reviews exact source/hash/version, complete exceptions/amendments, US-bank applicability, rights and historical dates; records approval or exclusion with rationale.
2. Independent reviewer labels relevance, scope, citation support and expected abstention for the existing 31 cases; adjudicate disagreements without rewriting outputs to match engineering keys.
3. Re-run reproducible isolated retrieval; publish all-question and applicable/unavailable subsets, label provenance, filter violations, latency and known failures. Define acceptance criteria **before** tuning.
4. Admit approved immutable versions; create approved release, membership, grants and server-selected context. Retain unverified FAQs as unavailable; add any dated replacement only through a separate approved parser/admission path.
5. Join optional regulatory context to an authorized packet with source IDs/hashes/as-of/authority labels; recheck approval/withdrawal/permissions before publication and on retrieval.
6. Implement UI citations/applicability/limitations and negative end-to-end tests for unapproved, forged, withdrawn, future, wrong-entity and stale references. No legal conclusion or autonomous SAR action follows.

## 5. LLM implementation truth

| Concern | Implemented now | Remaining work / acceptance |
|---|---|---|
| Provider interface | `investigation_provider.py::Provider`, typed input/reply; `ProviderConfig` permits only fake simulation v1 | A real adapter/transport and explicit provider/model/version registration do not exist |
| Legacy interface | `services/investigation.py` contains a compatibility Protocol | It is not a live adapter and must not be counted as one |
| Prompt/model behavior | Fixed instruction contract; fake chooses allowlisted items deterministically | No model inference, real chain of reasoning or language quality is evaluated |
| Input minimization | `investigation_draft_verifier.minimize()` excludes case/actor/customer/account IDs, raw predictors, source prose and artifact hashes | Assess approved real-provider data classification/retention/region/egress; identifiers can still be inferable from contextual facts |
| Output | Strict JSON/duplicate-key rejection, fixed selection DSL, allowlisted uncertain questions/hypotheses; server renders facts | Arbitrary natural-language claims are not independently verified or accepted |
| Tool boundary | No case selection, tools, approval claims, autonomous actions or regulatory citations | A future tool gateway must enforce server-held case/context scope; provider text must never grant authority |
| Numeric/source verification | Independent source membership, frozen revisions, transaction arithmetic and model output checks; unsupported selections rejected | Correct numbers and valid IDs do not establish semantic entailment, causal explanation or legal correctness |
| Publication security | Current actor/case/source/assessment checks, stale-run invalidation, append-only provenance/history | No analyst-facing review/adoption endpoint or screen |
| Isolation/recovery | Bounded subprocess, clean environment, timeouts, retries, leases/fencing, attempt reservations/receipts, atomic audit/result writes | No real HTTP cancel/unknown-outcome billing/retry behavior has been evaluated |
| Usage/cost/latency | **Simulated UTF-8 byte units, not vendor tokens; USD 0** | Real vendor usage reconciliation, spend ceilings, latency/quality/abstention metrics absent |
| Prompt injection | Untrusted data remains constrained; forged tools/citations/fields rejected in simulation | No evidence of live-model injection resistance; parsing tests are not a real-model red-team result |
| Semantic quality | Explicit `requires_human_semantic_review`; entailment/legal correctness are not verified | Independent real-provider benchmark and human review are mandatory |

The simulation child has a minimized environment and Linux resource limits, but does not create a network namespace or separate filesystem/OS-user sandbox. No external model call is implemented; this is a fixed trusted-code boundary, not proof of OS-enforced egress denial or safe execution of hostile provider code.

## 6. Provider gate and shortest credible integration

**Proposed, not implemented:** retain the deterministic packet and verifier as the authority boundary; add one approved provider behind the existing interface. No multi-agent framework is required.

- Approve provider/model/version, region, synthetic-only data classification, retention/training policy, egress allowlist, credential handling and bounded spend before any call.
- Implement a transport with strict structured output, real usage accounting, bounded payload/timeout/cancellation, no arbitrary tool execution and safe ambiguous-failure handling. Keep the fake explicitly labeled for offline tests.
- Evaluate a separate held-out connected scenario cohort: evidence support, numeric/reference integrity, contradiction handling, abstention, unsupported allegation rate, injection resilience, latency and cost. Human-labeled semantic quality is separate from programmatic checks.
- Add protected request/status/history/detail APIs and a review UI displaying the exact evidence, limitations, source versions and draft status. Persist explicit human adoption/rejection; never auto-close or file a SAR.
- Enable regulatory context only after its independent gate. A real evidence-only LLM can be evaluated separately if approved; it must clearly abstain on regulatory questions until approved context exists.

## 7. Approval versus engineering dependency

| Human/external gate | Engineering can proceed without crossing it |
|---|---|
| Qualified source approval + independent labels | Evidence/packet UI, assignment, notes, human decisions, offline reference tests |
| Approved provider/data handling/egress/spend | Adapter contract design, fake-labeled UI, minimization/error tests; no live calls |
| Acceptance rubric and independent findings labels | Scenario catalog, source-grounded packet oracles, review/audit interfaces |
| Promotion of aligned demo release | Rehearsal/restore proof on a recoverable copy; no automatic live migration during this audit |

**Readiness:** strong deterministic foundations; not ready to claim a real AI investigator or published regulatory RAG. Approval alone does not create missing adapters, HTTP routes, screens or human decision records.
