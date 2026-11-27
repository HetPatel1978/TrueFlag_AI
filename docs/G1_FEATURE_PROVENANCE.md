# G1 feature provenance

## Boundary

- Frozen input contract: **27 predictors**, `datarobot_provisional_v1`. No feature formula, RF artifact, preprocessing, policy threshold or SHAP behavior was changed.
- **All 27 model inputs remain explicit synthetic declarations.** The banking observations do not reconstruct the original dataset's historical predictors. Similar field names or coinciding counts are not derivation evidence.
- A connected case can have verifiable transaction evidence and an RF score without claiming that its predictors were computed from that evidence. Treat these as separate signals with explicit reconciliation limitations.
- Several scenarios intentionally share the same declared RF inputs and therefore the same RF score despite different transaction patterns. Behavioral differences appear in the independently verified analytics; this integration does not make the frozen RF consume the new transaction histories or implement multi-signal risk fusion.

| Origin | G1 treatment |
|---|---|
| Declared synthetic predictors | Preserved exactly in immutable alert features, including null versus zero |
| Observed source attributes | Customer observations, account currency/open date, declared-holder relationships, transaction direction/amount/currency/offset time; versioned source records |
| Reproducibly derived facts | Existing Decimal analytics over authorized source records, explicit currency/window/reversal treatment; independently checked |
| Unavailable information | Expected customer activity, settlement status, unsupported KYC/credit/servicing details and unknown timestamps; no inference or zero-fill |

## Machine-readable manifests

- `app.services.connected_scenarios.feature_origins(bundle)` emits a manifest for each scenario; `preview(seed)` includes it before any database mutation.
- `scripts/setup_connected_scenarios.py` persists the applied manifest in the protected per-scenario receipt. The immutable source version already holds declarations, hashes, configuration, record hashes and reconciliation.
- Fields: catalog/generator/feature-contract versions, scenario identity, source revision/digest, approved dictionary SHA-256, all 27 declarations and origin flags, source-record hashes, dictionary definitions/units/windows/references/uncertainties, and scenario-specific units.
- The actual approved private `assets/local/baseline/contracts/data_dictionary.csv` must match SHA-256 `6d262b3b8cce169fd3898019d46bb0dc542a3054f51ff3f2c80d5cf3b14de442`. Missing or modified metadata fails safely. The dictionary exists; it is not an implemented feature derivation registry.
- Only allowlisted metadata columns are read into the manifest. Observed example values, statistical distributions and private scientific records are not copied into Git.
- Definition/status/source/unit/window fields come from that dictionary; they are not rewritten into an invented business definition. `scenario_unit` is a fictional fixture assumption and cannot override the dictionary's documented uncertainty.

## Important semantics

| Item | Required interpretation |
|---|---|
| `income=null` | Declared unavailable income; remains null through ingestion and fitted preprocessing |
| `income=0` | Explicit observed zero in the synthetic customer declaration; distinct from null |
| `kycRiskScore` | Explicit customer/scenario declaration, not inferred from transfers; existing High mapping remains unchanged |
| Transaction-window predictors | Synthetic declarations, not aggregates of the supplied feed; no claim that spend/payment counters reconcile to this feed |
| Credit/portal/servicing inputs | Separate scenario declarations; no invented credit-bureau or portal event history |
| Currency/codebooks/collections window | Original uncertainty remains recorded; no unsupported original USD currency, codebook or collections-window claim |
| Source revision | Current evidence may be v2 while the immutable alert and its assessment remain bound to v1 inputs |

## Exact linkage

1. Catalog key/seed determine the stable scenario UUID; actor/source/record keys determine source-scoped identity UUIDs.
2. `EvidenceService.admit_version()` freezes canonical source/configuration/declaration/record digests and independently reconstructs persisted typed rows.
3. `EvidenceService.create_case()` uses existing atomic alert ingestion and creates `EvidenceCaseBinding(case_id, source_id, source_version_id, input_sha256)`; it does not attach invented history to CSV/legacy cases.
4. The assessment job binds actor, case version, immutable input hash, deterministic run ID and selected policy. Existing services persist actual model identity, policy trace and verified SHAP contributions.
5. Latest authorized evidence selection is governed by source/access/evidence revisions. Investigation manifests independently bind that selection and the selected assessment; model outputs remain model signals.

## Verification and limitations

- Tests check source-scoped reference membership, typed-row reconstruction, exact Decimal financial results, null/zero distinction, original-profile manifest parity, actual model processing and invalid dictionary rejection.
- Multi-currency packet tests independently reject forged later-currency input references and tampered totals before accepting the original packet.
- Scenario expectations are deterministic fixture oracles, **not independent human AML relevance labels**. No real-world detection performance, criminal inference or regulator approval is established.
- A future derivation registry requires explicit reviewed source fields, inclusion rules, units, time windows, missingness policy and reconciliation tests. G1 does not supply or silently approve that registry.
