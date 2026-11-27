# Native Windows: real Claude and regulatory investigation gate

## 1. Current execution boundary

- Native Windows is the primary development/demo runtime. Frontend: `http://127.0.0.1:54464`; API: `http://127.0.0.1:54463`. Use `scripts/start_trueflag_windows.ps1 -Action Status` to check current ports and readiness.
- Preserve the running private PostgreSQL cluster, application records, source snapshots and immutable history. This follow-up performs no infrastructure restart, migration, provider activation or paid request.
- Current native read-only inventory: **0 sources, documents, versions, approvals, releases, contexts and grants** in the regulatory tables. No accepted review was found under `assets/local/regulatory/reviews/`; the committed reviewer registry is empty/unapproved.
- The owner subsequently confirmed that a qualified reviewer still needs to be appointed and that no reviewer identity, qualification reference or completed decision is available. This supersedes the earlier statement that approval existed; it supplies no source publication authority.
- This is an observed approval dependency, not permission to manufacture a reviewer, use a test approval, substitute research text or label simulation as real Claude.

## 2. Exact source review handoff

Private directory:

```text
runtime/windows-native/c60bf6f3100c4eba97fc5450a5906891/regulatory-review-d5e790e8f3cd45f9bba9989c51886760/
```

| Artifact | Purpose |
|---|---|
| `ecfr-bank-2026-11-02.xml` | Unchanged complete dated Part 1020 acquisition |
| `ecfr-us-banks-complete-selected-sections.json` | Complete extracted sections 1020.210/1020.320, including original locators and hashes |
| `fincen-sar-faqs.html` and matching selected-sections JSON | Unchanged candidate, explicitly unapproved/excluded pending historical validity |
| `source-decisions-UNSIGNED.json` | Blank reviewer decisions; no approval authority or invented identity/date |
| `independent-review-packet.json` | Existing 31-case independent evaluation workflow, with null labels |
| `reviewer-registry-UNAPPROVED.json` | Copy of the existing empty registry; requires actual authorized owner/reviewer input |
| `file-identities.json` | SHA-256 of each handoff file, exclusive-created; no legal certification |

The existing bounded parser recomputed raw, full extraction and every selected-section identity against `contracts/regulatory_source_proposals.json`; **both candidates matched**. No new network acquisition or claim about current law was made. The eCFR raw SHA-256 remains `2588950c5c16efb45a2a78369e08bda2174bf9a8be5afd634235a406f51924bb`; the HTML raw SHA-256 remains `c6a9c857bfc6bfc3a5f22049949bb3b6f190f66440e8978e5a185583dbaab50e`.

## 3. Actual reviewer actions still required

1. Supply the qualified reviewer's actual identity, qualification/conflict reference and completed private decision. No application account or engineering author is automatically an independent AML/legal reviewer.
2. Review complete eCFR sections and exceptions, institution/charter/regulator applicability, rights, incorporated cross-references and amendment evidence for the **historical 2026-11-02 US-bank/English scope**. Do not describe that corpus as current law.
3. Resolve date/provenance precision: the original acquisition date is known, but an exact HTTP timestamp is not. Approve an explicitly evidenced curation event/interface interpretation or provide genuine acquisition evidence. Do not invent an earlier timestamp to satisfy `VersionSpec.retrieved_at` or the historical knowledge cutoff.
4. Record accept/revise/reject, limitations and separate permission for publication and external AI grounding, bound to exact raw/extracted/section identities and the final version-manifest hash. Keep FinCEN excluded while its historical interval is unresolved; the research PDF also lacks a production parser.
5. Use existing `ReferenceService.register_source`, `admit`, `approve_version`, `proposed_release`, `publish` and `grant` operations only after the corresponding actual decisions. An official version's human approver must differ from its admitting curator, and the review dossier SHA-256 must be supplied. A blank source form is not the version or release approval contract.
6. Record actual independent benchmark labeling/adjudication through the existing `scripts/regulatory_review_workflow.py`; the separate reviewer/adjudicator/evaluation-owner requirements remain intact. Do not report expert retrieval metrics from engineering hints or unreviewed labels.

See [source checklist](PHASE3_4_SOURCE_APPROVAL_CHECKLIST.md), [reviewer guide](PHASE3_4_REVIEWER_GUIDE.md) and [governance workflow](G5_1_SOURCE_REVIEW_AND_GOVERNANCE.md). Review templates do not automatically admit/publish sources. The metadata-only research endpoint explicitly returns `eligible_for_ai_grounding=false`; `RegulatoryInvestigationService._origin` requires official, human-reviewed sources outside tests.

## 4. New exact Claude request: not yet eligible

No grounded request body/hash has been generated or approved in this follow-up: there are **no permitted passages or published source-version identities** to bind. Creating a payload from unapproved material would bypass the existing contract.

The existing grounded Claude path also requires verified provider compatibility and ordinary investigation authorization. Its development-only evidence probe cannot acquire regulatory scope: `ClaudeProvider.propose` rejects grounded non-investigation purposes, and `RegulatoryQueryClaudeConfig` requires the existing investigation financial scope. The earlier development-specific withdrawal of financial limits is not silently applied to that separate scope. Preserve these gates and obtain the applicable compatibility/operating/financial decisions before claiming a grounded request is dispatchable. No setting is marked verified by an offline response fixture.

After genuine source/release/grant decisions:

1. Recheck native clock health, current assignment, evidence/access revisions and source permissions; create a fresh server-verified packet through the existing durable workflow.
2. Retrieve applicable permitted passages and freeze their document/version/chunk/release/context IDs, text hashes, historical scope and grant revision in the job binding.
3. Use the existing Claude adapter/wire schema to construct the exact synthetic-only request. Candidate contract currently selects `claude-sonnet-5-5` and plain HTTPS `https://api.anthropic.com/v1/messages`; this is configuration, **not proof of paid API/model acceptance**.
4. Present the **full request file**, exact byte count/SHA-256, schema/wire version, all source identities, bounded input/output/response bytes, timeout, one-attempt/no-retry and single-outstanding-request controls. Verify no credential or real customer data enters the body. Preserve applicable current ledger/financial authorization and history.
5. Obtain a new explicit owner decision against that identified body. Old pending/consumed evidence-only approvals do not authorize it. The original 900-second snapshot/binding limit still applies during review: if it expires, stop and prepare a newly identified request for approval; do not refresh timestamps or substitute a different packet under the old approval. Do not expose general analyst generation.
6. Only then dispatch once. Record sanitized HTTP response/error, returned model, structured validation, usage and estimated/reported cost separately. Ambiguous outcome consumes the attempt; no automatic paid retry.
7. Revalidate source/assignment/snapshot authority and independently recompute financial claims, validate evidence/citation membership and preserve uncertainty before publication. A valid citation identity does not itself certify a legal interpretation; source/claim support still needs the required human review.
8. Exercise the actual React result and refresh persistence. Report live acceptance only if that entire path ran successfully.

## 5. Evidence available now

- Actual native Chromium foundation: login, assignment, RF/27 grouped SHAP contributions, durable evidence packet/source verification, unavailable unapproved guidance, browser refresh, persisted human note/history and logout denial passed. No mocked transport was used to claim this journey.
- Actual native worker hard-crash recovery: expired lease recovered, attempt 2 succeeded, exactly one assessment, idempotent replay reused the result, PostgreSQL uptime unchanged, case remained open.
- Pinned native ML: **178 passed**, 88 subtests; **4,000 RF / 12,000 policy / 4,000 SHAP comparisons, zero mismatches**. Original artifacts remain unchanged.
- Additional native official-candidate verification: **21 passed / 0 failed / 0 errors / 0 skipped** using unchanged proposed/research bytes in a separate private source copy and disposable PostgreSQL schemas. Includes unapproved-version API/tool withholding, source/locator integrity, 19/31-case candidate diagnostics and authorization/revocation controls. Engineering diagnostic labels remain unreviewed; this is not independent legal/retrieval acceptance or live Claude compatibility. Receipt: `regulatory-candidate-verification-04cad33315ff4a858e86f19a5b00e225/` under the private native runtime.
- Two actual native provider-process checks passed: the isolated offline adapter produced an explicit abstention; the Claude child rejected disabled activation with no HTTP status/transport. This exercised real Windows Job Object children using dummy test-only credentials, not a real key or model response. Application simulation and live activation remained off. Receipt: `native-provider-boundary-check.json`.
- Full native Windows/PostgreSQL backend suite: **1,439 passed / 0 failed / 0 errors / 124 skipped**, 1 warning, **17m 40s**. Saved JUnit and skip classification: `backend-verification-aae177a76aef4ba6a9e697d27450c9ff/`. Skips: 53 Linux-specific, 59 separate isolated rehearsals/evaluations, 5 legacy probe fixtures, 7 unstaged official-source fixtures. The 21-pass source supplement covers its own selected checks; counts overlap and are not summed. See [native acceptance report](WINDOWS_NATIVE_RUNTIME.md).
- This follow-up: **live API requests executed: 0**; no official source approved/published; no general live AI enabled.

## 6. Short video runbook

| Time | Actual screen/action | What to explain |
|---|---|---|
| 0:00-0:20 | Open the native frontend and sign in using the private local login file | Native Windows app; synthetic data; no credentials recorded |
| 0:20-0:50 | Open authorized connected velocity case `/#/cases/64b8876f-5527-404d-b0de-dab49a475b4d` | Existing assignment and case state; direct fixture link is separate from uploaded-session lists |
| 0:50-1:20 | Assess Alert, then expand Key Risk Drivers | Actual fitted RF result and SHAP; prioritization signal, human decision remains separate |
| 1:20-1:50 | Review Evidence | Linked customer/accounts/transactions and deterministic totals with source references |
| 1:50-2:10 | AI Investigation | **Currently unavailable**: do not represent an evidence summary or simulation as Claude |
| 2:10-2:30 | Regulatory Guidance | **Currently withheld**: genuine source approval/publication is missing |
| 2:30-3:00 | Human Decision / existing Casework history / Activity History; refresh | Persisted human work, source/audit provenance; no automatic closure or SAR filing |

After the new exact request is approved and independently passes, replace only the two blocked recording segments with the genuine Claude result: show provider/model and actual findings, open the returned authorized financial/source references and regulatory passages, then refresh and confirm the same stored run remains visible. Do not perform an extra paid generation solely for recording. Record the verified stored result and disclose any abstentions or missing evidence.

**Full real Claude + official Regulatory RAG video acceptance: BLOCKED pending actual reviewer input and subsequent exact-payload approval.**
