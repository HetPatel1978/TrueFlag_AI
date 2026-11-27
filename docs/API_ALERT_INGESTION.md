# Synthetic AML alert ingestion — Week 1

## Endpoint and authorization

`POST /api/v1/alerts` accepts one synthetic alert. A valid bearer token and the **current database-backed admin role** are required on every request, including retries. Analysts cannot ingest. Role/actor fields supplied in the request are rejected. This is a single-workspace API; no tenant isolation is claimed.

| Header | Requirement |
|---|---|
| Authorization | `Bearer <access_token>` from the existing JSON `/api/v1/auth/token` endpoint |
| Content-Type | `application/json` |
| Idempotency-Key | Required, 16–128 characters, ASCII letters/digits or `_.:-`; normally a UUID |

Raw idempotency keys are not stored or returned; the receipt table stores SHA-256 hashes. No client-provided creator identity is trusted.

## Request contract

Four required envelope fields: `source_id`, `data_classification`, `feature_contract_version`, `features`. Extra envelope/predictor fields are rejected.

- `source_id`: stable upstream identity, 1–128 characters; initial character alphanumeric, remaining characters alphanumeric or `_.:-`. Unique within this workspace. Different source identifiers remain separate even when their features match.
- `data_classification`: exactly `synthetic`. This is a caller declaration, not proof that a submitted record is synthetic; approved data access remains an operational requirement.
- `feature_contract_version`: exactly `datarobot_provisional_v1`, identifying the retained 27-predictor contract.
- `features`: exactly the ordered field set below, matching the immutable baseline contract (SHA-256 `97ec1a8c39bb368621609ea66d1a652179dee8a1c910bc7c14c1b3ff81f72747`).
- Numeric predictors require finite JSON numbers, not strings or booleans. Supported KYC values are whole-valued 0–6 (including `3.0`); unsupported values are rejected rather than assigned Standard priority.
- `income` is required but nullable: JSON `null` denotes missing, distinct from observed zero. The raw CSV token `\N` is not a JSON-number representation and must be mapped explicitly by an upstream CSV adapter. No imputation is applied.
- `state` requires a nonblank string, maximum 128 characters; no case normalization or new category whitelist is applied. Numeric values are not scaled, clipped, rounded or constrained using invented accounting rules.
- SAR, notes, source/split/review metadata and derived priority never enter `features`. No optional default fills a missing predictor.

This wholly fabricated example is not copied from a case:

```json
{
  "source_id": "synthetic-demo-001",
  "data_classification": "synthetic",
  "feature_contract_version": "datarobot_provisional_v1",
  "features": {
    "kycRiskScore": 3,
    "income": null,
    "tenureMonths": 12,
    "creditScore": 650,
    "state": "ZZ",
    "nbrPurchases90d": 10,
    "avgTxnSize90d": 25,
    "totalSpend90d": 250,
    "nbrDistinctMerch90d": 4,
    "nbrMerchCredits90d": 1,
    "nbrMerchCreditsRndDollarAmt90d": 0,
    "totalMerchCred90d": 20,
    "nbrMerchCreditsWoOffsettingPurch": 0,
    "nbrPayments90d": 3,
    "totalPaymentAmt90d": 300,
    "overpaymentAmt90d": 50,
    "overpaymentInd90d": 1,
    "nbrCustReqRefunds90d": 1,
    "totalRefundsToCust90d": 20,
    "nbrPaymentsCashLike90d": 0,
    "maxRevolveLine": 5000,
    "indOwnsHome": 0,
    "nbrInquiries1y": 1,
    "nbrCollections3y": 0,
    "nbrWebLogins90d": 5,
    "nbrPointRed90d": 0,
    "PEP": 0
  }
}
```

Save an approved synthetic example beneath ignored `assets/local/` and invoke in PowerShell:

```powershell
curl.exe -X POST http://127.0.0.1:8010/api/v1/alerts `
  -H "Authorization: Bearer $env:TRUEFLAG_ACCESS_TOKEN" `
  -H "Idempotency-Key: synthetic-demo-request-0001" `
  -H "Content-Type: application/json" `
  --data-binary "@assets/local/synthetic-alert.json"
```

## Responses and idempotency

| Situation | HTTP | Business effect |
|---|---|---|
| New key and new source | 201 | One alert, one unassigned open case, one `alert.ingested` audit event, one durable receipt |
| Same key and equivalent content | 200 | Original creation receipt; no repeated business writes |
| New key, same source and equivalent content | 200 | Same alert/case; another key receipt; no duplicate creation audit |
| Same key, changed request; or same source, changed input | 409 | No new alert/case/receipt/audit |
| Missing/invalid/inactive token | 401 | No ingestion writes |
| Non-admin role | 403 | No ingestion writes |
| Missing key, invalid envelope/predictors | 422 | No ingestion writes; errors omit submitted input values |
| Database/state failure | 503 | No success acknowledgment; retry the same request/key |

Creation receipts contain `alert_id`, `case_id`, `case_status: open`, `scoring_status: not_requested`, `routing_status: not_evaluated`, and `feature_contract_version`. **These describe ingestion, not current case state.** Retrying a previously closed case does not reopen it. Receipt responses do not expose predictors or raw idempotency keys.

Object ordering and equivalent numerical spelling (`1`/`1.0`, signed zero) do not create conflicts. Fingerprinting uses exact numeric ratios without changing stored inputs or collapsing distinct large integers. Missing and zero income remain different. The feature hash includes the contract; the request hash also includes source identity and classification. These transport hashes are not claimed to equal historical CSV/SHAP source-lexeme hashes.

## Transactions and concurrency

- A single transaction includes the alert, linked case, creation audit and receipt. No success response is returned before commit. Failed statements/commit roll back the entire uncommitted unit; the same key remains retryable.
- Database unique constraints arbitrate concurrent writers across processes. A bounded retry resolves expected source/key uniqueness races; other database errors remain failures.
- A network failure around commit can leave the client unsure whether the transaction committed. A retry with the same key resolves this ambiguity using the durable receipt; a `503` alone is not proof that the server committed nothing.
- Authentication uses the request's session; the service does not nest a new outer transaction after its authentication read. Existing inconsistent alerts without linked cases are not silently repaired.
- No prediction, policy routing, priority derivation, automatic dismissal, case closure, or ML integration occurs. Model score and decision tables remain untouched.

## Verification

- Unit/HTTP tests use newly migrated SQLite fixtures with foreign keys enabled.
- Set `TRUEFLAG_TEST_POSTGRES_URL` to an approved local test connection to rerun all tests against PostgreSQL. Each test creates a uniquely named schema and drops only that schema in teardown; no existing project tables are reset.
- Real PostgreSQL tests force concurrent requests to reach insertion together and inject a database-trigger failure after earlier writes, checking rollback and subsequent successful retry.
- Optional local-only tests compare the exact staged contract and validate the 27-field representation of all 10,000 retained synthetic rows without scoring, storing, or printing them. CI does not require private files.

## CSV onboarding boundary

The existing single-alert ingestion contract remains unchanged. Admin-only private CSV staging and versioned full-file mapping/validation preview are separate APIs; see [CSV staging](PHASE2_10_1_CSV_STAGING.md) and [preview API](PHASE2_10_2_VALIDATION_PREVIEW.md). Preview never calls ingestion or creates canonical records. [Phase 2.10.3 durable import](PHASE2_10_3_DURABLE_IMPORT.md) adds explicit approval and protected progress/row APIs, reusing the same transactional ingestion statements. The single-alert wrapper still commits one request; the import worker owns each chunk transaction. No ML dispatch is triggered. No transaction monitoring or enterprise source connector is claimed.
