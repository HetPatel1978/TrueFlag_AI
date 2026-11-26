# Live Claude + Regulatory RAG acceptance results

Date: November 22, 2026. **Overall: BLOCKED — not LIVE AI + RAG READY.**

## 1. Live-provider evidence

| Item | Actual outcome |
|---|---|
| Live requests in this task | **0** |
| HTTP status / returned model | Not available; no request dispatched |
| Token usage / actual charge | Not available; no provider usage receipt generated |
| Intended provider | Anthropic, `claude-sonnet-5-5`, `https://api.anthropic.com/v1/messages` |
| Existing v2 request | 11,540 bytes; SHA-256 `45cf3308e79f6bb86c932dba0e528cdba6b47b1c6b6f5c06d50c0880dcf935a9`; reproduces byte-for-byte after code changes |
| Owner decision | Pending; not consumed or inferred from the financial authorization |
| Historical attempts | Eight retained; zero v2 attempts and zero outstanding provider attempts at read-only inspection |
| Live compatibility / general activation | Not promoted; `.env` unchanged; project flags and existing application remain disabled for live generation |

Earlier HTTP 200/400 attempts are historical evidence, not successes of this task. The earlier complete 400 error body was not retained; its exact cause remains unconfirmed. New rejection diagnostics and offline tests do not establish genuine compatibility.

## 2. Clock remediation and repeated measurements

All three windows used Windows QueryPerformanceCounter round trips, Linux realtime/libc/raw/adjusted monotonic clocks and PostgreSQL `clock_timestamp()` against the isolated recovery cluster. No fake-time library or application guard override was used. Each window contained 120 host exchanges and hundreds of database samples.

| Window | Host-QPC duration | Windows backsteps | Linux backstep events | PG backsteps | Guest adjusted/raw monotonic ratio |
|---|---:|---:|---:|---:|---:|
| Before remediation | 120.307 s | 0 | 10 | 8 | 1.061818 |
| After Windows start/resync | 120.249 s | 0 | 8 | 7 | 1.061946 |
| Temporary WSL time-service stop | 120.257 s | 0 | 4 | 4 | 1.028590 |

Observed guest-minus-host envelopes were respectively −992.407…+767.843 ms, −972.851…+743.774 ms and −175.689…+1,495.130 ms. These are measurements with round-trip uncertainty, not a time correction or accuracy guarantee.

**Authorized actions and actual outcomes:**

1. The owner explicitly authorized Windows Time start/resync using its existing source. Unelevated start failed; the first elevation attempt returned `InvalidOperationException`. Following owner confirmation of Windows consent, the local-script elevation succeeded at `13:40:00.9616837 UTC`.
2. Windows Time became Running. Resync/status exited 0; leap indicator 0, stratum 5, last sync `08:40:01` America/New_York, last sync error 0. Existing peers and Manual startup type were preserved. The retained phase-offset reading was −0.9892815 s and root dispersion 8.7594596 s; successful status alone was not accepted as trustworthy guest time.
3. WSL is Ubuntu 24.04.3 / kernel 6.6.87.2. `systemd-timesyncd` was running/enabled, chrony inactive, and `timedatectl` claimed synchronized despite independently observed backsteps. The owner authorized a temporary time-service stop. Stop succeeded at `13:46:38.904213 UTC`; startup remained enabled.
4. Instability persisted, so the temporary service change was **restored** at `13:50:15.940817 UTC`; final state active/running/enabled. Windows Time remains running under its separate authorization. No WSL/Docker restart, NTP-peer change, clock-value write or floor reset occurred.

The supported investigation direction was checked against [Microsoft Windows Time tools](https://learn.microsoft.com/en-us/windows-server/networking/windows-time-service/Windows-Time-Service-Tools-and-Settings) and [Canonical WSL time synchronization](https://ubuntu.com/wsl/docs/stable/explanation/time-sync/). Coexisting time controllers were investigated; these observations **do not prove** which component causes the remaining adjustments.

### Current authorization checks

| Real-clock snapshot window | Passed | Denied | Epoch change |
|---|---:|---:|---|
| After Windows resync, 200 iterations | 197 | 3 | 3→4 |
| Temporary WSL service stop, 200 iterations | 195 | 5 | 4→6 |

Fresh authorized snapshots could be generated, but recurring `ClockUnavailable` denials prevent sustained readiness. Floor/epoch advances occurred only through normal observer transactions. No preincident snapshot was revived and no approval attempt was consumed. **Environment acceptance: FAIL.**

No independent native Linux runner was available through inspected local tools/configuration. Existing GitHub CI is push/PR-triggered and has not received this dirty/private candidate. No cloud resource, remote credential transfer or CI dispatch was initiated. Next environment action requires an approved broader maintenance plan or a supplied secure, independently synchronized Linux runner.

## 3. Actual automated results

| Execution | Passed | Failed | Setup errors | Skipped |
|---|---:|---:|---:|---:|
| Final offline Claude compact/development/legacy contract/provider/approval tests | 82 | 0 | 0 | 0 |
| Official candidate retrieval, parser, benchmark and review-protocol tests; real Linux/PostgreSQL | 90 | 0 | 0 | 0 |
| Final durable grounding + protected API + regulatory integration/context/benchmark selection; real Linux/PostgreSQL | 71 | 1 | 1 | 0 |
| React investigation, drafts, guidance and research tests | 33 | 0 | 0 | 0 |
| Controlled PostgreSQL clock, snapshot, readiness and worker-handshake/security tests | 38 | 0 | 0 | 0 |

Selections overlap; do not sum them into an independent full-suite count. The final 71-pass PostgreSQL run included all five newly added compact-grounding integration cases passing. Its outstanding failures were:

- `test_existing_claude_transport_accepts_grounding_only_with_explicit_gate[legacy_v1]`: **direct `ClockUnavailable`** during current evidence retrieval, before transport.
- `test_simultaneous_workers_do_not_duplicate_publication`: setup parent returned `pending / processing_unavailable`, not the expected abstention. Its precise child/worker cause remains **unconfirmed**; do not classify it as clock-related solely by coincidence.

Earlier runs remain relevant: the pre-change selection had 67 passed / one clock setup error. The first compact run had 66 passed / five failures / two clock setup errors. Those five failures came from the new test fixture forwarding the local-only `schema_version` field into a deliberately closed compact wire format. The fixture was corrected to construct the actual compact contract; production extra-field rejection was preserved. No frozen source/reference output was edited. The final run above replaced neither the old failure history nor environmental acceptance.

The test suite covers forged/duplicate citation IDs, binding tampering, unapproved/withdrawn sources, wrong-user access, revocation, immutable binding storage, retries/concurrent workers, rollback, provider HTTP errors/timeouts, abstention, bounded transport and immutable stored results. Mock HTTP responses are explicit fixtures, not real Anthropic results or full browser acceptance.

React build (`tsc` + Vite) passed. Changed-file Ruff lint/format checks passed. Initial Windows test launch used an incomplete global Python environment; reran with the existing `.venv`. Initial frontend launch was blocked by esbuild's sandbox ancestor access; the authorized same tests outside that filesystem sandbox passed. No dependencies were installed or execution policy changed.

The controlled clock/snapshot/worker tests passed 38/38 after the synchronization experiments; they do not replace genuine environment stability checks. Final preservation evidence is retained privately. Publication/secret-ignore boundary verification passed for 531 source candidates. No full backend suite, frozen ML comparison or real-provider Chromium journey is claimed in this task. RF/policy/SHAP artifacts were not changed.

## 4. Retrieval against actual official source text

The existing isolated candidate query was exercised against retained eCFR §§ 1020.210 / 1020.320 text, not mock citations. Source/section hashes and the historical November 2 scope matched the frozen proposal. It remains a private candidate path; production retrieval still requires actual source approvals and publication.

| 31-case benchmark observation | Result |
|---|---|
| Question/control population | 19 information questions + 12 technical controls |
| Independent labels / approved official sources / published official releases | **0 / 0 / 0** |
| Engineering-only P@5 / R@5 / MRR across 19 questions | 0.1263157895 / 0.6315789474 / 0.6315789474 |
| Independently adjudicated metrics / claim-support coverage | **Not available** |
| Candidate timing | 28 queries; p50 4.853 ms, p95 6.576 ms; local observations, no production SLO |
| Scope-filter violations / forged citations accepted / unauthorized disclosures | **0 / 0 / 0** across the exercised controls |
| Approved-only runtime behavior | All 19 queries unavailable; **zero unapproved passages disclosed** |

These proposed relevance keys are engineering hypotheses, not independent ground truth. The benchmark records one false abstention under those hypotheses. Exact source-reference integrity is separate from legal/semantic citation support. FinCEN guidance remains excluded where historical validity is unverified. No LLM injection-safety or legal-certification claim follows from parser/retrieval tests.

## 5. Commands and retained evidence

From the repository root, using existing private recovery state and pinned image:

```powershell
python scripts/verify_reference_proposals.py
python runtime/live-claude-rag-20261122/measure.py sample
python runtime/live-claude-rag-20261122/post-sync/measure.py sample
python runtime/live-claude-rag-20261122/post-sync/measure.py authority
python runtime/live-claude-rag-20261122/post-wsl-stop/measure.py sample
python runtime/live-claude-rag-20261122/post-wsl-stop/measure.py authority
python runtime/live-claude-rag-20261122/tests.py
python runtime/live-claude-rag-20261122/regulatory_tests.py
python runtime/claude-demo-20261120/development-v2/clock-review-20261122/tests.py --security
$env:PYTHONPATH = 'backend'
.venv\Scripts\python.exe -m pytest backend/tests/test_claude_grounded_compact.py backend/tests/test_claude_development.py backend/tests/test_claude_contract.py backend/tests/test_claude_provider.py backend/tests/test_claude_live_validation_approval.py -q -p no:cacheprovider
# From frontend:
npm.cmd test -- src/drafts.test.tsx src/regulatory-guidance.test.tsx src/investigation.test.tsx src/regulatory-research.test.tsx
npm.cmd run build
```

Private clock samples, service receipts, source/ledger checks, request-contract review and failed/successful test output are retained under `runtime/live-claude-rag-20261122/`. No credentials, real customer data or private scientific fixtures were transmitted to a provider.

## 6. Acceptance matrix

| Required genuine acceptance | Status |
|---|---|
| Repeated healthy clock environment | **FAIL** |
| Authorized genuine Claude response | **NOT RUN** — clock block and pending exact approval |
| Live JSON + independent numeric/evidence/citation verification | **NOT RUN** |
| Official-source hashes / candidate retrieval | **PASS technically**, qualified source approval absent |
| Compact grounded adapter capability | **Offline tests and new PG cases passed**, not live compatibility |
| Complete one-action durable financial+RAG orchestration | **INCOMPLETE** |
| Real Claude+RAG findings in React, refresh, casework/audit journey | **NOT RUN / BLOCKED** |
| Security, source-review and human decision gates retained | Enforced in exercised tests; no bypass or autonomous action |

There is no safe basis to enable general live analyst inference or present a live Claude+official-RAG demonstration yet.
