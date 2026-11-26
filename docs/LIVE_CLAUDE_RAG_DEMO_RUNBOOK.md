# Claude + Regulatory RAG demonstration runbook

Date: November 22, 2026. **Not ready for a live-AI/RAG recording.** The following distinguishes the current application from the remaining acceptance journey.

## 1. Current application

| Item | Verified state |
|---|---|
| Frontend | `http://127.0.0.1:5173` |
| Backend | `http://127.0.0.1:8010` |
| Runtime | Existing isolated local application, schema `0019_upload_sessions` |
| Login | Existing account/session; use the established private local login procedure. No password or token is included here |
| Running services | API/frontend, PostgreSQL, assessment/import/packet/draft workers and dispatcher reported running/idle during this task |
| AI mode | Offline simulation; provider key not mounted in that runtime. Key presence in project `.env` is separate from runtime activation |
| Regulatory guidance | No approved official collection established; unapproved research metadata is not AI grounding |

Do not relabel existing simulation findings as Claude output. Do not use this runtime to claim candidate-schema acceptance.

## 2. Exact isolated validation case

- Case ID: `e4d9ce8f-6979-47e2-a5aa-6accf145a843`.
- Private Claude probe schema in the identity-verified recovery database; **not the UI database**.
- Current evidence: 12 synthetic transactions, two financial summaries, 17 authorized active reference links; stored packet digest/minimization verified.
- No model assessment selected in this probe; do not invent an RF/SHAP assessment or risk score for it.
- Regulatory context: `unavailable_unapproved`.

There is presently **no verified browser link** to this private probe case. Changing a browser hash to its UUID does not connect the UI to that database. A separately isolated, compatible candidate API/worker/UI environment must be prepared and verified before recording. Do not point the running original demonstration database at candidate migrations.

## 3. Required gates, in order

1. **Clock:** verify the authorized synchronization changes and repeated host/guest/PostgreSQL observations plus fresh authorized snapshots. Any regression still blocks; preserve floors and advanced epochs.
2. **Sources:** obtain qualified, independently authorized decisions against the exact historical source hashes and applicability scope in [the source checklist](PHASE3_4_SOURCE_APPROVAL_CHECKLIST.md). Store real approval records privately under `assets/local/regulatory/reviews/`. Complete the existing reviewer/adjudication workflow; do not generate identities or independent labels.
3. **Wire approval:** the existing `claude-development-review-2026-11-22-v2` record remains pending and covers an evidence-only 11,540-byte request. A request containing regulatory passages is different and needs a new complete payload/hash/schema/limits/terms review and explicit owner authorization.
4. **One controlled request:** after current authorization, clock, source, snapshot and ledger checks pass, use the existing adapter/worker and immutable ledger. One attempt, no automatic retry. Record HTTP status, sanitized response/error, schema outcome, usage, estimated charge and independent evidence/citation results. A failed/ambiguous attempt must not be replayed.
5. **Operating acceptance:** real-response evaluation, candidate deployment compatibility, ongoing analyst authorization and server-side regulatory retrieval orchestration must pass before enabling general generation. No feature flag is an independent approval.

The old evidence-only execution command is intentionally not offered as a live-RAG shortcut: it neither includes regulatory passages nor has a current approved owner decision.

## 4. Recording journey after every gate passes

| Analyst action | Required genuine observation |
|---|---|
| Log in → Cases → assigned connected case | Authorized customer/account/transaction links; genuine persisted assessment when one exists |
| Review Evidence | Source identifiers, exact amounts/currencies, missing evidence and current revisions |
| Generate AI Investigation | Durable server admission; evidence preparation and permitted retrieval independent of an open browser |
| Inspect processing | Only stages supported by recorded backend state; no invented progress percentages |
| Open completed findings | Real provider/model identity, verified numeric/reference findings, limitations and mandatory human review |
| Open Regulatory Guidance | Actual approved retrieved passage text, source/version/digest, historical scope and authorization status |
| Refresh browser | Same stored, still-authorized verified result; no second paid request |
| Record note / follow-up / escalation | Existing human casework, supervisor authorization and immutable activity history |

This journey has **not** been completed with real Claude plus official RAG. A successful offline fixture or source parser test does not satisfy it.

## 5. Safe operational checks

From the repository root:

```powershell
python runtime/local-app/manage.py status
python scripts/verify_reference_proposals.py
python runtime/live-claude-rag-20261122/tests.py
python runtime/live-claude-rag-20261122/regulatory_tests.py
```

These local diagnostics require the pre-existing private recovery state and pinned image. They are not a portable production installer. The test transports are offline; source approvals/publication and live provider activation remain separate. No credentials should be printed or copied to a new runner without approved secure handling.

## 6. Time-service maintenance

Windows Time start/resync was separately authorized and succeeded using the existing configured source. WSL/Docker were not restarted, and no peer configuration was changed.

The owner subsequently authorized a **temporary** stop of Ubuntu 24.04 `systemd-timesyncd` for measurement. Startup enablement was preserved. Final restoration/measurement outcome is recorded in [test results](LIVE_CLAUDE_RAG_TEST_RESULTS.md); do not treat a temporary diagnostic stop as a permanent production time policy.

Do not run `hwclock -s`, set the system date, reset snapshot floors/epochs, extend the 900-second limit or use simulated clocks to claim genuine environment readiness.
