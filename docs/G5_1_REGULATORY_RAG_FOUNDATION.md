# G5.1 — Offline regulatory intelligence foundation

## 1. Outcome and limits

- Reused and strengthened existing PostgreSQL lexical retrieval; no vector database, second search engine, provider activation, frontend feature or new infrastructure.
- Added independent review/adjudication workflow, source-approval safeguards and a dormant revalidated regulatory-context contract for future investigator integration.
- **No official source approved/published and no independent expert labels supplied.** Qualified source review, acquisition/date precision, applicability and independent benchmark approval remain blocking gates.
- Branch `codex/project-initialization`; HEAD remains `a3b2ba49cd92c4aa0401842fa4999897fdc28713`. Earlier unrelated uncommitted work preserved. No commit, push, deployment or live migration.

## 2. Components reused and changes

| Component / actual path | Status and responsibility |
|---|---|
| `backend/app/models/references.py`, `backend/alembic/versions/0013_reference_corpus.py` | Reused unchanged: immutable source/document/version/chunk, approval, release/context/grant and lifecycle history. No schema migration added. |
| `backend/app/services/reference_parser.py` | Reused unchanged: bounded XML/HTML/plain text, complete section extraction, byte/hash locators and publisher URL restrictions. No runtime fetch or PDF support. |
| `backend/app/services/references.py` | Existing publication, scope/date/authority/source lifecycle filters, PostgreSQL English lexical ranking, citation resolution and hashed audits retained. New official approval requires distinct approver account plus review-dossier hash. New atomic selection handoff rechecks every citation field and current permission. |
| `backend/app/schemas/references.py` | Existing public search/result contract preserved; optional `Approval.review_reference_sha256` added to internal curation contract. Official new approvals require it. |
| `backend/app/api/references.py` | Unchanged protected case search/citation routes. No public curator/review/investigator endpoint added. |
| `backend/app/services/reference_evaluation.py` | Fixture/proposed evaluation retained; unchecked `human_reviewed` string can no longer manufacture expert metrics. |
| `backend/app/evaluation/regulatory_review.py` | New manifest-bound, role-separated human review state machine and gated expert-reference metric interface. Synthetic protocol labels cannot become expert truth. |
| `contracts/regulatory_reviewer_registry_v1.json` | New empty/unapproved roster template; grants no authority. All earlier source/benchmark/review contracts unchanged. |
| `scripts/regulatory_review_workflow.py` | New bounded offline preparation/intake/status/evaluation CLI; exclusive-create hash-linked events, no DB/source publication calls. |
| `backend/app/schemas/regulatory_context.py` | New versioned internal handoff: source/version/approval/citation identity, exact excerpt, applicability, limitations and explicit no-action/no-violation authority. Not connected to G4 dispatch. |
| `backend/tests/test_regulatory_review_workflow.py`, `test_regulatory_context.py` | New protocol unit tests and actual PostgreSQL security/authorization/integrity/audit tests; existing suites retained. |

## 3. Architecture

```mermaid
flowchart TD
    O[Privately staged official bytes: exact hashes] --> P[Existing controlled parser / section chunks]
    P --> V[Immutable source versions: unapproved]
    H[Qualified human source review: pending] --> A[Separate approval + dossier hash]
    V --> A
    A --> R[Explicit corpus release / grants / server scope]
    R --> Q[Existing case-authorized PostgreSQL lexical retrieval]
    Q --> F[Publication / institution / dates / version / withdrawal filters]
    F --> C[Exact immutable citations + hashed read audit]
    C --> S[New atomic source/permission selection revalidation]
    S --> X[Dormant regulatory-context envelope: no legal conclusion]
    X -. separate G5.2 approval .-> G[Future G4 investigator integration]
    B[Existing 31-case benchmark] --> W[Independent label / dispute / adjudication workflow]
    W --> E[Expert metrics only after valid human review]
    Q --> T[Engineering diagnostics: no expert labels]
```

## 4. Applicability and governance

- Current scope is **US / us_bank / en / historical 2026-11-02**, knowledge cutoff 2026-11-04 New York. Scope is selected server-side; neither client nor model may broaden it.
- PostgreSQL filters publication, jurisdiction, institution type, authority, effective interval or exact dated snapshot, verified-through, knowledge cutoff, supersession and withdrawals **before** rank/limit. Retrieval remains potentially applicable context, not a confirmed legal conclusion.
- Current institution taxonomy is coarse `us_bank`; charter/regulator and paragraph-specific applicability require qualified review. Do not infer every bank requirement applies to every institution or transaction. No complete BSA/CDD/statutory corpus exists.
- eCFR snapshot is proposed, FinCEN HTML excluded pending historical validity, dated PDF research-only/unsupported for production parsing. No missing text, dates or citations were invented.
- Source version approval, release approval, reader grants, independently reviewed benchmark labels and model/data-transfer authorization are **separate** gates. New workflow records cannot execute publication or case decisions.
- Source dossiers, exact hashes, temporal gaps and reviewer actions: `G5_1_SOURCE_REVIEW_AND_GOVERNANCE.md`. Benchmark rules/results: `G5_1_RETRIEVAL_EVALUATION.md`. Reader/UI/G4 contract: `G5_1_FRONTEND_INTEGRATION_CONTRACT.md`.

## 5. Measured verification

| Run/check | Actual result |
|---|---|
| `python runtime/g5-1/run.py --mode materialize --label regulatory-first` | **150 passed, 0 failed, 0 skipped**: existing parser/retrieval/publication/approval/31-case suites plus new review/context tests. |
| Same runner `--label regulatory-acceptance` | **152 passed, 0 failed, 0 skipped** on final code, including added ASCII/Unicode journal resource-bound tests. Intermediate `regulatory-final`: 151 passed, 0 failed/skipped. |
| `python runtime/g5-1/run.py --mode regression --label investigation-security` | **178 passed, 1 failed, 0 skipped**: existing AI evaluation, coordinator, evidence authorization, snapshot/clock and release tests. Relevant suites, not a full backend-suite run. |
| `python runtime/g5-1/check_workflow.py` | 31 blank tasks, expert metrics null, unapproved reviewer rejected, concurrent synthetic duplicate creates one event. Zero independent human labels or source approvals. |
| `python scripts/verify_reference_proposals.py` | Exact existing XML/HTML source integrity verified; approval/publication false. Dated research bytes also covered by existing benchmark tests. |
| `python scripts/run_ml_verification.py --check tests` | **178 passed**, pinned Linux private fitted artifacts, network disabled. |
| Same script `--check scoring` | **4,000 matches**, maximum absolute error **0**, zero mismatches; original `1e-12` tolerance. |
| Same script `--check policy` | **12,000 matched routes**, zero route/trace/retained/dismissed-total differences. |
| Same script `--check shap` | **4,000 verified**, zero encoded/grouped/base reference differences; maximum score difference **0**; reconstruction residual **3.1086244689504383e-15**, original `1e-6` tolerance. Missing income 87 and observed zero 22 preserved. |
| Frontend `npm.cmd test` | **85 passed**, seven files. No frontend feature/Chromium flow added in G5.1. |
| Frontend `npm.cmd run lint`, `build`, `format:check` | Passed. No deployment performed. |

Counts overlap where suites are rerun; do not sum them into a claimed unique full-suite total. Private commands use the repository `.venv/Scripts/python.exe -B`. Actual benchmark operations and controls are detailed separately; no expert-quality score is reported.

### Single regression failure

- `tests/test_evidence_read.py::test_numeric_oracle_from_original_generated_observations[timezone_offsets]` raised **ClockUnavailable** during initial authorized context retrieval (`test_evidence_read.py:215 → evidence_read.py:198 → snapshot_clock.py:57`), before numeric assertions.
- Sanitized observation: database epoch **1794834015**, persistent high-water **1794834016**, epoch **2**, `regressed=true`, `unsafe=true`: a real one-second regression and safe denial.
- The failure is retained as a failure. No clock guard, 900-second expiry, token epoch, source authorization or numeric rule was relaxed. A passing regulatory run does not establish clock stability or resolve the upstream Windows/WSL clock cause.
- Independently clock-stable Linux release acceptance remains blocked from earlier G1 work. G5.1 does not claim full integrated release acceptance, legal certification or production capacity.

### Environment

- Docker Desktop was initially stopped; started the installed engine in the background, then only explicitly started the verified owned rehearsal PostgreSQL container. No demo Compose rebuild, migration or deployment.
- Test cluster: existing isolated `tf-g0-3-db-674bf460c1f147fab6dfc9530dd96ed2`, verified separate system identity and internal-only network. Tests create/drop random schemas; public demo schema is not the target.
- Existing pinned Linux image `trueflag-assessment-verify:phase2-5`, read-only source/scientific/corpus mounts, two CPUs, 3 GiB, 128 PIDs. ML image `trueflag-ml-verify:phase2-4` uses no network.
- Exact protected summaries, sanitized failure traces, benchmark observations and review artifacts remain under the owner-restricted directory referenced by `runtime/g5-1/current.json`. No query/source/customer text or credentials were printed as diagnostics.

## 6. Residual limitations and G5.2 gate

- Qualified source approval and independently adjudicated labels are still absent. Source version hashes do not authenticate a legal expert or establish semantic support; reviewer identity/qualifications and private registry approval remain a trusted human process.
- Same-account approval protection and immutable dossier references strengthen future source approvals; they do not certify legacy approval quality, rewrite existing approvals or provide externally signed authority.
- Local review journals are tamper-evident, not signed WORM storage. Database-superuser/trusted-principal tampering, production SQL least privilege, external audit retention, tenant-specific proprietary-source ACLs and malware scanning remain unresolved deployment work.
- Historical provenance precision, amendment/effective-date validity, FinCEN HTML exclusion, PDF parser limitations, broader BSA/CDD coverage and competing legal interpretations remain explicit review gaps.
- No source-review UI added: actual curator/review APIs are absent. Existing reader APIs and a future business-facing contract are documented; no placeholders or fabricated citations.
- **G5.2 is not activated.** First resolve human source/evaluation approvals and stable-runner release acceptance, then explicitly authorize the version-fenced investigator adapter. Any live provider still requires the separate G4.2B privacy/data-transfer/model/spend gate.

## 7. Final checks and preservation

- Ruff lint and formatting passed: **226 Python files**. Publication scanner passed: **383 source candidates**, private/secret ignore boundaries verified. These checks are not security certification.
- Initial event-byte enforcement used UTF-8 content length while the writer escaped Unicode and indented JSON. A controlled payload was accepted but would serialize to **73,376 bytes**, exceeding the **65,536-byte** reader limit. Corrected the bound to use the exact writer serialization, including newline; ASCII and Unicode regression cases pass in the final 152-test run. No source/label/reference output was modified to achieve parity.
- New review histories retain 64 KiB/event, 16 MiB/journal, 500-event and 4 MiB intake bounds; partial/oversized histories fail closed. No timeout, clock, source or permission guard changed.
- Final generated local source SHA-256: `80c05dea0dd0acbcf4634194983b9b5ce615d9c0db1057575f78461ecceb8f63`; build ID `38709242215699a0e180b3ede444d054117460bf7d27377e51a08debbb6a1663`. Candidate schema remains `0017_live_provider`; this metadata refresh does not deploy it or create a Git commit. Final frontend build passed against this identity.
- Original-file baseline: **413 files**, including frozen regulatory research/review assets and scientific inputs. Only three intended existing Python files (`schemas/references.py`, `services/references.py`, `services/reference_evaluation.py`) and two ignored generated release metadata files changed. All new G5.1 files are additive.
- Final `python runtime/g5-1/finalize.py --stop`: **PASS_ISOLATION_AND_FILES_LIVE_DB_UNAVAILABLE**, recorded in protected `preservation.json`. Original G1/G2 public-schema fingerprints, backups, corpus/review assets, scientific inputs and `.env` unchanged; random schemas cleaned; 111 foreign keys checked with zero orphan rows, invalid constraints or invalid indexes. Only the owned rehearsal PostgreSQL container was stopped; all volumes/backups retained.
- The original demo PostgreSQL container is currently stopped (as are demo backend/frontend); its identity/image were checked, but SQL schema/system identity could not be rechecked. Last known schema is `0012_evidence_foundation`; do **not** report it as verified in G5.1. Initial finalization failed trying `docker exec` on that stopped container; the checker now records the limitation explicitly without starting or modifying the demo.
- No demo rebuild/migration, source approval/publication, live-provider call, credential/role change, commit or push. Existing demo assessment/import worker containers remain outside this phase's test target.
