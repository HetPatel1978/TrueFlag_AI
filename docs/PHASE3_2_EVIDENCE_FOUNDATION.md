# Phase 3.2 - Frozen implementation contract

Contract frozen before migration authoring on 2026-11-03, starting at `b0af194`. User authorizes local synthetic evidence only. No LLM/RAG/public evidence API/frontend, external source, document upload or historical backfill.

## Selected minimum schema and access

Twelve additive tables: `evidence_sources`, `evidence_source_versions`, `evidence_identities`, `evidence_record_versions`, `evidence_customers`, `evidence_accounts`, `evidence_relationships`, `evidence_transactions`, `case_evidence_states`, `evidence_case_bindings`, `evidence_source_access`, `case_evidence_links`.

- Sources are owned/registered by an active admin; only that active admin may admit/correct, bind, link or grant/revoke. An explicit source-to-case access record permits currently authorized case readers to obtain an internal redacted manifest. No source-owner privilege overrides a denied case. Current workspace roles remain unchanged.
- One generated source/scenario can bind to one **new** alert/case through the existing atomic ingestion core. An immutable binding proves that creation; linking generated history to arbitrary legacy cases or another case/source is rejected. An incomplete source can exist without a Case; mandatory `Case.alert_id` is never bypassed.
- UUID identities, source-scoped stable record keys/kinds, unique source/release and identity/version; composite FKs enforce same-source source versions, corrections, typed payloads and account/party/relationship references. Explicit corrections retain prior versions; releases are complete source snapshots, not silent last-write-wins merges.
- Source/release/record identity and typed observations/binding/audit are immutable. Exactly one correct typed payload per record version is checked at PostgreSQL commit. No legacy Evidence/Alert/Case/assessment record is rewritten. Version history and source bytes are represented as typed synthetic records/hashes, not arbitrary objects/URIs.
- Transaction money is finite non-negative exact `NUMERIC(24,8)`/Decimal (less than 10^16), with explicit currency, direction, event kind, aware timestamp or explicit unknown time, original time and source quality. No settlement status is invented. Reversal identity is explicit and source-scoped; it is not a correction or inferred negative amount. Duplicate key/different content conflicts unless submitted as an explicit new source release.
- Grants are case/source scoped, not inferred from a common customer/account ID. Case manifests recheck live actor/assignment and active source access before reading; raw declarations and oracle labels are omitted. No public evidence retrieval is added.

## Revision/atomicity contract

| Operation | Evidence revision | Access revision |
|---|---:|---:|
| Admit source version, unlinked | No case change | No case change |
| New case binding + initial source grant | 0 | 1 |
| Link one or multiple exact versions in one operation | +1 if new/reactivated links | +1 if visibility changed |
| Revoke exact linked versions | +1 if active links changed | +1 |
| Revoke/restore source grant | Unchanged membership | +1 if changed |
| Matching admission/link/grant retry | Unchanged | Unchanged |

Owner/user locks serialize mutation with role revocation; source/case locks arbitrate concurrent retries. Full source release admission and all typed writes/audits are atomic. Case creation, ingestion receipt, immutable source binding, grant, links/revisions and audit commit together. Any failure rolls back the entire operation. No automatic assessment job is created; explicit existing queue/worker can score the new case afterward.

## Generator and provenance contract

- Fixed caller-supplied scenario UUID, bounded integer seed, generator/config versions, explicit aware as-of, canonical ordering and UUIDv5 record identities. No current-time/random-UUID dependency in generated content. Parameters, record digests, feature-declaration and dictionary identities bind the manifest; observed-at/as-of differ from DB admission time.
- Fictional aliases only (`SYN-CUSTOMER-*`, `SYN-ACCOUNT-*`); no real names, contact/address/identity numbers. No arbitrary evidence upload or external network. Admission is limited to supported generated bundle profiles; re-generation validates that an admitted bundle matches its declared generator/configuration.
- Fourteen profiles: normal activity, concentrated/burst activity, partial feed, unavailable feed, missing income, observed-zero income, out-of-order events, corrections/duplicate events with explicit reversal, multi-currency, unknown/offset timezone, inconsistent KYC, incomplete feature declarations and eight-decimal precision. Oracles live in test-only code and are not included in source/record payloads, manifests or RF inputs.
- Coverage is a declared source interval and complete/partial/unavailable status, not inferred from row count. A zero-row unavailable feed never means no activity. Contradictory KYC snapshots remain separately identified observations; a correction has an explicit predecessor, never an overwritten value.

## 27-feature matrix - declared synthetic inputs, not invented derivations

Dictionary inspected individually: all 27 documented entries present; trusted file SHA-256 `6d262b3b8cce169fd3898019d46bb0dc542a3054f51ff3f2c80d5cf3b14de442`. Definitions/units/windows inform the following source classification, but raw event equations/codebooks are not supplied by this implementation. **All 27 default inputs are explicit versioned scenario declarations. Zero features are claimed fully reconstructed from transactions.** Values may deliberately illustrate inconsistencies; no narrative may call these reconstructed historical facts.

| Predictor | Source / method | Window / units | Missingness / unresolved semantics | Status and tests |
|---|---|---|---|---|
| kycRiskScore | Declared opening-profile input | Opening; source score units | Codebook/direction undefined; preserve frozen supported 0..6 | Declared; exact field/missing/type tests |
| income | Declared annual profile input | Annual; baseline monetary units | Currency/rounding unspecified; null distinct from zero | Declared; null/zero tests |
| tenureMonths | Declared account input | Months, source snapshot cutoff unspecified | Required; no invented account-age equation | Declared; field-completeness tests |
| creditScore | Declared credit input | Snapshot; source score units | Bureau/bounds unspecified; required | Declared; completeness/type tests |
| state | Declared billing-state code | Snapshot, code | Preserve recorded category; not jurisdiction proof | Declared; exact category tests |
| nbrPurchases90d | Declared activity aggregate | Intended 90-day pre-alert; events | No imposed posting/reversal/cutoff rule | Declared; completeness/contract tests |
| avgTxnSize90d | Declared activity aggregate | 90 days; baseline monetary units | Included transaction kinds/rounding unknown | Declared; no division-derived claim |
| totalSpend90d | Declared activity aggregate | 90 days; baseline monetary units | Netting/currency/cutoff unspecified | Declared; complete input tests |
| nbrDistinctMerch90d | Declared merchant aggregate | 90 days; count | Merchant identity equivalence unspecified | Declared; complete input tests |
| nbrMerchCredits90d | Declared merchant-credit aggregate | 90 days; events | Credit inclusion rules not invented | Declared; complete input tests |
| nbrMerchCreditsRndDollarAmt90d | Declared merchant-credit aggregate | 90 days; events | Currency and round-dollar convention unspecified | Declared; not calculated from fractional parts |
| totalMerchCred90d | Declared merchant-credit aggregate | 90 days; baseline monetary units | Currency/netting unspecified | Declared; complete input tests |
| nbrMerchCreditsWoOffsettingPurch | Declared unmatched-credit aggregate | 90 days; events | Matching/offset rule unspecified | Declared; no fabricated purchase matching |
| nbrPayments90d | Declared payment aggregate | 90 days; events | Posting/reversal rule unspecified | Declared; complete input tests |
| totalPaymentAmt90d | Declared payment aggregate | 90 days; baseline monetary units | Currency/netting unspecified | Declared; complete input tests |
| overpaymentAmt90d | Declared servicing aggregate | 90 days; baseline monetary units | Balance/allocation/overpayment rule absent | Declared; never inferred from spend/payment difference |
| overpaymentInd90d | Declared servicing code | 90 days; code | No new business/legal rule | Declared; original numeric contract |
| nbrCustReqRefunds90d | Declared servicing-event aggregate | 90 days; requests | Requests are not settled refunds | Declared; complete input tests |
| totalRefundsToCust90d | Declared servicing aggregate | 90 days; baseline monetary units | Currency/settlement rules unspecified | Declared; complete input tests |
| nbrPaymentsCashLike90d | Declared payment-channel aggregate | 90 days; events | Channel codebook not invented | Declared; complete input tests |
| maxRevolveLine | Declared credit/account input | Source snapshot; baseline monetary units | Currency/cutoff unspecified | Declared; complete input tests |
| indOwnsHome | Declared customer code | Snapshot; code | Not ownership-document evidence | Declared; original numeric contract |
| nbrInquiries1y | Declared credit aggregate | One year; events | Source event/cutoff provenance not reconstructed | Declared; complete input tests |
| nbrCollections3y | Declared original named input | **Unresolved: name three years vs description one year** | Preserve original field, no chosen event window | Declared scalar only; unresolved note/tests |
| nbrWebLogins90d | Declared portal aggregate | 90 days; events | Transaction ledger cannot establish logins | Declared; complete input tests |
| nbrPointRed90d | Declared loyalty aggregate | 90 days; events | Transaction ledger cannot establish redemptions | Declared; complete input tests |
| PEP | Declared KYC/profile code | Source snapshot; code | Not verified PEP/sanctions finding; not assumed constant | Declared; original numeric contract |

The user's approved scope permits declared synthetic inputs. This supports new synthetic scored cases without resolving undocumented transaction equations. Missing any mandatory declaration blocks case creation, leaves the evidence fixture intact and reports a fixed blocker; there is no zero-fill or orphan Case. No input/model/threshold/SHAP semantics or saved references are changed.

## Rollback plan frozen before migration

- Add migration `0012_evidence_foundation`, twelve new tables only, plus new evidence-audit guards. No existing row/backfill/rewrite. Application schema expectation and migration verification lists advance together.
- Test fresh head, 0011-to-head with retained synthetic legacy records, no schema drift, empty downgrade to 0011 and upgrade again. Downgrade **refuses if any new source/history or evidence audit exists**; never drops retained evidence to make rollback succeed. Recovery with retained history uses compatible code/forward migration or an approved backup plan.
- Existing alert/case/model/assessment/legacy Evidence data and constraints must survive upgrade/empty downgrade. PostgreSQL enforces immutable update/delete/truncate and typed/source integrity. SQLite remains regression compatibility, not evidence-service acceptance.

## Execution results

**Phase 3.2 local synthetic acceptance: PASS.** Final Linux/PostgreSQL regression passed all 591 tests, with zero failures/skips, and all 14 recovery scenarios passed. Phase 3.3 remains out of scope.

| Acceptance area | Actual evidence |
|---|---|
| Final full Linux/PostgreSQL | 591 passed, 0 failed/skipped; 14 recovery scenarios passed; final suite wall time 486.77 seconds, not a capacity benchmark |
| Final evidence suite | 77 Linux/PostgreSQL passed, 0 failed/skipped; 75 native PostgreSQL passed, 0 failed, 2 Linux ML skips |
| Schema/provenance/integrity | Fresh head, empty 0012 downgrade/upgrade with retained legacy Alert/Case/Evidence, populated-audit downgrade refusal, no metadata drift, source/type FKs and deferred completeness |
| Security/atomicity | Current assignment/role/source scope, grants/revocation/replay revisions, immutable update/delete/truncate/audit, concurrent duplicate admission/case creation, audit rollback and actual owned PG connection termination |
| Synthetic/model linkage | 14 profiles; 27 individual missing-field checks; exact eight-place money and original offsets/unknown time; two newly generated null/zero-income scenarios through the actual pinned worker, verified assessment/SHAP, no case action |
| Full native regression | 551 passed, 0 failed, 39 Linux-only skips; final evidence rerun above covers the additional reconciliation test |
| Final SQLite regression | 364 passed, 0 failed, 227 PostgreSQL/Linux skips; SQLite is not evidence-service acceptance |
| ML boundaries | 178 pinned Linux tests passed; dependency consistency passed |
| Frozen scientific replay | 4,000 RF / 12,000 routes / 4,000 SHAP: zero mismatches. Maximum RF error 0; SHAP reconstruction residual 3.1086244689504383e-15, unchanged tolerances |
| Live migration | 0012, 36 domain tables, zero schema drift; row count/hash preservation across seven business tables; backend/frontend HTTP 200, both workers running |
| Repository boundary | All 25 private baseline hashes and seven unrelated branding/startup file hashes unchanged; source/private-ignore publication check passed |

Verification notes:

- Native Windows' default pytest temp directory was inaccessible. Reruns use unique ignored workspace temp paths; no existing temp or data directory was reset.
- Initial native lease tests mixed Windows time with PostgreSQL scheduling. Test fixtures now use `clock_timestamp()` for due/expiry timestamps. The unchecked import-drain assertion was strengthened; all three previously failed native tests and the native regression rerun passed. Production scheduler code is unchanged.
- A subsequent full Linux run reported two old harness assumptions: immediate concurrent adoption and a child exiting before its intended fault point. Harnesses now wait within fixed bounds, retain exact job/checkpoint/crash-exit assertions, and emit only sanitized exception-type diagnostics. Five repeated runs passed all 15 cases; the final full Linux regression then passed all 591 tests. Job uniqueness, exact checkpoint counts and intended crash exit assertions were preserved.
- Generated evidence fixtures were admitted/scored in disposable test schemas only. No public/legacy case was enriched with invented history; the live migration added empty evidence tables and preserved prior business records.
- Starlette emits the existing httpx deprecation warning. No application/security certification, frontend rerun or production throughput claim is made. Historical Phase 2 benchmark/recovery files are unchanged.


## Internal interfaces and limits

| File / interface | Responsibility |
|---|---|
| `backend/app/schemas/evidence.py` | Frozen extra-forbidden observations; bounded configuration, Decimal, currency and timestamp checks |
| `backend/app/services/synthetic_evidence.py` | Seeded fictional generator, canonical records, manifest, individual feature reconciliation |
| `backend/app/models/evidence.py` / `backend/alembic/versions/0012_evidence_foundation.py` | Twelve additive tables; immutable history, typed/source FKs, deferred release/payload completeness |
| `EvidenceService.register_source(actor_id, scenario_id)` | Owned idempotent registration; active admin only |
| `admit_version(actor_id, source_id, bundle)` | Regeneration, complete typed snapshot, predecessor links and admission audit |
| `create_case(actor_id, release_id)` | Full declared feature support; reuse atomic ingestion; new binding, grant, links and revisions |
| `link_version(actor_id, case_id, release_id)` | Link exact record versions in an admitted snapshot to its bound new case |
| `set_source_access(...)` / `revoke_links(...)` | Current authorization, atomic revision/audit changes, idempotent retries |
| `manifest(actor_id, case_id)` | Authorized value-free provenance/coverage; verify typed rows; audit commits before return |

- PostgreSQL only; internal caller supplies authenticated server identity, never a public actor/role claim. Fresh active role and case assignment checked each operation. Owner/admin admission is deliberate; no shared source workspace or tenant privilege is invented.
- Bounds: 100 sources/owner, 100 releases/source, 200 records/bundle or revoke operation, 1,000 visible versions/manifest. Excess manifest size fails explicitly, never truncates a complete claim. Lock/statement/idle transaction limits: 2/5/15 seconds. These are resource limits, not production capacity claims.
- History is immutable; service grant/membership writes keep revisions and audits atomic. Privileged SQL owners can bypass application controls; deployment SQL roles and independent audit storage remain pending.
- Hashes normalize exact Decimal value and UTC instants; original timezone text remains stored. Unknown time is never imputed to UTC. Money rejects floats, nonfinite, exponent-string, negative, excess magnitude/precision input before SQL.
- Complete coverage describes the declared synthetic window only. Revoked records produce partial membership; revoked grants reveal no source/record metadata. Corrections retain marked predecessors; contradictory KYC observations remain separate.
- Manifests identify the case-creation release and flag later declarations that differ from the immutable case input. Linking a correction never rewrites features; attempting to recreate the bound case from changed inputs conflicts.
- RF inputs are explicit declarations, not recomputed from observation subsets or FX-normalized. No history is invented from existing aggregate alerts. Evidence operations never queue ML; acceptance tests explicitly use the existing Linux queue/worker for new null/zero-income cases.

## Repeatable verification

- `python -B scripts/run_assessment_verification.py --evidence-only`: real Linux/PostgreSQL evidence tests, including two actual worker assessments.
- `python -B scripts/run_assessment_verification.py --full-backend --phase3-report`: backend regression; historical Phase 2 reports unchanged, new recovery measurements in ignored runtime storage.
- `python -B scripts/run_ml_verification.py --check tests`, then `--check scoring`, `--check policy`, `--check shap`: private read-only artifacts; counts/errors only.
- Native PostgreSQL/SQLite use isolated-schema/file fixtures. PostgreSQL is primary; SQLite skips evidence service acceptance. Test schemas are removed after each test; live data and teammate files remain untouched.

## Deferred work

- Phase 3.2 delivered internal foundation only. Case-authorized read APIs and deterministic analytics are subsequently implemented in [Phase 3.3](PHASE3_3_RETRIEVAL_ANALYTICS.md); no corpus/provider capability is implied.
- Real feed derivations, collections-window ambiguity, currency/codebooks, FX rules, verified PEP status, entity resolution, ledger reconciliation and approved retention/deletion remain unresolved. All 27 declared inputs support synthetic fixtures only.
- No external provider, LLM/RAG, binary intake/scanner, automatic case action or UI. Malware scanning remains unavailable. Tenant/RLS, production IAM/SQL roles, independent audit storage and certification are not implemented.
