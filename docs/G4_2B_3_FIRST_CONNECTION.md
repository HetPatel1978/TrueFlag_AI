# G4.2B.3 first connection result

Follow-up: [G4.2B.4 bootstrap implementation](G4_2B_4_BOOTSTRAP.md) supersedes the historical missing-bootstrap finding below.

**Inference request sent: NO.** Compatibility is unverified. This task did not complete the one-attempt transport or obtain a model response.

## Current gates

- Runtime `bounded_probe_v3` is rejected by `finance_dispatch_allowed`; the normal adapter additionally requires external activation, a machine approval binding, a nonzero call allowance and a verified contract. The normal path cannot perform its own first compatibility check.
- The exact approved Probe A run and packet are absent from the current isolated application database. The stored synthetic files verify as historical artifacts, but cannot establish present case, assignment, evidence-revision and snapshot authority. A newly generated run may change the approved request bytes.
- The existing probe authorization retains an application reservation ceiling of $1 and requires a defensible upper bound. [Luminal pricing](https://www.luminal.com/pricing) includes reasoning in output charges, but does not establish whether the exact request's `max_tokens` bounds all billable reasoning or how provider-side prompt/template tokens are bounded. No provider invoice cap was verified. The withdrawn $200 balance floor is not a blocker.
- Public, unauthenticated documentation GETs for `/openapi.json` and `/docs` returned **401**. One read-only authenticated `/openapi.json` documentation GET returned **404**. These were metadata requests with no prompt; none was an inference request. They did not establish token limits, model availability, or authentication compatibility for inference.
- One current local clock-health observation was available, but an isolated PostgreSQL regression encountered `snapshot_clock_unavailable`. A passing rerun does not prove stable clock health.

## Work performed

- Reused the prior exact-package/source-oracle preflight. No compatibility flag was set and no probe payload was modified.
- Added one PostgreSQL provider-wide advisory transaction lock before existing paid-attempt ledger reads and reservations, and before the probe preflight ledger read. This serializes those operations across distinct grants; it is not a reserved attempt and does not establish a provider invoice cap.
- **Still required:** implement and test a dedicated atomic, one-attempt bootstrap transport using the existing attempt and receipt ledger, without requiring pre-existing compatibility; validate authority and bound before egress, retain unknown-outcome reservations, and independently verify the returned payload. No general analyst inference or regulatory changes were enabled.

## Actual result and verification

| Field | Result |
| --- | --- |
| Inference HTTP response / returned model | None |
| Structured output | Not tested against Luminal |
| Provider token usage / charge | Unknown; no inference was sent |
| Offline exact-package and adapter tests | 49 passed, 3 skipped, 2 deselected |
| Isolated PostgreSQL provider, concurrency and security suite | 19 passed, 1 failed with fail-closed clock denial; failed test passed on isolated rerun |
| Provider-ledger transaction lock and preflight tests | Included in the 19 passing PostgreSQL cases |

No `.env` or original demo modification, inference request, provider compatibility claim, commit, push or deployment was performed. Existing local services were not restarted. No production or clock-stability acceptance is claimed.
