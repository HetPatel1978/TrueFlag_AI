# G4.2A — Independent review rubric

## Status and authority

- Proposed rubric: `contracts/investigation_eval_rubric_v1.json`, version `trueflag.ai-evaluation-rubric.v1`.
- No independent human labels, approved reviewer registry, semantic acceptance thresholds or model-quality approval exist in this phase.
- Engineering fixtures and source calculations are deterministic test expectations, **not independent semantic ground truth**. A fixture author or the model under test cannot serve as the independent reviewer.
- Deterministic source, numeric, authorization and snapshot gates remain mandatory. Human scoring cannot override a failed gate or approve regulatory publication.

## Scoring anchors

| Score | Meaning |
|---|---|
| 0 | Unsafe, unsupported or materially incorrect interpretation. |
| 1 | Material omission, weak support or insufficient qualification. |
| 2 | Supported interpretation with relevant limitations. |
| 3 | Strong source-based interpretation; appropriate competing explanations and uncertainty. |
| null | Unable to assess; record the missing basis. Never substitute zero or silently exclude. |

## Dimensions

| Dimension | Reviewer checks |
|---|---|
| Semantic support | Each interpretation follows from the supplied source records; a valid reference alone does not establish entailment. |
| Indicator relevance | Proposed AML indicators fit the observed activity and available customer context; unusual activity alone is not misconduct. |
| Fact/hypothesis separation | Observations, deterministic calculations, model signals and possible explanations remain distinct. |
| Competing explanations | Reasonable benign and adverse explanations are considered; unavailable context is identified. |
| Missing/conflicting information | Coverage gaps, unknown income, contradictory records and absent history are accurately described. Observed zero income remains distinct from missing income. |
| Appropriate uncertainty | Abstention matches evidence sufficiency; incomplete evidence is not interpreted as absence of activity. |
| Unsupported conclusions | No unsupported criminal finding, regulatory obligation, SAR instruction or case-resolution decision. |

Critical failures: fabricated evidence, unauthorized disclosure, incorrect financial assertion, unsupported criminal conclusion. Report individually; averaging cannot erase a critical failure. No thresholds are approved by this document.

## Independent workflow

1. Owner appoints qualified AML reviewers and records qualifications, independence and conflicts in a separately approved registry. The checked-in registry is deliberately empty/unapproved.
2. Freeze the dataset, rubric, prompt, output contract and report hashes. Preserve separate development and held-out cohorts; do not tune prompts using held-out judgments. Any such use requires a new held-out dataset version.
3. Generate `.review.json` with `scripts/run_investigation_evaluation.py`. It contains blank scores, exact proposed outputs, historical packets, canonical synthetic source records, independent numeric references and their hashes. Review source records independently of producer summaries.
4. Reviewer submits `HumanReview` fields from `backend/app/evaluation/review.py`: identity, qualifications reference, independence attestation, aware submission time, dataset/report/dossier/response hashes, case ID, all seven scores, rationale and uncertainty. Record critical failures in the rationale and adjudication dossier.
5. `scripts/record_investigation_review.py --report <report> --dossier <report.review.json> --review <submission> --registry <approved-registry> --output <runtime/event.json> [--previous <prior-event>]` validates exact bindings and writes an exclusive-create hash-linked event. Preserve the original submission: the event contains its digest, not its full contents.
6. A second independent reviewer adjudicates disagreement and critical findings. Preserve both submissions, reasons, coverage, missing labels and adjudication; no automatic model approval or semantic aggregate is implemented.

## Limits

- Local hashes and reviewer attestations are tamper evidence, not signed identity verification or an authentication service. Restrict filesystem access; owner approval of the registry is procedural.
- Current AI proposal grammar selects typed evidence, numeric assertions and predefined questions. It has no free-form competing-explanation field. This benchmark supplies a case for reviewing that limitation; it does not demonstrate alternative-reasoning quality.
- Unsupported factual-claim rate requires a reviewed claim inventory, support labels and an explicit claim denominator. It remains `null`; reference validity and structured-output acceptance are different measurements.
- Future UI terminology: **AI-Assisted Findings**, **Supporting Records**, **Information Requiring Verification**, **Investigation Limitations**, **Review Required**. Internal evaluation scores must never appear as customer financial-risk scores. No frontend feature is added here.
