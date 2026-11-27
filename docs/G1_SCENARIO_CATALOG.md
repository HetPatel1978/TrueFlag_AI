# G1 scenario catalog

- Catalog: `trueflag.connected-scenarios.v1`; seed `1701`; as-of `2026-01-01T00:00:00Z`.
- Window: `[2025-10-03T00:00:00Z, 2026-01-01T00:00:00Z)`; explicit offsets, half-open bounds; Decimal amounts.
- These are fictional observations for investigation exercises, not criminal labels or validated detection typologies.
- `complete_declared_window` is an explicit fixture coverage declaration, not external proof of a bank's complete historical records. Account base currency does not supply an FX rate or settlement evidence.
- All 16 scenarios passed the earlier 44-case Linux/PostgreSQL focus and their cases in the completed full suite, including real RF/Policy/SHAP, analytics and independently verified packets. Latest final-source focus: 46 passed, 1 clock-denied failure. Full acceptance and retained-cohort status are reported separately.

| Scenario | Events | Currency | Incoming | Outgoing | Gross total | Coverage / interpretation |
|---|---:|---|---:|---:|---:|---|
| `ordinary` | 12 | USD | 243.16 | 406.41 | 649.57 | complete_declared_window; Ordinary observed activity; no criminal label |
| `velocity` | 12 | USD | 4243.16 | 8406.41 | 12649.57 | complete_declared_window; Twelve events in twelve hours |
| `related_transfers` | 12 | USD | 1000 | 2000 | 3000 | complete_declared_window; Repeated transfers to a declared co-owned account |
| `concentration` | 12 | USD | 4000 | 6020 | 10020 | complete_declared_window; Ten large observations to one of two counterparties |
| `flow_change` | 12 | USD | 600 | 9000 | 9600 | complete_declared_window; Earlier incoming versus recent outgoing observations |
| `high_kyc` | 12 | USD | 243.16 | 406.41 | 649.57 | complete_declared_window; Declared KYC 5; preserve Coverage protection |
| `partial_customer` | 12 | USD | 243.16 | 406.41 | 649.57 | complete_declared_window; Income and expected activity unavailable |
| `missing_income` | 12 | USD | 243.16 | 406.41 | 649.57 | complete_declared_window; Missing income is not observed zero |
| `zero_income` | 12 | USD | 243.16 | 406.41 | 649.57 | complete_declared_window; Explicit recorded zero income |
| `corrections` | 13 | USD | 243.16 | 488.00 | 731.16 | complete_declared_window; Duplicate delivery and matched reversal |
| `conflicting_kyc` | 12 | USD | 243.16 | 406.41 | 649.57 | complete_declared_window; Two contradictory income observations |
| `incomplete_history` | 4 | USD | 160.71 | 139.93 | 300.64 | partial; Only four observed events; no whole-history claim |
| `source_revision` | 12 | USD | 244.16 | 406.41 | 650.57 | complete_declared_window; Revised event; original alert features stay immutable |
| `source_revocation` | 12 | USD | 243.16 | 406.41 | 649.57 | complete_declared_window; Explicit post-setup revocation exercise |
| `multi_currency` | 6 | CAD | 120.17 | 135.76 | 255.93 | complete_declared_window; Separate USD/CAD totals; no inferred FX |
| `multi_currency` | 6 | USD | 122.99 | 270.65 | 393.64 | complete_declared_window; Separate USD/CAD totals; no inferred FX |
| `unknown_time` | 11 | USD | 161.57 | 406.41 | 567.98 | partial; Unresolved timestamp excluded from timed totals |

## Independent expectations

- `concentration`: USD 10,000 / 10,020 to the dominant counterparty; USD 20 to the secondary account. These are observed amount shares, not criminal-risk probabilities.
- `related_transfers`: 12 transfers of USD 250; common account holder is explicitly recorded. No familial, beneficial-owner or third-party relationship is inferred.
- `flow_change`: six earlier USD 100 credits versus six recent USD 1,500 debits. Compare dated observations; do not annualize or assume missing transactions.
- `velocity`: 12 events in 12 hours. Daily bucket counts and totals are independently checked; no learned anomaly threshold.
- `corrections`: 14 delivered transaction objects include one exact duplicate; 13 unique gross observations; excluding the verified reversal pair leaves 11. Original versions remain retained.
- `unknown_time`: 12 source events, 11 timed observations. Unresolved time is not assigned an offset or silently included.
- `conflicting_kyc`, `incomplete_history`, `unknown_time`: verified packet abstains from behavioral interpretation; missing evidence/questions remain visible.
- All packets abstain from money-laundering, violation and SAR conclusions; model signals remain separate from facts.

## Revisions, revocation and traceability

- `source_revision`: admit v1/create its case, then admit/link v2. The first transaction amount increases by USD 1; immutable alert declarations remain v1. Old signed evidence snapshots become stale.
- `source_revocation`: starts readable so its assessment/evidence can be inspected. Revocation is an explicit separate service call; setup never automatically revokes, regrants or closes a case.
- Scenario UUID: UUID5(catalog namespace, `seed:key`). Source UUID: UUID5(admin UUID, scenario UUID string). Account/customer/transaction identities: UUID5(source UUID, canonical record key). Record-version UUIDs are source-scoped, versioned and generated by EvidenceService.
- Case/alert IDs come from actual ingestion, not fabricated deterministic predictions. `EvidenceCaseBinding` freezes their source/version/input hash; `CaseEvidenceLink` retains version membership; access/evidence revisions fence stale reads.
- Protected setup receipts contain the exact actual case, alert, source, source-version, job and assessment IDs. See the G1 implementation report for retained cohort limitations. Never substitute source-record IDs from another case.

## Feature interpretation

- Every RF predictor is a separate explicit synthetic scenario declaration. Counts/amounts in those declarations are not asserted to be aggregates of this transaction feed; see `G1_FEATURE_PROVENANCE.md`.
- Missing annual income remains null, observed zero remains zero. Partial customer context lacks expected activity and other unrecorded attributes; no new customer facts are invented.
- Frozen RF/Policy/SHAP outputs are obtained through existing services, not selected to produce desired scores. Catalog scenarios are separate from the frozen 4,000 evaluation records.
