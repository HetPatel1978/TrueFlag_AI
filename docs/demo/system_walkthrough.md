# TrueFlag system walkthrough

A step-by-step tour of the whole system using the eight `SYN-` demo cases (see [demo_cases.md](demo_cases.md)).

All screenshots are in `screens/`. They come from an isolated dry run on the native Windows stack. That dry run used a throwaway database, which has been dropped. The screens show synthetic data only.

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
| 1.7 | Admin | Command line | Run `scripts/attach_demo_evidence.py --username windowsadmin` | `attached` for all 8 | Binds each case to its generated evidence, after checking that the inputs match exactly. Demo only. |

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

## 4. Case review: SYN-01 (structuring)

| # | Who | Page | Do this | Screen shows | Why |
|---|---|---|---|---|---|
| 4.1 | Analyst | Case › **Assess Alert** | Open case 4db2685e | Score 47.5%, Continue analyst review, ✓ Verified, and Key Risk Drivers ([14](screens/14-assess-syn01.png)) | See below. |
| 4.2 | Analyst | Case › **Review Evidence** | Click **Review Evidence** | See below ([15](screens/15-evidence-syn01.png)) | The analyst checks the score against the actual records. |
| 4.3 | Analyst | Compare | Open **SYN-05** › Assess Alert | Priority **High**, score **0.0%** ([17](screens/17-assess-syn05.png)) | Priority and score answer different questions. Coverage keeps this case for review anyway. |
| 4.4 | Analyst | Compare | Open **SYN-06** › Review Evidence | **Partial coverage**, 4 events, "Missing: Annual income, Expected activity" ([18](screens/18-evidence-syn06.png)) | Missing data is shown as missing, never as zero. |
| 4.5 | Analyst | Compare | Evidence for SYN-02, SYN-07, SYN-08 | In/out pairs within 1–2 days ([19](screens/19-evidence-syn02.png)); 14 days of sudden activity ([20](screens/20-evidence-syn07.png)); spending far above income ([21](screens/21-evidence-syn08.png)) | The story is visible in the evidence, even where the model cannot see it. |

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

**What you need before a live run (owner decisions, not demo steps):**
- The owner's research scope must name the case. The scope allows at most 3 cases and is tied to this database. New cases get their IDs at import, so a new scope is needed after the upload.
- Each request then needs its own approval.

Until both exist, the tab shows **"No authorized provider is available"** and the button is disabled ([16](screens/16-ai-investigation-syn01.png)). That is the control working.

**The live flow.** The steps below are described from the system's code and controls. **They were not captured**, because no scope covers the new cases and no paid request was made.

1. **Analyst prepares the request.** Click **Generate investigation**.
   - The system checks the evidence packet.
   - It retrieves regulation sections for this case.
   - It builds the *exact* request, which is shown under **AI Request Review**.
2. **The review panel shows:**
   - case, model and data scope ("Synthetic data only")
   - request limits and the spending reservation
   - the financial evidence to be sent, the regulatory sources, and the missing evidence and limitations
3. **Owner approves.** Only the named approver can click **Approve & Run Once**. Anyone else sees "Pending Owner Approval".
   - If the evidence changed since the request was prepared, nothing is sent and a refresh is required.
   - The spending cap is shown in Provider usage ($10.00 all-time in the demo).
4. **One run, no retries.** The request is sent once. A failure is recorded and is not repeated automatically.
5. **The result.** Every claim is checked against the evidence and the cited text before it is shown.
   - **Conclusion and Key findings**, with transaction chips such as "T1–T12".
   - **Regulatory basis:** only the sections the AI actually cited, each with "Used in: …". Other retrieved sections sit under **Also retrieved (n)**.
   - **How sources were retrieved:** the query words, the case inputs they came from, "Top N of 24 sections · text-match ranking".
   - The badge **Unapproved research · Not production regulatory guidance**.
6. **Traceability.** The record keeps:
   - the request and response hashes
   - the retrieved section IDs and excerpt hashes
   - the approval and the actor
   Stored results are re-verified when read.

**What the dry run shows instead (offline simulation).** For the dry run only, I turned on the offline simulation. It is labelled "Offline simulation, not a live LLM result" and makes no provider call. It produces findings that can be reviewed in step 7.

| # | Who | Page | Do this | Screen shows | Why |
|---|---|---|---|---|---|
| 5.1 | Analyst | SYN-01 › AI Investigation | Click **Generate investigation** | **Completed · Verified**. Conclusion: 12 transactions, $180,650. **Missing evidence:** expected customer activity, supporting documents, sampling information, settlement status ([28](screens/28-ai-result-syn01.png)) | The result states only what the records support, and lists what is missing. |
| 5.2 | Analyst | SYN-06 › AI Investigation | Click **Generate investigation** | **Further evidence needed**: "Not enough evidence to support a finding. The AI abstained" ([29](screens/29-ai-abstain-syn06.png)) | With only partial history, the system declines to conclude rather than guess. |
| 5.3 | Analyst | SYN-04 › AI Investigation | Click **Generate investigation** | Completed · Verified ([30](screens/30-ai-result-syn04.png)) | Needed so the case can be reviewed and closed in step 7. |

**How sources are retrieved for each case.**
- The query is built from three things:
  - the case's top 3 score-raising drivers, each mapped through a fixed table to plain regulatory words (for example, cash-like payments → "cash currency transaction")
  - a counterparty term
  - terms for the evidence that is always missing
- PostgreSQL ranks the 24 sections by text match (`ts_rank_cd`).
- Up to 3 sections are kept, dropping any that score below 25% of the best section.

## 6. Comparison: different cases retrieve different rules

| # | Who | Page | Do this | Screen shows | Why |
|---|---|---|---|---|---|
| 6.1 | Admin | Administration › Provider Usage › **Test retrieval** | Paste SYN-02's query (from `demo_cases_offline.json`), click **Test retrieval** | 1. §1020.315 Transactions of exempt persons, 2. §1020.220 Customer identification program, 3. §1020.320 Reports of suspicious transactions ([43](screens/43-test-retrieval-syn02.png)) | The ranking is visible and repeatable. No AI call is made. |
| 6.2 | Admin | Same | Paste SYN-07's query | 1. §1020.210 AML program requirements, 2. §1020.100 Definitions, 3. §1020.320 ([44](screens/44-test-retrieval-syn07.png)) | Different drivers lead to different rules. |

Test retrieval uses the same ranking as the per-case step. In the dry run, all 8 case queries returned the same sections as the offline check.

Across the 8 cases there are **4 different top sections** (§1020.210, .220, .315, .320) and 5 sections overall.

## 7. Human decision

| # | Who | Page | Do this | Screen shows | Why |
|---|---|---|---|---|---|
| 7.1 | Analyst | SYN-04 › **Human Decision** | Action **Write note**. Type the note, click **Submit investigation note** | [23](screens/23-note-syn04.png) | Notes cannot be edited; a correction is added as a new note. |
| 7.2 | Analyst | SYN-04 | Action **Review simulated findings** › **Load my verified simulated findings** › **Accept for consideration**. Add a rationale, click **Record finding review**, then **Confirm and record decision** | [31](screens/31-finding-review-syn04.png), confirmation [32](screens/32-confirm-decision.png) | AI findings are only inputs. A person accepts or rejects each one. |
| 7.3 | Analyst | SYN-04 | Action **Escalate to supervisor**. Rationale: "Recommend closing as a false positive…". Click **Request supervisor review**, then **Confirm** | 1 pending supervisor review ([33](screens/33-escalated-syn04.png)) | An analyst cannot close a case alone. |
| 7.4 | Analyst | SYN-01 | Action **Request information** (Customer documentation, assigned analyst) | [25](screens/25-request-info-syn01.png) | Missing evidence becomes a tracked, internal request. No email is sent. |
| 7.5 | Analyst | SYN-01 | Action **Respond to information request**, link a supporting record, click **Record request response** | [34](screens/34-info-response-syn01.png) | Open requests must be answered before any resolution. |
| 7.6 | Analyst | SYN-01 | Review the findings, write a note, then **Escalate to supervisor**: "Recommend compliance review for a possible SAR referral" | [35](screens/35-escalated-syn01.png) | The analyst proposes the outcome; the supervisor decides. |
| 7.7 | Supervisor | **Review Queue** | Open the queue | Escalated cases and how long they have waited ([36](screens/36-review-queue.png)) | Escalations cannot get lost. |
| 7.8 | Supervisor | SYN-04 › Human Decision | **Supervisor review** › **Approve proposed internal outcome** › outcome **No further action recommended**. Add a rationale, click **Review supervisor response**, then **Confirm** | [37](screens/37-supervisor-review-syn04.png) | An independent second person approves; nobody can approve their own escalation. |
| 7.9 | Supervisor | SYN-04 | **Record resolution**, then **Review final case resolution**, then **Confirm** | Resolution: **No further action recommended**. This is the false positive, closed ([38](screens/38-resolved-syn04.png)) | The case is closed by a person, with the full history kept. |
| 7.10 | Supervisor | SYN-01 | Approve with outcome **Escalated for compliance review**, then record the resolution | Resolution: **Escalated for compliance review**, with 7 history entries ([39](screens/39-resolved-syn01.png)) | Any SAR decision stays with compliance. TrueFlag never files one. |

**Rules the system enforces before a resolution:**
- a current analyst note
- no open information requests
- at least one reviewed finding
- a supervisor who is not the person who escalated

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
- **Text-match retrieval.** Ranking is by word overlap (PostgreSQL `ts_rank_cd`), not meaning. Common due-diligence terms dominate, so §1020.310–.314 (currency transaction reports) never rank first in these cases.
- **Research scope is small.** At most 3 cases, approved by the owner, per research scope.
