# G4.2B — Model quality: NOT EVALUATED LIVE

## Real-model result

| Measure | Actual result |
| --- | --- |
| Authorized / executed Luminal requests | **0 / 0** |
| Live benchmark cases / responses | **0 / 0** |
| Live structured-output success | **Not measured**; denominator zero |
| Live reference / financial correctness | **Not measured** |
| Unsupported factual statements / semantic support | **Not measured**; no reviewed live claim inventory |
| Source-grounded observations / abstention / contradiction handling | **Not measured** |
| Real-model prompt-injection resistance | **Not measured** |
| Provider response latency / input-output-reasoning tokens | **Not measured** |
| Inference spend initiated in this task | **$0**; no vendor account/billing query, no claim about account-wide charges |
| Independent human judgments on live outputs | **0**; awaiting reviewer appointment and actual outputs |
| Model acceptance / G4.3B activation | **NOT APPROVED** |

Do not substitute offline fixture performance, successful connectivity, schema validation or G3 analyst decisions for these measurements. No claim of hallucination-free output or regulatory correctness is supported.

## Prepared benchmark and current offline check

- Existing `trueflag.ai-evaluation-dataset.v1`: **36** scenarios, **18 development / 18 held-out**, disjoint seeds; dataset/rubric/prompt/schema hashes in [compatibility report](G4_2B_LUMINAL_COMPATIBILITY_AND_EVALUATION.md).
- All **36** source-bound synthetic fixtures materialized through the existing isolated PostgreSQL evidence coordinator. Each is independently checked against canonical source records and deterministic financial oracles. No RF/SHAP values or transaction histories were invented.
- Fresh offline replay via existing `run_offline`: **307** controlled responses per split, **614** total; **32** accepted baseline fixtures and **582** deliberately adversarial responses rejected, **0** expectation mismatches. Four lifecycle trials produced four required denials. These are **verifier tests**, not model quality scores.
- Approved-generation scope must distinguish 32 candidate generation cases from four revoked/stale lifecycle cases that require **no egress**. Archived fixture authorization is historical; actual generation must recheck current case/source/assignment/revisions and time.
- Prompt-injection description tests currently use evaluation sidecars because canonical transaction descriptions are absent. The existing minimizer does not turn those annotations into a real attack-bearing model input. This limits any future claim about indirect prompt-injection resistance.
- No prompt changes, held-out tuning, fabricated reviewer scores, simulated paid usage or scientific-artifact changes.

## Prepared independent review dossier

Protected `evaluation-approval-dossier.json` under `runtime/g4-2b/<run>/` lists all 36 case identities/splits/categories/fixture hashes with **null live-response hashes and null independent scores**. Existing offline review dossiers remain explicitly controlled fixtures. No reviewer registry is approved by this task.

| Evaluation layer | Future procedure / current boundary |
| --- | --- |
| Deterministic verification | Existing schema parser, canonical-source membership, exact versions, amount/currency/count/window recomputation, model-signal identity and explicit abstention checks. Store attempted/rejected/unavailable denominators separately. |
| Automated semantic judgment | No separate semantic judge has been run or established. Do not interpret enum/code selection as full semantic entailment. |
| Independent human review | Qualified reviewers, exact report/dossier/response bindings, independence attestations and seven-dimensional existing rubric. Current review fields remain blank; require adjudication of disagreements and critical failures. |
| Financial correctness | Report numeric assertion counts and source-backed correctness, separately from reference membership and prose support. A valid reference does not prove the interpretation. |
| Unsupported claims | Requires a human-reviewed claim inventory, support labels and explicit denominator; remains null until available. |
| Alternative explanations | Current proposal is a constrained selection DSL without free-form competing-explanation reasoning. Evaluate that limitation honestly; do not claim demonstrated AML reasoning quality. |
| Latency / usage / cost | Monotonic wall duration, provider-reported token breakdown, configured-rate estimate and independently reconciled billing are distinct. Timeout/unknown delivery stays a failed/uncertain attempt, not zero usage or success. |

## Freeze and acceptance procedure after separate approval

1. Approve privacy/recipients, exact minimized inputs, scope/expiry, call/spend ceilings, reviewers and metric thresholds. Establish stable isolated execution and complete the compatibility gate first.
2. Freeze dataset, rubric, schema, prompt and approval identities. Use development cases for any authorized iteration; freeze again before held-out evaluation. Held-out labels cannot guide prompt tuning.
3. Reuse existing durable draft attempts, immutable receipts/provenance and verifier. Admit only currently authorized source-bound cases. Failed safety/lifecycle cases must not dispatch or publish.
4. Produce real-output reports with explicit attempted/completed/blocked denominators and independent review tasks. Preserve both accepted and rejected outputs under restricted retention; never present raw unverified output as case findings.
5. Require human adjudication and separately approved thresholds before any evaluated-live badge or G4.3B generation control. Critical fabricated evidence, disclosure, financial errors or criminal overclaim cannot be averaged away.

**Conclusion:** framework readiness and local verifier containment are measured; real Luminal investigation quality is not. Stop at the approval/preparation gate.
