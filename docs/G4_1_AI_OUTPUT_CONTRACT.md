# G4.1 — AI investigation output contract

## 1. Versions and authority

- Wire schema: `trueflag.ai-investigation-proposal.v1` (`AIProposal` in `backend/app/schemas/provider_live.py`). Stored projection: `trueflag.ai-investigation-draft.v1` (`AIDraftBody`). Existing simulation v1 remains separately supported.
- Prompt: `trueflag.ai-evidence-prompt.v1`; prompt/schema hash bound to immutable run configuration. No model-supplied version, approval, verification result, case selector, tool or legal authority is accepted.
- This MVP is a **bounded selection grammar**, not unrestricted factual prose. The model prioritizes supported records, existing calculations and uncertain inquiry templates. The server renders authoritative observations; natural-language quality/semantic relevance remains G4.2 work.

## 2. Strict proposal fields

| Field | Contract / independent check |
|---|---|
| `schema_version`, `packet_sha256` | Fixed wire version and exact digest of the already independently verified parent packet. |
| `overview` | `review_supplied_evidence` or `insufficient_evidence`; the latter required when source evidence requires abstention. No criminal narrative. |
| `supporting_records` | Bounded unique record-version UUIDs, all in the authorized case packet; review overview requires supporting records. |
| `financial_observations` | <=8 calculated-fact selections; exact supplied calculation ID and full source-input membership. Optional numbers must match independently recomputed Decimal totals/counts, currency and UTC window exactly. |
| `unusual_activity` | <=8 observed-fact selections; exact transaction reference and supporting record. This marks an observation for review, not proof that conduct is suspicious or criminal. |
| `model_signals` | <=1 selected stored assessment; exact assessment identity, approved stored score/SHAP values if asserted. Always distinct from observed facts and crime likelihood. |
| `risk_indicators` | <=8 existing uncertain hypothesis templates, authorized supporting/contradictory records, explicit human-review uncertainty. Existing verifier checks applicable conflict/gap/concentration prerequisites; relevance is not fully semantically validated. |
| `missing_or_contradictory_evidence` | Exact set of supplied gap/conflict codes; no invented gaps and no omission of existing limitations through prose. |
| `follow_up_questions`, `additional_information_needed` | <=20 each, unique selections from the server's question templates. All original unresolved questions remain preserved in stored output. |
| `uncertainty_limitations` | Exact set of supplied limitation codes; original limitations also rendered from the authoritative packet. |
| `next_steps` | <=4 allowlisted inquiry/review actions; server always adds `human_review`. These are recommendations, not executed actions. |
| `abstain`, `uncertainty` | Strict boolean; cannot override required source abstention. Uncertainty fixed to `requires_human_semantic_review`. |

- Extra fields, duplicate JSON keys, nonfinite numbers, oversized payloads and malformed references fail closed. Financial/model/observed groups cannot substitute for each other.
- Original verifier remains authoritative: re-read current authorized source versions; independently verify parent calculations/model identity; validate references and numeric statements; preserve snapshot/clock/source/assignment fencing; atomically persist only after successful checks.
- Correct JSON and valid IDs do not prove semantic support. A verified draft explicitly states `full_factual_entailment_verified=false`, `legal_correctness_verified=false` and `human_semantic_review_required=true`.

## 3. Stored result and failure boundary

- Stored output includes immutable draft/parent/manifest/packet identities, provider/model/prompt/config/attempt provenance, typed reported usage, server-rendered observations, uncertain hypotheses, gaps, conflicts, questions and limitations.
- Candidate mode is `provider_candidate`, not “validated AI investigator.” HTTP mocks simulate this mode only inside disposable tests; no real-provider success is reported by G4.1.
- Existing durable statuses remain Pending/Running/Succeeded/Abstained/Failed/Invalidated. Failed or revoked/stale results provide no invented successful finding. The human case disposition remains separate and unchanged.
- Regulatory citations and human conclusions remain empty; unapproved RAG cannot populate a draft. No transaction history, relationships, totals, legal obligations or SAR/case decisions can be supplied as free-form findings.

## 4. G4.3 frontend contract — defined, not implemented

| Future user-facing section | Server projection |
|---|---|
| AI-Assisted Findings | Candidate status, version, review-required disclaimer; no provider controls for analysts. |
| Supporting Records | Reauthorized record links resolved through case/source scope, never direct arbitrary document URLs. |
| Financial Observations | Stored server-generated calculation summaries, exact currency/period and coverage. |
| Areas Requiring Review | Observed selections and explicitly uncertain hypotheses; separate stored model signals. |
| Additional Information Needed | Server templates and unresolved questions, including original evidence gaps/conflicts. |
| Investigation Limitations | Source coverage, missing data, abstention, non-causality and semantic-review limitations. |

- Future protected request/status/history/detail APIs must select immutable stored case context server-side; clients may not submit feature snapshots, scores, prompts, credentials or arbitrary provider settings.
- Recheck current permissions/source revisions on every disclosure; clear stale views on logout/revocation. G2 design system and terminology are retained.
- Require G4.2 evaluation and explicit activation approval before adding an actionable AI control. Human adoption/rejection/disposition requires separately authorized casework; no automatic case action follows generation.
