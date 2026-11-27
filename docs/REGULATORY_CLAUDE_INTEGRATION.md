# Regulatory / Claude integration — 21 November 2026

## Decision and approval inventory

**G5.3 follow-up:** [Durable binding implementation and actual live-request results](G5_3_CLAUDE_REGULATORY_INTEGRATION_REPORT.md) supersede the pending-durability status below. Candidate 0021 is tested only in isolated schemas; the running app remains 0019. One real Claude request returned HTTP 400. Official approvals remain missing and full acceptance remains blocked.

**APPROVAL RECORD MISSING. Official publication and live regulatory-grounded inference remain disabled.** The owner clarified that the approval path is not established and that verbal confirmation is not a signed record.

- Checked `assets/local/regulatory/`: only `proposed/` and `research_v2/` exist; `reviews/` is absent. Protected G5 review locations contain a human-review task packet and a synthetic protocol registry, not a subsequently accepted official source decision.
- Read-only inventory of the identity-verified isolated local application database: **0 official-source version approvals**. No original demonstration database access or modification.
- `python scripts/verify_reference_proposals.py`: original and extracted identities verified against the existing proposal; both sources remain pending. Source proposal hash: `832f42eafdc27a1e7847a8acf21c4b0615c8ca129f3117df969ec116fefc84c1`.
- Initial eligible review scope remains complete 31 CFR 1020.210 and 1020.320, US / us_bank / English / historical **2026-11-02**. Current pages were not substituted. FinCEN HTML remains excluded from publication.
- Actual approved source versions: none found. Sources published by this task: **0**. No approved reviewer labels were found; Precision@5, Recall@5 and MRR against accepted independent ground truth remain **not measured**. No independent evaluation acceptance is claimed.

Required record location: save the actual authorized source-review dossier under `assets/local/regulatory/reviews/` and provide its precise path. It must identify the exact original/extracted/section hashes, historical scope and institution applicability, reviewer authority and decision, publication/AI-grounding permission, limitations, and associated accepted evaluation labels/conditions. Existing independent reviewer-registry, version approval, release and access-grant requirements still apply. This task created no reviewer identity, signature, approval timestamp, label or grant.

## Implemented non-publication integration

| Component | Implemented behavior |
| --- | --- |
| `backend/app/services/regulatory_investigation.py` | Reuses the existing coordinator to verify the selected packet, existing PostgreSQL lexical retrieval and governed selection revalidation. Binds case, run, packet and regulatory context through a versioned digest. Rechecks current evidence, approval, exact citation fields, grants and source lifecycle before provider handoff and verification. |
| `backend/app/schemas/regulatory_investigation.py` | Bounded input/context/output contracts. At most five passages; combined context capped at 48 KiB. Explicit human-review, untrusted-reference and no-legal-certification fields. No reviewer personal data in the minimized provider payload. |
| `POST /api/v1/cases/{case_id}/investigations/{run_id}/regulatory-context` | Protected, size/rate/capacity-bounded `ReferenceQuery` request. Requires a current verified investigation. Returns approved-search results plus run, packet and binding hashes; no curation or publication operation. |
| Existing Claude codec/adapter/process | Opt-in structured regulatory schema, exact binding constant and supplied citation-ID enumeration. Existing financial verifier is retained, with an additional independent citation-membership and current-source check. Unapproved activation is blocked before transport. `regulatory_investigation_enabled` defaults false. |
| Existing React investigation screen | Guidance search can bind to its selected verified summary through the new endpoint. Source opening still uses the protected reference-resolution API. Case/run changes remount guidance state and abort requests. Test-fixture passages remain excluded from official UI guidance. |

Empty/unavailable retrieval produces an explicit unavailable result. It cannot be converted into approved provider grounding; the existing evidence-only/simulation workflows remain separate. Retrieved instructions are passed as untrusted data with no tools or case-action authority. Citation identity verification does not certify legal reasoning, applicability or factual entailment of model prose.

## Important incomplete integration

- This is the approved-context preparation/verification bridge and transport contract, not a newly activated durable AI pipeline. Persisting a chosen regulatory binding with a durable draft job and wiring its revalidation into every worker dispatch/completion/read remain pending; the current draft gateway still exposes offline simulation.
- The existing Claude candidate migration remains outside the active release. No source publication, application migration, general live-provider activation, `.env` edit, frozen ML change, commit, push or deployment occurred.
- Actual live inference requests in this task: **0**. The historical five Claude calls remain unsuccessful at the complete independent verification gate. Offline/mock transport results do not establish live compatibility or model quality.
- Clock-stable integrated acceptance remains unresolved. Successful reruns do not establish stable Windows/WSL clock behavior.

## Actual verification

| Command / scope | Result |
| --- | --- |
| `runtime/local-app/test_upload_sessions.py backend/tests/test_regulatory_investigation.py backend/tests/test_regulatory_context.py backend/tests/test_references.py` | 72 passed on the intermediate implementation; synthetic fixture retrieval/publication/revocation, not legal-source approval. |
| Later handoff/context run | 31 passed, 1 setup error: `ClockUnavailable` before the source-revocation test assertion. Retained as an unresolved failure. |
| Final `...test_upload_sessions.py backend/tests/test_regulatory_investigation.py` | 12 passed: source/binding/citation forgery, revocation, wrong user/case, unavailable context, synthetic-only scope, instruction-text containment, protected API, existing simulation and opt-in Claude MockTransport. |
| Claude contract/provider Windows tests | 27 passed before final formatting; no network calls. |
| React guidance/investigation/draft tests | 30 passed; subsequent complete React suite: **148 passed**. Frontend build, ESLint and changed-file Prettier checks passed. Changed Python files passed Ruff checks/formatting. Publication-ignore boundary check passed. |
| `scripts/run_ml_verification.py --check tests` | 178 tests passed in the pinned Linux runtime with network disabled. Full 4,000/12,000/4,000 comparisons were not rerun by this task. |

Initial Chromium `runtime/local-app/ux_e2e.py --suite drafts`: **4 passed, 2 failed**. The one-action test waited for the previous `/references/search` URL; its assertion was corrected to require the specific verified investigation's `/regulatory-context` URL and returned binding hash. The partial-evidence test encountered the clock-safety unavailable screen during its click; it did not complete its assertion. Wrong-analyst isolation, source revocation and controlled clock regression passed. The failures are retained even if a later rerun passes.

Final Chromium rerun after the URL assertion correction: **6 passed**, using actual FastAPI/PostgreSQL/workers and the controlled simulation. It exercised investigation-bound unavailable regulatory retrieval, evidence-linked simulated findings, partial-evidence abstention, history/logout, cross-analyst isolation, source revocation and a controlled clock regression. It did not exercise an approved official corpus or real Claude inference. No production clock-stability or live-model acceptance is inferred. The local application was reloaded with the tested endpoint; its database remains at 0019, official approvals remain zero and live-provider activation remains off.

Test counts overlap; do not sum reruns as independent acceptance. Complete application readiness: **NOT ACCEPTED** until approval, durable grounding persistence, real-model verification, clock reliability and complete browser workflow acceptance pass.
