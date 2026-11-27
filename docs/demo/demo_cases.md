# TrueFlag demo case set (catalog v2)

Eight synthetic cases for a live demo. Each one follows a different path through the system.

**Label:** Synthetic data · Academic demo · Unapproved research · Not production regulatory guidance.

## What the system does and does not do with these cases

- **The model gives a risk signal, not a finding.** It scores 27 account totals and says which inputs raised the score. It does not see transactions, and it does not identify structuring, pass-through or funnel activity.
- **The pattern shows up in the evidence and the investigation.** Review evidence shows the transactions. The deterministic evidence-pattern rules (retrieval v5) and the human analyst describe what they show.

## The story

A fictional investment firm offers a cash management account. Customers get direct deposit, bill pay, transfers to and from P2P wallets, and bank transfers. All IDs start with `SYN-`. There are no real names, firms or account numbers.

The evidence records do not carry merchant or app names. A "P2P wallet" in the story is a counterparty account such as `SYN-ACCOUNT-…`.

## Files

| File | What it is |
|---|---|
| `docs/demo/trueflag_demo_cases.csv` | The upload file for Admin › CSV imports (8 rows) |
| `docs/demo/evidence/SYN-*.json` | The generated customer, account and transaction records for each case |
| `docs/demo/demo_cases_offline.json` | Offline results: score, routes, drivers, v4 and v5 queries, rules fired, sections |
| `backend/app/services/demo_case_catalog.py` | The catalog: inputs and evidence for each case |
| `scripts/build_demo_cases.py` | Rebuilds the files and reruns the offline checks |
| `scripts/attach_demo_evidence.py` | Binds uploaded cases to their evidence |
| `scripts/issue_research_scope.py` | Owner tool: scopes AI research to up to 3 named cases (preview unless `--confirm`) |

**Model inputs and evidence are separate.** The model scores the 27 CSV values, which are card-account style totals from its training contract. The evidence records tell the story. The model never sees the transactions, and every case records this: `feature_values_are_transaction_derived = false`.

## Live run: steps before you record

Your native runtime runs a *staged copy* of the code, made the last time you ran `refresh`. Restage it once so it includes this round's changes (catalog, retrieval v5 and the two UI fixes). The database is kept.

```text
.venv-windows/Scripts/python.exe -B scripts/windows_runtime.py stop
.venv-windows/Scripts/python.exe -B scripts/windows_runtime.py refresh
.venv-windows/Scripts/python.exe -B scripts/windows_runtime.py supervise     (in the background)
```

1. **Upload (on camera).** Admin › CSV imports › ⋯ › **Add CSV** → `trueflag_demo_cases.csv` → Upload → Map columns → Validate → Import.
2. **Evidence (off camera, right after the import):**

   ```text
   .venv-windows/Scripts/python.exe -B scripts/attach_demo_evidence.py --username windowsadmin
   ```

   You should see 8 lines with `"status": "attached"`. A second run reports `already_linked`.
3. **Assess:** Start assessments with **Balanced**.
4. **Assign:** as supervisor, assign the cases to the analyst.
5. **Scope AI research to SYN-01, SYN-04 and SYN-06 (your decision; I did not issue it):**

   ```text
   .venv-windows/Scripts/python.exe -B scripts/issue_research_scope.py --cases SYN-01-STRUCTURING SYN-04-SAVER SYN-06-PARTIAL --actors windowsanalyst
   ```

   - Check the preview: case IDs, actor and database.
   - Then repeat the same command with `--confirm`.
   - The old scope file is kept, renamed with a timestamp. The tool prints `new_scope_sha256`.
6. **Rebind the approver policy (owner decision; spending authorization).** The approver file is bound to the scope's hash, so approvals stay disabled until you update it. In `runtime/windows-native/<runtime>/academic-demo/owner-ai-approvers.json`, change only:
   - `scope_sha256`: set it to the `new_scope_sha256` the tool printed;
   - `recorded_at`: set it to now, in ISO format with an offset, for example `2026-11-27T09:00:00-05:00`;
   - `owner_decision_reference`: set it to a new reference for this decision.

   Leave the cap, the reservation, the approver IDs, the single request per approval and the no-retries setting unchanged.
7. **Restart** so the new scope hash is loaded: `windows_runtime.py stop`, then `supervise`.
8. **AI investigation on SYN-04:** the analyst prepares it, the named approver clicks **Approve & Run Once**, and one paid request runs.
   - The analyst then uses **Review AI findings** to accept a finding from this run, writes a note and escalates.
   - The supervisor approves and records the resolution.
   - A resolution needs a reviewed AI finding. Reviewing findings from a live research result is new this round (it was previously limited to the offline simulation), so SYN-04 can be closed after this run.

## Case table

Scores come from the real frozen model (RF `20261018_183648_RF`). Thresholds: Balanced and Coverage 16.04%, Efficiency 19.09%. Priority comes from the customer risk rating only: KYC 3 to 6 is High.

| ID | Situation | Score | Priority | Recommendation: Balanced (Efficiency / Coverage) | Top 3 score drivers | Evidence | Evidence patterns (v5 rules fired) | Top sections, v5 | Expected AI outcome |
|---|---|---|---|---|---|---|---|---|---|
| **SYN-01** ★ | Cash deposits just under the reporting threshold | 47.5% | Standard | Retain (Retain / Retain) | Merchant credit amount; Payment amount; Cash-like payments | Complete: 12 transactions; 10 cash deposits of $9,400–9,900; $84,000 out | Cash below reporting threshold (10 ≥ 3); Activity above declared income ($340,667/yr ≥ $144,000) | **§1020.315** Transactions of exempt persons; §1020.320 SAR; §1020.210 AML program | Findings |
| SYN-02 | Money in and out within 1–2 days via P2P wallets | 29.1% | Standard | Retain (Retain / Retain) | Payment amount; Overpayment amount; Cash-like payments | Complete: 6 in/out pairs | Money out within 48 h (6 ≥ 3); Activity above declared income | **§1020.410** Records to be made and retained (funds transfers); §1020.210; §1020.315 | Findings |
| SYN-03 | Many small incoming transfers, then large outgoing ones | 60.4% | Standard | Retain (Retain / Retain) | Merchant credit amount; Total spending; Merchant credits | Complete: 40 credits from 25 senders; 3 large transfers out | Many senders (25 ≥ 10) | **§1020.315**; §1020.320; §1020.313 Aggregation | Findings |
| **SYN-04** ★ | Ordinary saver | 0.1% | Standard | Reduction (Reduction / Reduction) | Tenure; Income; State (all tiny) | Complete: biweekly salary, bills | None | **§1020.220** Customer identification program; §1020.410; §1020.100 | Findings (planned live run, then closed by people) |
| SYN-05 | High customer risk rating, normal activity | 0.0% | **High** | Reduction (Reduction / **Retain**: High-priority protection) | KYC rating; Credit score; Income (all tiny) | Complete: salary, bills | None | **§1020.220** Customer identification program; §1020.410; §1020.315 | Findings |
| **SYN-06** ★ | Partial history | 12.7% | **High** | Reduction (Reduction / **Retain**) | Payment amount; Cash-like payments; Online logins | **Partial**: 4 events; income not recorded | None (a partial history fires no rule) | **§1020.410**; §1020.315; §1020.100 | **Abstains** |
| SYN-07 | Quiet account that suddenly becomes active | 40.5% | Standard | Retain (Retain / Retain) | Merchant credit amount; Cash-like payments; Tenure | Complete: 21 transactions, all in the last 14 days | Quiet then active (75 days quiet, 21 transactions) | **§1020.210** AML program (ongoing monitoring); §1020.315; §1020.220 | Findings |
| SYN-08 | **Policies disagree** (spending above declared income) | 17.8% | Standard | **Retain** (Efficiency: **Reduction** / Coverage: Retain) | Total spending; Payment amount; Average transaction | Complete: about $72,000 card spending; income $21,000 | Activity above declared income ($269,674/yr ≥ $63,000) | **§1020.210**; §1020.315; §1020.320 | Findings |

★ = the 3 cases you'll scope and show:
- **SYN-01:** high risk signal; the evidence and rules point to currency transaction reporting; escalated.
- **SYN-04:** low signal; real approved AI run; closed by people as a false positive.
- **SYN-06:** partial history; the AI abstains and lists what is missing.

SYN-08 sits between the thresholds (16.04% < 17.8% < 19.09%). Balanced and Coverage keep it for review, and Efficiency suggests review reduction. The same case gets a different recommendation depending on the policy the firm chose.

## Retrieval v5: before and after

v1–v4 records keep their own rule and re-run unchanged. New investigations use v5.

**What v5 changes:**

1. **Inputs present in every case are dropped.** These are the four always-missing evidence codes (expected activity, documents, sampling metadata, settlement status) and the counterparty-concentration calculation, which runs for every case with transactions. The record lists them under `dropped_inputs`.
2. **Evidence-pattern rules add case-specific words.** The rules run on the case's own transactions, with no AI. Each rule adds 4 words, and each word counts 3 times as much as a driver word.
3. **New ranking.** Sections are ordered by the weighted query words they contain. `ts_rank_cd` breaks ties, and scores are compared as numbers.
   - The v1–v4 ranking sorted the score *as text*, so a score of 10 or more ranked below single-digit scores. That ranking is kept only so stored records re-run identically.
   - The 25%-of-top threshold is unchanged. Because the v5 score counts matched words, it keeps more single-word matches than before.

| Rule | Fires when | Words added (weight 3) |
|---|---|---|
| Cash below reporting threshold | ≥ 3 cash-like deposits of $9,000–9,999.99 | structured, currency, reports, aggregation |
| Money out within 48 h | ≥ 3 incoming amounts each followed within 48 h by an outgoing 90–100% of it | transfer, transmittal, originator, beneficiary |
| Many senders | Incoming from ≥ 10 distinct counterparties | multiple, sources, aggregate, aggregation |
| Activity above declared income | Outgoing in the window, annualized ≥ 3 × declared income (never inferred if income is missing) | diligence, beneficial, ownership, profile |
| Quiet then active | No activity for the first ≥ 60 days of the window, then ≥ 10 transactions | ongoing, monitoring, update, risk |

| Case | Before (v4 query) → top 3 | After (v5 query; ×3 = pattern word) → top 3 |
|---|---|---|
| SYN-01 | credit refund return funds payment transfer amount cash currency transaction counterparty customer due diligence risk profile documents records verification retained → §1020.220, .315, .210 | currency×3 structured×3 reports×3 aggregation×3 diligence×3 beneficial×3 ownership×3 profile×3 credit refund return funds payment transfer amount cash transaction → **§1020.315**, .320, .210 |
| SYN-02 | payment transfer funds amount overpayment refund return cash currency transaction counterparty customer due diligence risk profile documents records verification retained → §1020.315, .220, .320 | transfer×3 transmittal×3 originator×3 beneficiary×3 diligence×3 beneficial×3 ownership×3 profile×3 payment funds amount overpayment refund return cash currency transaction → **§1020.410**, .210, .315 |
| SYN-03 | credit refund return funds transaction amount aggregate counterparty transfer customer due diligence risk profile documents records verification retained → §1020.220, .315, .210 | aggregate×3 multiple×3 sources×3 aggregation×3 credit refund return funds transaction amount → **§1020.315**, .320, .313 |
| SYN-04 | account opened customer relationship occupation business address location counterparty transfer due diligence risk profile documents records verification retained transaction → §1020.210, .320, .100 | account opened customer relationship occupation business address location → **§1020.220**, .410, .100 |
| SYN-05 | customer identification verification credit occupation business counterparty transfer due diligence risk profile documents records retained transaction → §1020.315, .210, .320 | customer identification verification credit occupation business → **§1020.220**, .410, .315 |
| SYN-06 | payment transfer funds amount cash currency transaction online access account counterparty customer due diligence risk profile documents records verification retained → §1020.320, .210, .100 | payment transfer funds amount cash currency transaction online access account → **§1020.410**, .315, .100 |
| SYN-07 | credit refund return funds cash currency transaction account opened customer relationship counterparty transfer due diligence risk profile documents records verification retained → §1020.210, .100, .320 | ongoing×3 monitoring×3 update×3 risk×3 credit refund return funds cash currency transaction account opened customer relationship → **§1020.210**, .315, .220 |
| SYN-08 | transaction amount aggregate payment transfer funds counterparty customer due diligence risk profile documents records verification retained → §1020.220, .315, .320 | diligence×3 beneficial×3 ownership×3 profile×3 transaction amount aggregate payment transfer funds → **§1020.210**, .315, .320 |

**Distinct top sections:**
- v4: 4 (§1020.210, .220, .315, .320).
- **v5: 4 (§1020.210, .220, .315, .410)**, with 7 distinct sections across all top-3 results (v4 had 5).
- SYN-01 now ranks §1020.315 first. That is the long currency-transaction-report section (exempt persons). It leads §1020.320 only narrowly: 15.87 against 14.80.

§1020.310–.314 are one-line cross-references ("Refer to § 1010.314…"). They contain too few words to rank first by word coverage, and only length normalization would lift them, which put them first for unrelated cases too. §1020.313 (Aggregation) does appear in SYN-03's top 3.

## Dry-run check

The dry run used the same staged copy as your native runtime: candidate migrations 0020–0023 applied, schema 0023, research tables present. It ran against a throwaway database on the native cluster, which has since been dropped. There was no simulation and no paid request.

| Check | Result |
|---|---|
| Validation and import | 8 valid / 0 invalid / 0 warnings; 8 imported. The session bar shows **"8 cases"** right after the import (fixed). |
| Evidence binding | 8 of 8 attached |
| Scores, top-3 drivers and Balanced recommendations | 8 of 8 match the table |
| AI Investigation tab without a scope | "No authorized provider is available", as expected |
| Notes, information request, escalations | Recorded. Both escalations appear in the supervisor's Review Queue. |
| Case summary after a resolution | Shows **"Decision: Escalated for compliance review"** (fixed). I verified this separately with the offline simulation; those screens are not in these docs. |
| Retrieval v5 | Verified offline from the same records with the system's own functions, and by the retrieval tests (`test_research_retrieval.py`, `test_research_retrieval_v5.py`). In the app, per-case v5 retrieval runs only for scoped cases. Test retrieval uses the same v5 ranking, with every word weighted 1. |
| Cleanup | Database dropped (0 remaining); staged copy and logs deleted |

## Targets still not reachable honestly

| Case | Target | Status |
|---|---|---|
| SYN-01 | A currency transaction reporting section first | **Reached:** §1020.315 is first, by a narrow margin. |
| SYN-07 | A time-pattern *score driver* | The model has no time inputs. The pattern is visible in the evidence and fires the "quiet then active" rule. |
| SYN-08 | An income-mismatch *score driver* | The model does not compare income with spending. Re-targeted as the "policies disagree" case. The mismatch appears in the evidence and fires the income rule. |
| All | At least 5 distinct top sections | 4 with v5. Reaching 5 would need either tuning words to the corpus or length normalization; both make the retrieval less honest. |
