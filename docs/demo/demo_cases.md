# TrueFlag demo case set (catalog v2)

Eight synthetic cases for a live demo. Each one follows a different path through the system.

**Label:** Synthetic data · Academic demo · Unapproved research · Not production regulatory guidance.

## The story

A fictional investment firm offers a cash management account. Customers get direct deposit, bill pay, transfers to and from P2P wallets, and bank transfers. All IDs start with `SYN-`. There are no real names, firms or account numbers.

The evidence records do not carry merchant or app names. A "P2P wallet" in the story is a counterparty account such as `SYN-ACCOUNT-…`. The story wording lives only in this document.

## Files

| File | What it is |
|---|---|
| `docs/demo/trueflag_demo_cases.csv` | The upload file for Admin › CSV imports (template column order, 8 rows) |
| `docs/demo/evidence/SYN-*.json` | The generated customer, account and transaction records for each case |
| `docs/demo/demo_cases_offline.json` | Offline results: score, routes, drivers and retrieval |
| `backend/app/services/demo_case_catalog.py` | The catalog: inputs and evidence for each case |
| `scripts/build_demo_cases.py` | Rebuilds the CSV and evidence files and reruns the offline checks |
| `scripts/attach_demo_evidence.py` | Binds uploaded cases to their evidence (run once, after the import) |

## Two separate inputs per case

1. **Model inputs.** These are the 27 values in the CSV. The model was trained on credit-card-style account totals, so the inputs are those totals: purchases, merchant credits, payments, cash-like payments, refunds, credit line, logins and KYC. Each case's inputs were chosen to fit its story.
2. **Evidence.** These are the generated customer, account and transaction records that Review evidence shows. They tell the cash-account story.

The model never sees the transactions. The system records this on every case: `feature_values_are_transaction_derived = false`.

## How to run it live

1. Admin uploads `trueflag_demo_cases.csv` in Admin › CSV imports, then validates and imports it.
2. Run the attach script once, as the same admin:

   ```text
   .venv-windows/Scripts/python.exe -B scripts/attach_demo_evidence.py --username windowsadmin
   ```

   For each case, the script first checks that the uploaded inputs exactly equal the catalog's inputs, by fingerprint. Only then does it bind the evidence. Running it again reports `already_linked`.
3. Start assessments with the **Balanced** policy.
4. As supervisor, assign the cases to the analyst.

### Before the AI investigation step (owner decision)

AI investigation (Claude research) runs only for cases named in the owner's research scope file. That scope allows at most 3 cases, and case IDs exist only after the import. The current scope does not cover these new cases, so the AI Investigation tab shows "No authorized provider is available."

To run the 3 video cases live, the owner must issue a new scope for their case IDs. Each run then still needs its own approval. I did not create or change any scope or approval.

### Before the human decision step

A supervisor can approve a resolution only after the analyst has done three things:

- written a note,
- answered every open information request,
- reviewed at least one AI finding.

So a case can be closed only after an AI investigation has produced findings. In the dry run I enabled the **offline simulation**, which is clearly labelled in the UI and makes no provider call, so the findings could be reviewed. It is off in the native runtime. To close cases live, use either the owner-scoped research runs or an owner decision to enable the offline simulation.

## Case table

All scores come from the real frozen model (RF `20261018_183648_RF`). Policy thresholds: Balanced 16.04%, Coverage 16.04%, Efficiency 19.09%. Priority comes from the customer risk rating only: KYC 3 to 6 is High, 0 to 2 is Standard.

"Recommendation" is the Balanced policy. "Retain" means continue analyst review, and "reduction" means review prioritization suggested. No case is ever closed automatically.

| ID | Situation | Score | Priority | Recommendation (Balanced; Efficiency / Coverage) | Top 3 drivers | Evidence | Retrieval query (terms) | Top sections (rank order) | Expected AI outcome |
|---|---|---|---|---|---|---|---|---|---|
| **SYN-01-STRUCTURING** ★ | Cash-like deposits just under USD 10,000 | **47.5%** | Standard (KYC 2) | Retain (Retain / Retain) | Merchant credit amount; Payment amount; Cash-like payments | Complete: 12 transactions (10 cash deposits USD 9,400–9,900, USD 84,000 out) | credit refund return funds payment transfer amount cash currency transaction counterparty customer due diligence risk profile documents records verification retained | §1020.220 CIP; §1020.315 Transactions of exempt persons; §1020.210 AML program | Findings *(confirmed in dry run, offline simulation)* |
| SYN-02-PASSTHROUGH | Money in from one P2P wallet, out to another within 1–2 days | **29.1%** | Standard (KYC 2) | Retain (Retain / Retain) | Payment amount; Overpayment amount; Cash-like payments | Complete: 12 transactions, 6 in/out pairs | payment transfer funds amount overpayment refund return cash currency transaction counterparty customer due diligence … | §1020.315; §1020.220; §1020.320 SAR | Findings (expected) |
| SYN-03-FUNNEL | 40 small credits from 25 senders, then 3 large transfers out | **60.4%** | Standard (KYC 2) | Retain (Retain / Retain) | Merchant credit amount; Total spending; Merchant credits | Complete: 43 transactions, 25 distinct senders | credit refund return funds transaction amount aggregate counterparty transfer customer due diligence … | §1020.220; §1020.315; §1020.210 | Findings (expected) |
| **SYN-04-SAVER** ★ | Ordinary saver: salary, bills, small transfers | **0.1%** | Standard (KYC 1) | Reduction (Reduction / Reduction) | Customer tenure; Annual income; Recorded state (all tiny) | Complete: 15 transactions (biweekly salary, bills) | account opened customer relationship occupation business address location counterparty transfer due diligence … | §1020.210; §1020.320; §1020.100 Definitions | Findings *(confirmed in dry run)*; **closed as a false positive** in the dry run |
| SYN-05-HIGHKYC | KYC 4 customer, normal activity | **0.0%** | **High** (KYC 4) | Reduction (Reduction / **Retain**, High-priority protection) | Customer risk rating; Credit score; Annual income (all tiny) | Complete: 15 transactions | customer identification verification credit occupation business counterparty transfer due diligence … | §1020.315; §1020.210; §1020.320 | Findings (expected) |
| **SYN-06-PARTIAL** ★ | Looks suspicious, but only part of the history is available | **12.7%** | **High** (KYC 3) | Reduction (Reduction / **Retain**) | Payment amount; Cash-like payments; Online logins | **Partial**: 4 events; income not recorded | payment transfer funds amount cash currency transaction online access account counterparty customer due diligence … | §1020.320; §1020.210; §1020.100 | **Abstains** *(confirmed in dry run)* |
| SYN-07-DORMANT | 19-year-old account, quiet for 75 days, then one large credit and a burst of spending | **40.5%** | Standard (KYC 1) | Retain (Retain / Retain) | Merchant credit amount; Cash-like payments; Customer tenure | Complete: 21 transactions, all in the last 14 days | credit refund return funds cash currency transaction account opened customer relationship counterparty transfer due diligence … | §1020.210; §1020.100; §1020.320 | Findings (expected) |
| SYN-08-INCOME | Declared income USD 21,000; about USD 72,000 of card spending in 90 days | **17.8%** | Standard (KYC 2) | Retain (**Reduction** / Retain) | Total spending; Payment amount; Average transaction amount | Complete: 36 transactions | transaction amount aggregate payment transfer funds counterparty customer due diligence … | §1020.220; §1020.315; §1020.320 | Findings (expected) |

★ = best 3 for a 4-minute video:

- **SYN-01:** high score, clear evidence, request information, escalated for compliance review.
- **SYN-04:** low score, closed as a false positive.
- **SYN-06:** the AI abstains and lists what is missing.

These are also the 3 cases an owner research scope can cover, which allows at most 3.

Every query also contains the same 9 terms: "counterparty transfer", "customer due diligence risk profile", "documents records verification retained" and "transaction records". They come from the four evidence items that are always missing (expected activity, documents, sampling metadata, settlement status) and the counterparty calculation. "…" in the table stands for those terms. The full queries are in `demo_cases_offline.json`.

## Dry-run check

I imported the CSV into an isolated database on the native PostgreSQL cluster (`tf_windows_test_demo_…`), with its own API, workers and frontend. I attached the evidence, ran the Balanced assessments and walked the UI with Playwright. Then I dropped the database.

| Check | Result |
|---|---|
| Validation | 8 valid / 0 invalid / 0 warnings; 8 imported, 0 rejected |
| Evidence binding | 8 of 8 attached; second run 8 of 8 already linked |
| Scores and top-3 drivers (stored assessments vs. table) | **8 of 8 match** |
| Balanced recommendations | 8 of 8 match |
| Retrieval (same ranking via Admin › Test retrieval API, per-case queries) | **8 of 8 match** |
| AI outcome (offline simulation) | SYN-01 completed and verified; SYN-04 completed and verified; SYN-06 abstained ("Further evidence needed") |
| Human decisions | SYN-04: no further action recommended (false positive). SYN-01: escalated for compliance review. Both had independent supervisor approval. |
| Cleanup | Both dry-run databases dropped (0 remaining); dry-run folders deleted |

I did not run the AI investigation for SYN-02, -03, -05, -07 or -08. Their outcome is expected from the packet rule: complete coverage with transactions gives findings.

## Targets that could not be reached honestly

| Case | Target | What happened | Why | Suggestion |
|---|---|---|---|---|
| SYN-01 | Strong match on currency transaction rules | §1020.315 (exempt persons, part of the CTR rules) ranks **2nd**. §1020.220 (CIP) ranks 1st. §1020.310–.314 never rank first for any case. | Every case query contains the always-missing due-diligence terms, and §1020.220 matches them strongly. | Keep the case. Say "CTR section in the top 3". |
| SYN-02 | Counterparty-concentration finding | The concentration calculation is shown, but it runs for **every** case that has transactions. It is not specific to this case. | System design | Keep. Point to the 1–2 day in/out pairs in the evidence instead. |
| SYN-03 | Many-counterparty pattern as a driver | The 25 senders are visible in the evidence. The drivers are merchant credits and spending, not distinct merchants. | The model weights the credit totals far above the counterparty count. | Keep. The pattern is shown in Review evidence. |
| SYN-07 | Time-pattern driver | Drivers are merchant credit amount, cash-like payments and customer tenure. | The model has no time-of-activity input. Tenure is the only time-related one. | Keep "dormant then active" as an evidence story with tenure as a driver. |
| SYN-08 | Income-mismatch driver, high score | Score 17.8% (medium). Drivers are spending and payments. | The model does not compare income with spending. A low income never raises the score; tested from USD 8,000 to 300,000. | **Replace** the target with "policy disagreement". This case sits between the thresholds: Balanced and Coverage retain it, Efficiency suggests reduction. |
| All | At least 5 distinct top sections | **4 distinct top sections** (§1020.210, .220, .315, .320). **5 distinct** across all strong matches (+ §1020.100). | Only the top-3 drivers change between cases, and every 3-driver combination tops one of those 4 sections (tested all 2,925). | Not reachable without changing retrieval rules, which I did not touch. |

Sections:
- §1020.100 Definitions
- §1020.210 AML program requirements (includes customer due diligence)
- §1020.220 Customer identification program
- §1020.315 Transactions of exempt persons
- §1020.320 Reports of suspicious transactions

All are in the hash-verified 31 CFR Part 1020 research snapshot (Nov 2, 2026), labelled unapproved research.
