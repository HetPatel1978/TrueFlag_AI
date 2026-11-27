# TrueFlag system walkthrough

A step-by-step tour of the whole system using the eight `SYN-` demo cases (see [demo_cases.md](demo_cases.md)).

All screenshots are in `screens/`. They come from an isolated dry run on the native Windows stack. That dry run used a throwaway database, which has been dropped. The screens show synthetic data only, and no offline simulation was used.

**Roles:**
- **Admin** (windowsadmin): imports data and runs administration.
- **Analyst** (windowsanalyst): investigates assigned cases.
- **Supervisor** (windowssupervisor): assigns cases and makes independent decisions.
- **Owner / spending approver:** approves each paid AI request. This is a named person in the owner's approval file.

---

## 0. Deployment context (how a firm would adopt TrueFlag)

**This section describes the deployment process. It is not part of the demo.**

1. **Train and validate the model on the firm's own history.**
   - A firm would export past alerts and their outcomes: alerts that became SAR filings, and alerts that were closed.
   - It would train and validate the risk model on that history before using it.
   - *Why:* the model only means something on data like the data it learned from.
2. **Pick a review policy.**
   - Each policy is a threshold on the model score:
     - **Efficiency:** 19.09%. Fewer cases kept for review.
     - **Balanced:** 16.04%.
     - **Coverage:** 16.04%, and it also always keeps High-priority customers (KYC 3–6).
   - *Why:* the firm decides how much review work it trades for how much risk it catches.
3. **Load the regulation corpus.**
   - The demo uses a snapshot of 31 CFR Part 1020 (bank AML rules) from eCFR, dated Nov 2, 2026. It has 24 sections.
   - Its raw and extracted text hashes are checked every time it is used.
   - *Why:* the AI may only cite text the firm loaded and verified.
4. **Set up roles.** Analyst, supervisor, admin, and a named spending approver for AI requests.
   - *Why:* no single person can both flag and close a case, or both request and approve AI spending.

**What the demo model was actually trained on.** This is the truthful version.

**Data:**
- 10,000 synthetic AML alert records in a credit-card-account format (cleaned as `datarobot_cleaned_v1`).
- The outcome label is a synthetic "SAR" proxy, positive for 10.26% of rows.
- **No real firm's data was used.** The rights statement on these files is "no source license supplied; local reuse only."

**Model:**
- A random forest (`20261018_183648_RF`, 300 trees) over 27 inputs.
- It was selected with five-fold cross-validation on 6,000 development rows, then refit on those rows.

**Results on the 2,000 reserved evaluation rows.** I recomputed these from the saved predictions; nothing was retrained.

| Measure | Value |
|---|---|
| ROC-AUC | 0.945 |
| Average precision | 0.590 (positive rate 10.25%) |
| Balanced policy | keeps 98.1% of SAR rows for review; suggests review reduction for 73.9% of alerts |
| Efficiency policy | keeps 92.7%; suggests reduction for 75.6% |
| Coverage policy | keeps 98.1% and every High-priority SAR row; suggests reduction for 63.0% |

**Limits:**
- The project's own audit calls these rows an "exposed-population reproduction", not an untouched holdout.
- There is no independent time-split or real-bank validation.

---

## 1. New alerts arrive (Admin › CSV imports)

| # | Who | Page | Do this | Screen shows | Why |
|---|---|---|---|---|---|
| 1.1 | Admin | Sign in | Enter username and password, click **Sign in** | [01](screens/01-sign-in.png) | Every action is tied to a named user. |
| 1.2 | Admin | Administration › CSV Imports | Click **Administration** in the sidebar | The upload session bar and imports page ([02](screens/02-csv-imports.png)) | Imports are kept in upload sessions, so each batch stays separate. |
| 1.3 | Admin | Same | Click **⋯** (Session options), then **Add CSV**. Choose `docs/demo/trueflag_demo_cases.csv`. | The upload step ([03](screens/03-upload-csv.png)) | Only UTF-8 CSV within the size limits is accepted. |
| 1.4 | Admin | Map columns | Click **Upload CSV**. Check that each column maps to its field. Tick **Values use the required source units**. | The column mapping ([04](screens/04-column-mapping.png)) | The model needs exactly its 27 inputs in its own units. Nothing is converted or guessed. |
| 1.5 | Admin | Validate | Click **Validate mapped file** | 8 total, 8 valid, 0 invalid, 0 warnings ([05](screens/05-validation-preview.png)) | See the list below. |
| 1.6 | Admin | Import | Tick **I approve importing only the 8 valid records**, then click **Import valid records** | 8 imported · 0 rejected · 0 remaining ([06](screens/06-import-finished.png)) | Import is a separate, explicit approval. It does not start any scoring. |
| 1.7 | Admin | Command line | Run `scripts/attach_demo_evidence.py --username windowsadmin` | `attached` for all 8 | Binds each case to its generated evidence, after checking that the inputs match exactly. In production, evidence comes from the firm's core systems via connectors; in this demo, a script loads synthetic records. |

Validation (step 1.5) shows the problems before anything is imported. Each check protects against something specific:

- **Exact columns and contract version:** inputs the model was not trained on.
- **Strict numbers:** text or rounded values passed as numbers.
- **KYC must be 0–6:** an unsupported risk rating.
- **Empty income stays "missing":** a missing income being treated as zero income.
- **`synthetic` classification only:** real data getting into the demo.
- **Duplicate source IDs:** the same alert being imported twice.

## 2. Assessment (Admin)

| # | Who | Page | Do this | Screen shows | Why |
|---|---|---|---|---|---|
| 2.1 | Admin | Imports › Assess imported alerts | Choose **Balanced** in **Review policy**, then click **Start assessments** | [07](screens/07-choose-policy.png) | The policy is chosen on purpose for each batch. |
| 2.2 | Admin | Assessment progress | Wait | Completed 8 · In progress 0 · Waiting 0 · Needs review 0 ([08](screens/08-assessment-progress.png)) | Scoring runs in a separate worker. It retries safely and never runs twice for the same request. |
| 2.3 | Admin | Batch results | Read the table | Score and recommendation for each case ([09](screens/09-batch-results.png)) | See below. |
| 2.4 | Admin | Same | Click **View explanation** | The factors that raised or lowered the score ([10](screens/10-batch-explanation.png)) | Every score comes with its reasons. |

The batch results in step 2.3 show **Continue analyst review** for SYN-01, -02, -03, -07 and -08, and **Review prioritization suggested** for SYN-04, -05 and -06. Scores are signals, not proof. The banner says so, and no case is closed automatically.

## 3. Analyst morning

| # | Who | Page | Do this | Screen shows | Why |
|---|---|---|---|---|---|
| 3.1 | Supervisor | Case › **Assign** | Choose **windowsanalyst**, click **Confirm assignment** (once per case) | [11](screens/11-assign-investigator.png) | Analysts see only cases assigned to them. |
| 3.2 | Analyst | Overview | Open **Overview** | Open 8 · Assigned to me 8, and the **Needs attention** list ([12](screens/12-overview.png)) | See below. |
| 3.3 | Analyst | Cases | Open **Cases** | All 8 cases with priority, score, recommendation and assignee ([13](screens/13-cases-list.png)) | See below. |

**How Needs attention is ordered (step 3.2).** It lists the top 5 open cases. High priority comes first, then the highest model score. In the demo that order is SYN-06, SYN-05, SYN-03, SYN-01, SYN-07.

High priority comes from the customer risk rating (KYC 3–6), not from the score. So SYN-05 (score 0.0%) appears near the top: a high-risk customer is shown even when the activity looks normal.

**How the Cases list is ordered (step 3.3).** The newest update comes first. Filters change the queue, for example My Assigned or Unassigned.

## 4. Case review: SYN-01, cash deposits just under the reporting threshold

| # | Who | Page | Do this | Screen shows | Why |
|---|---|---|---|---|---|
| 4.1 | Analyst | Case › **Assess Alert** | Open case b795ddf6 | Score 47.5%, Continue analyst review, ✓ Verified, and Key Risk Drivers ([14](screens/14-assess-syn01.png)) | See below. |
| 4.2 | Analyst | Case › **Review Evidence** | Click **Review Evidence** | See below ([15](screens/15-evidence-syn01.png)) | The analyst checks the score against the actual records. |
| 4.3 | Analyst | Compare | Open **SYN-05** › Assess Alert | Priority **High**, score **0.0%** ([17](screens/17-assess-syn05.png)) | Priority and score answer different questions. Coverage keeps this case for review anyway. |
| 4.4 | Analyst | Compare | Open **SYN-06** › Review Evidence | **Partial coverage**, 4 events, "Missing: Annual income, Expected activity" ([18](screens/18-evidence-syn06.png)) | Missing data is shown as missing, never as zero. |
| 4.5 | Analyst | Compare | Evidence for SYN-02, SYN-07, SYN-08 | In/out pairs within 1–2 days ([19](screens/19-evidence-syn02.png)); 14 days of sudden activity ([20](screens/20-evidence-syn07.png)); spending far above income ([21](screens/21-evidence-syn08.png)) | The model gives only a risk signal. The pattern is visible in the evidence, which the analyst reads. |

What step 4.1 shows:

- **Key Risk Drivers:** merchant credit amount (+27.2 points), payment amount (+11.1), cash-like payments (+3.7). **Show all 27** lists every input.
- **Verified** means the stored model, policy and explanation passed their checks.
- **Version:** if the case is assessed again, a version picker appears. Old versions are never overwritten.

What step 4.2 shows:

- The customer: income $48,000, risk rating 2, "Missing: Expected activity".
- 2 accounts.
- Activity for Oct 3 – Dec 31, 2025: 12 transactions. In $96,650, out $84,000.
- Ten cash-like deposits of $9,400–$9,900, and transfers out of $38,000 and $46,000.

Gaps are listed as such. For example, expected activity is not on file.

## 5. AI investigation

The AI step is shown live on **SYN-04**. It runs one real, approved request. There is no simulation anywhere in this walkthrough.

**Before the live run (owner decisions, done off camera; see [demo_cases.md](demo_cases.md), steps 5–7):**
- The owner scopes AI research to SYN-01, SYN-04 and SYN-06. The scope allows at most 3 cases, named by case ID.
- The owner rebinds the approver policy to the new scope.
- The runtime is restarted.

Before that, the tab says **"No authorized provider is available"** and the button is disabled ([16](screens/16-ai-investigation-syn01.png)). That is the control working.

**The live flow (recorded live; not in these screenshots):**

1. **Analyst prepares the request.** Open SYN-04 › **AI Investigation** › **Generate investigation**.
   - The system checks the evidence packet.
   - It retrieves regulation sections for this case (retrieval v5, see step 6).
   - It builds the *exact* request and shows it under **AI Request Review**.
2. **The review panel shows:**
   - case, model, data scope ("Synthetic data only"), request limits and spending reservation;
   - the financial evidence, regulatory sources, missing evidence and limitations that will be sent.
3. **The owner approves.** Only the named approver can click **Approve & Run Once**. Anyone else sees "Pending Owner Approval".
   - If the evidence changed after the request was prepared, nothing is sent.
   - The spending cap is shown in Provider usage.
4. **One run, no retries.** The request is sent once. A failure is recorded and is not repeated automatically.
5. **The result.** Every claim is checked against the evidence and the cited text before it is shown.
   - Conclusion and findings, with transaction chips.
   - **Regulatory basis:** only the sections the AI cited ("Used in: …"). Others sit under "Also retrieved (n)".
   - **How sources were retrieved:** the case inputs and query words, the evidence patterns found (with each rule's threshold), and the inputs left out because every case has them.
   - The badge **Unapproved research · Not production regulatory guidance**.
6. **Traceability.** The record keeps the request and response hashes, the retrieved sections, excerpt hashes, the rules that fired, the approval and the actor. Stored results are re-verified when read.

**Expected outcomes for the scoped cases:**
- SYN-04 and SYN-01 have complete evidence, so findings are expected.
- SYN-06 has only a partial history, so the AI is expected to abstain and list what is missing.

These follow from the deterministic evidence packet rule. They are expectations, not results: no paid request was made for these docs.

## 6. How each case gets its own regulations (retrieval v5)

The query for a case comes from three things:

1. **The case's top 3 score drivers,** each mapped through a fixed table to plain regulatory words.
2. **Evidence-pattern rules** that run on the case's own transactions, with no AI. Each rule adds 4 words, each counting 3 times:
   - cash deposits of $9,000–9,999.99 (3 or more);
   - money out within 48 hours of money in (3 or more pairs);
   - incoming money from 10 or more senders;
   - outgoing activity at least 3× the declared annual income;
   - a quiet account (60+ days) that then has 10 or more transactions.
3. **Case-specific gaps or conflicts only.** The four evidence items missing in every case are left out, because they added the same words to every query.

Sections are ranked by how many weighted query words they contain, then by text-match score. Up to 3 are kept.

| # | Who | Page | Do this | Screen shows | Why |
|---|---|---|---|---|---|
| 6.1 | Admin | Administration › Provider Usage › **Test retrieval** | Type `structured currency reports aggregation` (the words SYN-01's cash rule adds), click **Test retrieval** | 1. §1020.315 Transactions of exempt persons, 2. §1020.320, 3. §1020.313 Aggregation ([43](screens/43-test-retrieval-syn01.png)) | Each rule's words lead to the rules about that behavior. No AI call is made. |
| 6.2 | Admin | Same | Type `transfer transmittal originator beneficiary` (SYN-02's in-and-out rule) | 1. §1020.410 Records to be made and retained (funds transfers) ([44](screens/44-test-retrieval-syn02.png)) | A different pattern leads to different rules. |

**Per-case results:**
- SYN-01 ranks §1020.315 (currency transaction reporting) first.
- SYN-02 ranks §1020.410 (funds-transfer records) first.
- SYN-07 and SYN-08 rank §1020.210 (AML program, including due diligence) first.
- SYN-04 and SYN-05 rank §1020.220 (customer identification) first.

Across the 8 cases there are 4 different top sections and 7 different sections overall. The full before/after queries are in [demo_cases.md](demo_cases.md).

## 7. Human decision

| # | Who | Page | Do this | Screen shows | Why |
|---|---|---|---|---|---|
| 7.1 | Analyst | SYN-04 › **Human Decision** | Action **Write note**. Type the note, click **Submit investigation note** | [23](screens/23-note-syn04.png) | Notes cannot be edited; a correction is added as a new note. |
| 7.2 | Analyst | SYN-04 | Action **Escalate to supervisor**. Rationale: "Recommend closing as a false positive…". Click **Request supervisor review** | A confirmation step: **Confirm and record decision** ([32](screens/32-confirm-decision.png)). After confirming: 1 pending supervisor review ([33](screens/33-escalated-syn04.png)) | An analyst cannot close a case alone. Every decision is confirmed first. |
| 7.3 | Analyst | SYN-01 | Action **Request information** (Customer documentation, assigned analyst) | [25](screens/25-request-info-syn01.png) | Missing evidence becomes a tracked, internal request. No email is sent. |
| 7.4 | Analyst | SYN-01 | Action **Escalate to supervisor**: "Recommend compliance review", then **Confirm** | [35](screens/35-escalated-syn01.png) | The analyst proposes; the supervisor decides. |
| 7.5 | Supervisor | **Review Queue** | Open the queue | Both escalations and how long they have waited ([36](screens/36-review-queue.png)) | Escalations cannot get lost. |
| 7.6 | Analyst | SYN-04 (live, after the AI run) | Action **Review AI findings** › **Load my latest verified AI findings** › pick a finding › **Accept for consideration**, then **Confirm** | (recorded live) The panel says **Live AI result (verified)** | A resolution needs at least one reviewed AI finding. The review is bound to the result's content hash and re-checked at resolution. |
| 7.7 | Supervisor | SYN-04 (live) | **Supervisor review** › **Approve proposed internal outcome** › **No further action recommended**, then **Confirm**; then **Record resolution**, then **Confirm** | (recorded live) The case closes. The case summary shows **Decision: No further action recommended**. | An independent second person decides. Nobody can approve their own escalation. |

SYN-01 stays escalated, waiting for the information it requested.

**Before a resolution, the system requires:**
- a current analyst note;
- no open information requests;
- at least one reviewed AI finding;
- a supervisor who is not the person who escalated.

The case summary's **Decision** now shows the recorded resolution, including outcomes that keep the case open, such as "Escalated for compliance review".

## 8. Audit and oversight

| # | Who | Page | Do this | Screen shows | Why |
|---|---|---|---|---|---|
| 8.1 | Admin / supervisor | Case › **Activity History** | Click **Activity History** | Every action on the case: what happened, when, and whether it was you or another user ([40](screens/40-activity-history.png)) | A complete trail for review and audit. |
| 8.2 | Any role | Case › **Audit details** | Expand **Audit details** | Model, policy and explanation versions and hashes ([41](screens/41-audit-details.png)) | Anyone can check which exact model and policy produced a result. |
| 8.3 | Admin | Administration › **Provider Usage** | Open the page | Anthropic: model, requests, spend vs **$10.00 cap**, "one named approver per request · No automatic retries"; Luminal: Blocked. Also the regulation corpus line: 24 sections, fingerprint ✓ ([42](screens/42-provider-usage.png)) | AI spending is capped and visible. |
| 8.4 | Admin | Administration › **Diagnostics** | Open the page | Release, API service, Health: Ready ([45](screens/45-diagnostics.png)) | Confirms which build is running and that it is healthy. |

## 9. What the system will never do, and its limits

**It will never:**
- Take automatic case actions. Scores and AI findings never close, escalate or file anything; a person does.
- Call the AI without approval. Each request needs the owner's scope and a named approver, runs once, and stays within the spending cap.
- Show unverified claims. AI output is checked against the evidence and the cited text, or it is not shown. It abstains when evidence is incomplete.
- File a SAR. "Escalated for compliance review" is an internal outcome only.

**Known limits:**
- **Synthetic data only.** The model was trained on 10,000 synthetic credit-card-style alerts with a synthetic SAR label. No real firm data. No independent real-world validation.
- **The model does not see transactions.** It scores 27 declared account totals. It cannot see timing, income-to-spending ratios or counterparty networks; those appear only in the evidence.
- **Part 1020 bank rules only.** The corpus is a snapshot of 31 CFR Part 1020 and is labelled *Unapproved research · Not production regulatory guidance*.
- **Word-based retrieval.** Sections are ranked by which case and evidence-pattern words they contain, then by text-match score (PostgreSQL `ts_rank_cd`), not by meaning. The one-line sections §1020.310–.314 contain too few words to rank first; §1020.315 is the currency transaction reporting section that ranks first for SYN-01.
- **Research scope is small.** At most 3 cases, approved by the owner, per research scope.
