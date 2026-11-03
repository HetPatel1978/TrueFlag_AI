# Phase 3.1 — Investigation security, governance and evaluation proposal

**Design only; no new controls/provider/evaluation results are implemented or claimed.** Existing Phase 2 local acceptance remains historical evidence for that pipeline, not acceptance of the proposed investigator. [Architecture](PHASE3_1_INVESTIGATION_ARCHITECTURE.md), [evidence model](PHASE3_1_EVIDENCE_MODEL.md), [contracts](PHASE3_1_RETRIEVAL_RAG_CONTRACTS.md).

## 1. Assets, actors and trust assumptions

- Protect case/assignment visibility; source identities/PII; transaction/evidence contents; privileged reference/internal-policy text; source integrity; immutable model/result history; provider credentials; investigator budgets; human decisions and audit history.
- Untrusted inputs include analyst text, CSV/document bytes, source metadata, retrieved text, provider output and provider-proposed tool arguments. A source may be official yet stale, incorrectly extracted, poisoned in transit or inapplicable to a case.
- Current user/role/case checks are reusable; evidence-level access, new job capabilities, corpus approval, independent reviewer gates and hardened production roles are proposed. No implemented multi-tenant/RLS boundary exists today.
- Model endpoint is an external disclosure boundary even with a private network endpoint. A local model reduces external egress but does not eliminate access-control, prompt-injection, logging, licensing or resource risks.
- Threat/control matrix below is our analysis of these proposed TrueFlag interfaces. [OWASP](https://genai.owasp.org/llmrisk/llm01-prompt-injection/) identifies direct/indirect prompt injection and notes RAG does not eliminate it; prompt instructions are not an authorization control. Use [NIST's generative-AI profile](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf) as a risk/evaluation organizing reference, not certification.

## 2. Threat model and proposed controls

| Threat / failure scenario | Required controls | Later acceptance evidence |
|---|---|---|
| Cross-case IDOR, guessed transaction/reference IDs | Current SQL case predicate + explicit active source/version membership on every read; server-bound run/case/purpose; scoped cursors; all aggregate/count paths filtered first | Other analyst/admin-owner/source cases; shared counterparty; forged handles/cursors; metadata/count/timing disclosure probes |
| Revocation or reassignment while a job runs | Fresh actor/service/case/source checks before tools/egress/publication/disclosure; case/evidence/access revision fences; no long DB lock around a model call | Revoke during tool query/provider wait/verification/commit; no unauthorized result publication |
| Direct or retrieved-document prompt injection | Treat content as data; deterministic question/tool allowlist and strict arguments; no SQL/shell/browser/write tools; externally cited passages cannot alter budgets, role or case | “Ignore instructions,” hidden markup, fake system/tool output, multilingual/encoded instructions and forged case IDs must not gain capabilities |
| Poisoned/stale/incorrectly parsed corpus | Approved publisher/source registry, restricted fetch/redirect/DNS, raw/extract hashes, parser identity, review/quarantine and corpus releases; scoped/effective-date filters | Modified bytes, compromised redirect, missing exception/context, draft/not-in-force text, stale index and revoked publication |
| SSRF/arbitrary file/object retrieval | Investigator has no fetch tool; curator egress allowlisted, private/metadata IPs blocked; generated storage keys, no client paths; safe-link resolver | URL redirects/private addresses/path traversal and unsupported protocols fail closed |
| Malicious binary/OCR payloads | Curated safe text MVP; quarantine, MIME/size/page/parse/time/process limits and approved scanner/sandbox before binary intake; no macros/active content | Untrusted binary intake remains disabled until those controls are implemented and tested; no malware-safety claim |
| Fabricated transactions or factual assertions | No aggregate-to-history backfill; typed facts/derivation registry; source-specific missingness/coverage; generated interpretations never stored as source observations | Empty/partial feeds, contradictory sources, missing/zero income and unrelated supplemental datasets |
| Citation laundering / unsupported legal conclusion | Issued-reference membership/version/hash/span checks; fact support separate from regulatory context; deterministic numeric checks; human entailment/applicability review | Existing-but-irrelevant citation, wrong scope/date, negated exception, altered quote or invented obligation blocked/abstained |
| PII leakage to provider, UI, logs or caches | Run-local aliases, purpose-minimized fields, explicit data/provider approval, strict projections, private content storage, sanitized logs and safe rendering | Canary identities/secrets in inputs, errors/tool traces/exports/provider packet; no unauthorized leakage in tested paths |
| Cross-case prompt/cache contamination | No shared provider conversation/thread; avoid cross-case result caching; any cache bound to actor/case/evidence/access/corpus/policy revisions and short TTL with reauthorization | Same query under different actors/cases; revoked source/cache entries cannot disclose previous context |
| Schema, HTML, URL or CSV injection in model output | Strict schema/length/enums, typed references; backend resolves citations; escaped UI text; no raw HTML/unsafe Markdown/code execution; separate authorized export allowlist/formula protection | Malicious markup/link/formula/output nesting; existing safe CSV pattern cannot be bypassed by new narrative fields |
| Resource/cost exhaustion or retry storm | Separate investigation queue/capacity, actor/rate/spend budgets, source scan/token/tool/deadline caps, leases/fencing, bounded repair/retry; reserve verification budget | Oversized context, repeated tool requests, provider timeouts/429s, dispatcher/worker crashes, uncertain billing and same-key retries |
| Draft/result/audit tampering or replay | Immutable source/run manifests, FK/unique intent/version constraints, independent content verification and transactional audit; access changes append separate events | Mutation/deletion/corruption, stale publication token, changed source/case/prompt/model/corpus identity and concurrent requests |
| Excessive LLM agency / unapproved case action | Read-only capabilities; human review records do not grant case actions; separate case workflow permissions; no LLM closure/SAR/export-send tool | Forged approval/tool request cannot close/dismiss/submit/transmit or change model policy |
| Privileged operator compromise | Separate migration/runtime/read-worker roles, controlled secret rotation, restricted objects/egress, independent audit/backup controls and institutional incident response | Production deployment gate; local hashes/triggers do not resist a privileged DB/host operator |

Prompt delimiters, attack classifiers and a second model can reduce some failures; none substitutes for server authority, fixed capabilities, content minimization and human accountability.

If PostgreSQL row-level security is later added as defense in depth, require reviewed non-owner runtime roles and safe transaction-local pool context. Owners/superusers/BYPASSRLS can bypass policies; a context label or enabled policy is not proof of tenancy ([PostgreSQL 17 documentation](https://www.postgresql.org/docs/17/ddl-rowsecurity.html)). No RLS change is implemented here.

## 3. Authorization, publication and revocation protocol

1. Enqueue under current case scope and declared purpose. Freeze exact case/evidence/access revisions, selected assessment/source/corpus versions, approved provider/prompt/tool/output profiles and intent digest; consume budget and commit request audit atomically.
2. Claim with separate service identity, lease and random fencing token. Before each read, bind actor/case/source visibility in SQL. Do not carry arbitrary user JWTs into long-lived jobs or accept model-supplied authorization.
3. Build a minimized bounded packet from admitted records only. Commit sensitive read audits before disclosure; verify digests and current permission again immediately before provider egress. Reserve capacity for independent verification.
4. Treat returned bytes as untrusted. Separate factual support, model attributions, regulatory context, uncertainty and hypotheses. Recompute typed facts and verify citations independently; do not blindly accept a provider's self-reported confidence/check status.
5. Before publishing, recheck current principal, case version, evidence/access revisions, source availability, approved provider/source context and live job fence. On change, invalidate/abstain with a fixed reason; do not silently rerun against newer evidence or broaden access. Commit result/verification/attempt/audit/job transition together.
6. Later reads reauthorize the case and all disclosed sources. Historical results remain historical and are not automatically current after new evidence; stale/corrected evidence must be clearly identified. If source access/content is withdrawn, withhold protected content and show only an authorized minimal restricted-status projection, without hidden source names/counts/snippets.

Revocation after external disclosure cannot retrieve already-sent bytes; cancellation is best effort and governed provider retention/deletion is still required. Browser views must use existing abort/denial/session/visibility controls; ten-second identity polling is not instantaneous invalidation. Do not claim to erase screenshots/downloads held by an authorized human.

## 4. Independent verification and human accountability

| Check | Verifier responsibility | Limit / disposition |
|---|---|---|
| Schema/capability | Reject extra fields, unexpected tools/actions, unsupported claims/statuses and budget violations | Provider output cannot authorize itself |
| Citation integrity | Resolve only issued refs; check exact version/manifest/hash/quote span/current access | Existing citation does not prove the claim follows from it |
| Numeric facts | Recompute source counts/sums/windows/currency and compare exact decimal outputs; validate coverage/reversal rules | Do not use LLM arithmetic or mixed-currency/partial-feed absolutes |
| Model interpretation | Resolve stored assessment ID/input/model/policy; check quoted score/route and SHAP attribution | Score is not criminal probability; attribution is not causal evidence or a regulatory trigger |
| Factual support | Prefer backend-rendered typed factual clauses, explicit support/counterevidence and no inferred missing records | Free narrative entailment is not completely decidable by checks; unsupported factual findings cannot be labeled verified |
| Semantic/legal review | Independent authorized human evaluates support, exceptions, uncertainty and applicability; records accept/reject/need-evidence per finding | An optional model critic cannot replace or self-approve this review |

- Proposed label for a machine-checked result: **“Draft — structural/numeric/citation checks passed; human semantic review required.”** `verified_draft` means those declared checks, not proven truth, legal compliance or approved disposition.
- Facts should reference typed source/derived values and server-rendered factual clauses. LLM narrative is constrained interpretation/hypothesis, with explicit unresolved support/coverage. Unverifiable factual claims are withheld or converted to missing-evidence outcomes; do not bury uncertainty in a generic footer.
- Preserve independent verifier input/result hashes, rule versions and per-finding outcome. The verifier reads evidence/metrics directly, not the generator's claimed validation narrative. Same-run membership bounds its own reads; budget exhaustion produces incomplete verification, never an automatic pass.
- Human review record binds reviewer identity/role/time, exact result/content/source manifest, finding verdicts and rationale. Recommendation: requester cannot be the final independent reviewer; supervisors/admins within current permitted scope receive a separately approved review capability. Require a second qualified person before adopting consequential conclusions; no self-review exception inferred for demos.
- Notes/reviews/corrections append new attributed records. A review approval does not file a SAR, close a case, change RF policy or create a training label. Consequential human case transitions require their own separately implemented authorization/approval flow.
- Failure of evidence/provider/verification keeps existing case/assessment review available. No missing evidence becomes “low risk,” no LLM failure changes the RF assessment state, and no result triggers automatic dismissal/closure/SAR.

## 5. Immutable provenance, PII and retention

- Final manifest: case/evidence/access revisions; exact observation/derived fact/model/reference versions and hashes; query/calculation/retrieval/parser/index versions; provider/model/revision/fingerprint when supplied; prompt/template/tool/output schema and decoding settings; execution identity/fence, attempts, token usage, price/cost status; verification/review records and timestamps.
- Store the authorized minimized context/actual provider response only in a separately protected, retention-controlled record if needed for reproducibility; audit/logs contain references/hashes, not text/PII. Redacted views and original objects have distinct hashes. Do not request/store private chain-of-thought; retain concise supported rationale and observable tool/provenance records.
- Provider generation may not be reproducible even at deterministic-looking settings. Preserve actual returned output and identity/parameters; do not promise bit-identical regeneration from a model name or seed. Missing provider version/usage is recorded as unavailable, not invented.
- Define data classes for source PII, normalized events, drafts/context, reference releases, access logs and operational metrics. Approve retention triggers/durations, legal holds, deletion authority and provider retention before implementation/egress. Do not apply one guessed regulatory period to every object class.
- Withdrawal/erasure/expiry must revoke retrieval/caches/links immediately and retain only approved minimal tombstones/digests/audit. Protected content/key deletion can make historical reproduction unavailable; show that state. Legal hold conflicts require authorized review, not an automatic deletion or indefinite-retention rule.
- Current gaps remain: no malware scanner, production identity/tenant boundary/TLS perimeter/least-privilege SQL roles/independent audit storage, institutional retention/backup/restore/HA acceptance or approved external-provider data contract. Phase 3.1 implements none of them and supplies no compliance certification.

## 6. Evaluation plan — future gates, no measured AI results yet

Separate frozen ML parity, evidence/calculation correctness, retrieval relevance, model factuality, security and human usefulness. Use versioned fixed fixtures with held-out seeds/source versions and an access-controlled oracle never sent to the provider.

| Evaluation family | Fixtures / ground truth | Measurement and proposed release rule |
|---|---|---|
| Source and analytics | Complete/partial windows, reversals/corrections, timezones, missing/zero, mixed currencies and duplicate events | Exact typed decimal/time/count/source-version reconciliation; all controlled invariant checks pass |
| Missing/conflicting evidence | Legacy aggregate-only cases, absent KYC, contradictory records, sampled feeds | Abstain on unsupported transaction/legal conclusions; explicitly report coverage/conflicts; no fabricated transaction/identity |
| Factual correctness | Reviewer-authored supported facts and allowed interpretations across benign/suspicious-looking controls | Supported atomic factual claims / all factual claims; blinded human adjudication plus deterministic numeric checks; no crime allegation inferred from scenario label |
| Citation coverage/integrity | Gold evidence spans and provision/exception support | Supported claims with valid permitted source links / claims requiring support; zero nonexistent/unauthorized/wrong-version refs in release fixtures |
| Unsupported-claim rate | Empty evidence, tempting unrelated passages, near-match numbers, wrong dates and counterevidence | Unsupported factual claims / all factual claims; report numerator/denominator and severity, not only an average; any critical unsupported allegation blocks release |
| Retrieval | Gold relevant passages per approved jurisdiction/entity/date/language plus wrong-scope distractors | Precision@5, Recall@5, rank metric and filter violation count; zero permission/scope/date violations in fixtures; approve relevance thresholds after dataset review |
| Injection/tool abuse | Direct/indirect injection, hostile document metadata, encoded instructions, forged refs/tools/cursors and cross-case memory attempts | Zero successful unauthorized reads/writes/egress or policy overrides in the adversarial suite; do not extrapolate a perfect real-world defense |
| Revocation/races/recovery | Permission/source changes at every stage, concurrent intent, stale lease, provider timeout/rate limit, DB interruption and orphan attempt | No unauthorized publication or duplicate result; every uncertain/billed attempt accounted for; durable state survives restart |
| Provider/schema/failure | Truncation, invalid JSON, hallucinated fields, absent token usage, outage/cancellation and exhausted budget | Bounded repairs/retries/deadlines; sanitized safe status; no successful mock substituted for a real approved-provider acceptance run |
| Human review/UI | Blind reviewer findings, citation drill-down, stale/withdrawn sources, logout and role change | Correct reviewer accountability and safe display; analyst utility/rationale quality measured separately from scientific accuracy |
| Latency/resources | Representative evidence/corpus sizes and permitted contexts | p50/p95 per retrieval/calculation/provider/verification/overall stage; queue age, memory/DB pressure, failures; no SLO claimed before measurement |
| Cost | Actual provider usage and all attempted/uncertain calls | Input/output tokens, tool/repair/attempt counts and cost per successful/abstained/failed run, price version and unknown usage; review spend cap; no invented token price/cost |

Proposed safety gates above are **requirements to approve/test**, not executed percentages or production guarantees. Record case/claim denominators, uncertainty, human disagreements, corpus/model/prompt versions and leakage-free splits. Evaluate lexically first; add embeddings/extra agents only after a held-out comparison demonstrates benefit without unacceptable permission/cost/regression effects.

## 7. Review gate and stop boundary

- Approve [D3-01–D3-07](PHASE3_1_INVESTIGATION_ARCHITECTURE.md#6-decisions-requiring-review--no-approval-inferred) at their relevant gates: evidence strategy/schema/linkage/source use/access/retention before 3.2; jurisdiction/corpus before 3.4; provider/egress/spend before 3.5; independent review capability before 3.6. Evaluation fixture coverage and quality/budget limits require review; no vendor/corpus approval is implied by evidence-only development.
- First 3.2 scope is evidence/schema/generator design acceptance and its future internal implementation, conditional on approval; no provider, RAG index, public API or UI feature is part of 3.2 by default.
- Current Phase 3.1 deliverable is documentation only. No Phase 3.2 work, provider call, corpus ingestion or new security feature is implemented or approved by this document.
