# G4.2B.4 — synthetic probe and first-request bootstrap

**Live inference requests: 0. The probe remains blocked.**

## Fixture recovery

- The original Probe A package, synthetic bundle and packet are available in the previously staged private artifact directory. The package and request hashes and the independent synthetic oracle pass existing offline checks; the original request SHA-256 is `135f684427912c0231d0a97f09f7773ff73882e033aed5045fd59fd350c886f6`.
- The original investigation run and packet were not found in the current isolated database. The preparation test created them in a temporary PostgreSQL schema that its fixture drops at teardown. No restorable original schema backup was located in the probe-run directories.
- The saved source bundle and packet do not include the complete original database transaction state, including the run's input manifest, actor/assignment and authorization history. Replaying the bundle through supported services creates new identities and cannot establish that the original approved packet is current. Exact database restoration and current source authorization are therefore **not established**; no replacement data was fabricated or inserted.

## Bootstrap implementation

- [OneAttemptProbeBootstrap](../backend/app/services/luminal_bootstrap.py) is an operator-only internal path, disabled by default. It validates the exact fixed package and source oracle, a versioned scope record, administrator and worker authorization, current packet and clock; it uses the existing provider-wide transaction lock and immutable draft attempt/receipt ledger.
- It reserves at most one attempt with the approved input/output and reservation limits, rechecks before transport, uses the existing fixed-host Luminal adapter, independently validates the returned structure and source references, and retains attempts on failure or ambiguous outcomes. No automatic paid retry or general-investigator activation is introduced.
- The bootstrap does **not** require or set `investigation_provider_contract_verified`. A dedicated opt-in setting defaults false. The source's `_billing_contract_verified()` and `_terms_contract_current()` currently return false and cannot be enabled by API input or environment settings; a reviewed implementation backed by authoritative evidence is required before real dispatch. The separate authorization record reflects the user's explicit exact-probe instruction; it is not a signed identity attestation.
- Model usage is a provider-reported token count multiplied by configured conservative rates, not a settled invoice. HTTP status and sanitized response provenance are recorded when available; unknown delivery retains its full reservation.

## Billing and terms

- [Luminal pricing](https://www.luminal.com/pricing) lists the candidate model, output pricing inclusive of reasoning, per-response usage reporting and text request/token rate limits. These do not prove that the approved `max_tokens` bounds every billable reasoning/output token, that all prompt/template tokens fit the admitted input bound, or that a provider-enforced $1 hard cap exists.
- The previously approved payload remains subject to its $1 application reservation ceiling; the withdrawn $200 balance floor is not a prerequisite. No assertion is made that the reservation caps the provider invoice.
- The current provider terms/privacy version has not been independently reverified against the version covered by the earlier narrow synthetic-probe acceptance. No broader data-use permission is inferred.

## Result

| Check | Result |
| --- | --- |
| Exact synthetic fixture restored | No; original database state and current authority unavailable |
| Approved payload hash | Pass, offline |
| Current source/clock authorization | Not established for the original packet |
| One-attempt bootstrap | Implemented, disabled and tested with mock-only provider transport |
| Billing bounds and current terms verified | No |
| Genuine inference request / HTTP response | None |
| Structured output and actual usage | Not tested against Luminal |

## Tests and limitations

- Offline exact-artifact, adapter, budget and credential-binding tests: **52 passed, 3 skipped, 2 deselected**. These include the actual locally staged synthetic package; no provider transport was used.
- Isolated PostgreSQL bootstrap, revocation, one-attempt, concurrent-reservation and controlled-clock tests: **30 passed**. The provider transport in the bootstrap tests was HTTPX `MockTransport`; billing and terms checks were explicitly mocked only inside tests.
- Existing mock-provider, authorization, budget and clock-policy regressions: **37 passed**. Lint, formatting and publication-boundary checks passed.
- Earlier development runs exposed a missing immutable draft-request envelope, a response-error classification defect and an intermittent clock denial; the implementation/tests were corrected and the stated final suites passed. One passing clock rerun does not establish stable host time.
- The isolated local application was not restarted or deployed for this change. No model artifact, source approval, original demo database, `.env`, commit or GitHub push was changed.

Next: locate a verified backup containing the original fixture and its authorization state, or prepare a new exact-payload approval if supported restoration changes the bytes. Obtain authoritative provider evidence for the token/billing bounds and current reviewed terms. Only then can the separately enabled bootstrap be reconsidered for one request.
