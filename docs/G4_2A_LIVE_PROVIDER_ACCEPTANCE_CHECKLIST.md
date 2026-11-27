# G4.2B — Controlled live-provider acceptance checklist

## Gate status

**NOT AUTHORIZED / NOT EXECUTED.** G4.2A makes zero live calls, transmits no synthetic evidence externally and does not approve a provider, corpus or model. Offline verifier acceptance is not real-model acceptance or production certification.

## Required owner decisions before any call

| Gate | Required evidence | Current status |
|---|---|---|
| Provider/model authorization | Named provider, exact model identity, fixed endpoint, approval owner, scope, expiry, approval ID and terms digest. | Pending |
| Synthetic transfer | Explicit authorization for the exact minimized cohort/input hashes; confirm no real customer data or secrets. | Pending |
| Privacy/retention | Retention, training use, deletion, regions, fallback/subprocessors, contractual and access review. | Pending; G4.1 public documentation is insufficient. |
| API compatibility | Approved bounded probe; exact request/response schema, model identity, error/usage semantics, no unsupported-format downgrade. | Offline mocks only; live support unverified. |
| Structured output | Confirm strict schema support and refusal/incomplete/tool-call handling on the chosen endpoint/model. | Unverified live |
| Budget | Approved total spend, configured rates, token limits, concurrency, number of attempts and stop conditions. Allowance for conservative reservations and unverified vendor billing. | Pending |
| Secrets | Server-managed secret, restricted worker environment, rotation/revocation, no browser/Git/log exposure. | Existing disabled adapter; no credential approval implied. |
| Cohort/independence | Approved synthetic development/held-out versions, source hashes, reviewer roster and adjudication process. | G4.2A proposal; human approval pending. |
| Acceptance thresholds | Human-approved metric thresholds, missing-label policy, critical-failure rules and operational limits **before** live results. | None approved; do not backfit. |
| Clock/environment | Independently clock-stable isolated runner, fresh source/auth checks, validated schema and readiness. | Existing local backward-clock blocker remains. |

## Execution boundaries after separate authorization

1. Keep candidate disabled until every approval is recorded. Use the existing G4.1 adapter, durable attempts, conservative spend reservations, verifier and audit path; no second investigator.
2. Run a separately approved minimal compatibility probe first. Reject unavailable schema support, unexpected model aliases, missing usage or unapproved provider fallback. Do not silently downgrade to free text.
3. Freeze dataset/prompt/rubric/contract/approval versions. Record actual returned model identity and attempt IDs; retain minimized-input/output hashes and independently verified source/calculation references.
4. Distinguish measured monotonic elapsed time, vendor-reported tokens, configured-rate estimates and vendor-verified billing. Never report mock token/cost fixtures as paid inference measurements.
5. Reuse permission, source-revision, 900-second expiry, clock-floor/epoch and publication checks. Rejected or unavailable evidence must not be published. No regulatory retrieval until a separate approved publication gate is satisfied.
6. Evaluate actual structured outputs using deterministic checks and independent human review. Report schema acceptance, source/numeric accuracy, rejected outputs, semantic coverage, abstention, latency, failure/retry/cancellation and denominators separately.
7. Stop on unauthorized disclosure, unsupported financial assertion, unexpected external route, unresolved time uncertainty, spent budget or failed required compatibility. No automated case closure, dismissal, SAR filing or regulatory conclusions.

## Disable and recovery rehearsal

- Withdraw the server-side candidate approval and disable external execution; revoke/rotate the key through the approved secret-management procedure if needed. Do not edit credentials during G4.2A.
- Cancel/fence active attempts through existing services; verify dispatch and publication rechecks deny withdrawn approvals and revoked source access. Retain immutable reservations, receipts and audit history.
- Unknown paid-request outcomes remain conservatively reserved and are not automatically redispatched. Review uncertain jobs manually; preserve evidence-only/simulation availability without inventing provider results.
- Verify disabled operation and no new egress, retain incident evidence, then require fresh explicit approval to resume. No deployment, activation or G4.2B work is authorized by this checklist.
