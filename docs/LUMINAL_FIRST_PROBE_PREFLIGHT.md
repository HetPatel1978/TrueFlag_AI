# Luminal first-probe preflight

Follow-ups: [G4.2B.3 first connection result](G4_2B_3_FIRST_CONNECTION.md) and [G4.2B.4 bootstrap implementation](G4_2B_4_BOOTSTRAP.md). The latter supersedes the historical statement below that no bootstrap transport has been implemented.

Review: November 18, 2026. **Live inference requests executed: 0.** This is a partial bootstrap implementation, not a successful connection test.

## Verified locally

- The original package digest and Probe A wire SHA-256 match the previously reviewed synthetic artifacts. The existing adapter reconstructs the exact request, and the independent synthetic source oracle passes. The approved request is unchanged.
- [Preflight service](../backend/app/services/luminal_bootstrap.py) rejects modified artifacts, requires an active administrator and a current case-authorized, independently verified investigation packet, compares it with the exact Probe A bytes and inspects existing Luminal attempt reservations. It does not rely on a pre-existing compatibility flag and has no provider transport.
- The Probe A investigation run and stored packet were **not found in the current isolated local database**. Archived synthetic artifacts are not proof of current case/source authority. Recreating a different run may change the approved payload; do not substitute or forge it.
- The current application status reported clock health available at one observation. Previous clock regressions remain unresolved; this is not evidence of a stable runner or authority for the missing case.

## Remaining blockers

1. A provider-supported upper bound on all billable input and reasoning/output tokens for the exact approved request has not been established. [Luminal pricing](https://www.luminal.com/pricing) says reasoning tokens are billed; it does not establish the required `max_tokens` semantics. The $1 application reservation is not a provider-enforced invoice cap.
2. Establish current source, actor and snapshot authority for the exact approved packet. If a new case changes the wire bytes, it is a changed payload and needs applicable approval.
3. Complete and test an atomic, one-attempt bootstrap transport using the existing durable attempt/receipt ledger. The implemented preflight deliberately cannot reserve or dispatch; it must not be treated as a complete bootstrap. Preserve a reservation on ambiguous outcomes and do not set compatibility verified before validating a real response.

The user withdrew the $200 balance floor; it is **not** a blocker. General live analyst inference and regulatory publication remain disabled. No HTTP status, returned model, token count, latency, structured-output behavior or provider charge can be reported because no inference request was sent. No `.env`, original demo, scientific artifacts or approvals were changed.

## Checks

- Actual frozen synthetic package and source oracle verified offline; altered package, wire and source artifacts rejected.
- Offline preflight/provider checks: **49 passed, 3 skipped, 1 deselected**. PostgreSQL administrator/current-case preflight: **1 passed** using a synthetic test fixture and a mocked wire only for its negative billing gate.
- The first PostgreSQL test run failed because an oversized mismatched fixture returned a sanitized unavailable error; preflight now reports the mismatch as blocked. The corrected test passed.
- Publication boundary check passed. No release or production readiness is claimed.
