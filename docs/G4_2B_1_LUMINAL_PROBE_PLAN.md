# G4.2B.1 — Proposed compatibility probes; no live execution

**Live Luminal inference requests executed: 0.** Activation remains OFF. The $10 objective conflicts with Sections 5 and 8; this preparation uses the stricter **$1.00 application reservation ceiling and three-attempt maximum**. Neither ceiling authorizes spending.

## Readiness

| Check | Verified local state |
| --- | --- |
| Expected `INVESTIGATION_PROVIDER_API_KEY` | Absent/empty in effective server Settings. |
| Legacy `LLM_API_KEY` | Present/nonempty; no value, fragment, fingerprint or length reported. Not automatically mapped or verified as a Luminal credential. |
| External activation / approval / contract flag | OFF / absent / false. Configured spend/rates/call allowance remain zero. `.env` unchanged. |
| Fixed candidate contract | `https://flash.luminal.cloud/v1/chat/completions`, `deepseek-ai/DeepSeek-V4.1-Flash`; configuration exists, authenticated availability unverified. |
| Processes | Original backend stopped; no live investigation-draft worker provisioned. Existing assessment/import workers observed only, not changed. |
| Data | Three newly generated synthetic sources only; no real customers, private scientific fixtures, RF outputs, analyst notes or 36-case benchmark in the probe package. |

## Three-request proposal

All requests reuse `LuminalProvider.request_body`, existing prompt/schema, one assistant choice and `stream=false`. All use strict JSON-schema output; Probe A does not introduce a permissive text fallback. There is no new transport or live probe CLI.

| Probe | Purpose/input | Input cap | Output cap | Request bytes | Conservative reservation |
| --- | --- | ---: | ---: | ---: | ---: |
| **A** | Connectivity, authentication outcome, exact returned model and envelope. Empty evidence projection; missing evidence explicitly requires abstention. | 8,192 | 512 | 6,820 | **$0.00992256** |
| **B** | Full versioned strict-schema contract: independently verified unavailable-evidence case, nullable financial fields, references and required abstention. | 16,384 | 1,024 | 9,790 | **$0.01984512** |
| **C** | Source grounding: four fresh USD transactions, source-version references and independently recomputed count/total. Coverage is partial and must remain qualified/abstained. | 32,768 | 2,048 | 11,126 | **$0.03969024** |
| **Total** | Maximum three external attempts; no paid retry. | 57,344 | 3,584 | — | **$0.06945792** |

Reservations use a 2× rate margin and charge **all** reserved tokens at the higher padded rate, ignoring cache discounts. They are conditional application-side arithmetic, not a verified invoice upper bound. Input byte admission is not a confirmed provider tokenizer. [Privacy/cost review](G4_2B_1_PROVIDER_PRIVACY_AND_COST_REVIEW.md)

### Acceptance and stopping rules

| Probe | Required response/acceptance | Failure / stop |
| --- | --- | --- |
| A | HTTP 200, JSON, exact candidate model, one assistant choice, completed nonempty strict-schema response, valid nonnegative integer usage within ceilings; independent parsing. | Any auth error, unsupported model/format, redirect, refusal, truncation, absent/excess usage, timeout or unknown delivery. Stop; do not spend B/C. |
| B | Exact existing `AIProposal` schema, correct packet identity, no invented fields, required abstention and preservation of missing evidence/limitations. Existing verifier must accept. | Permissive parsing, unsupported schema, fabricated facts/references, suppressed gaps or invalid values. No format downgrade or retry. |
| C | Source/numeric verifier accepts exact source references, **4 observations / USD 160.09**. Source amounts: USD 30.98, 9.10, 56.42, 63.59. Currency/time windows, count and sums are recomputed independently. Preserve partial-history limitation and abstention. | Foreign/stale references, wrong totals/currency/count/window, criminal/SAR claims, unqualified behavioral conclusion, revoked authority or clock uncertainty. No publication. |

Probes A/B test missing evidence, **not observed zero activity**. No probe is a test of real AML semantic quality. C's total is gross recorded activity, not net/settled cash flow or proof of criminal conduct.

## Concrete approval package

- [Pending manifest](../runtime/g4-2b-1/approval/approval-package.json), exact [A](../runtime/g4-2b-1/approval/A.request.json), [B](../runtime/g4-2b-1/approval/B.request.json), [C](../runtime/g4-2b-1/approval/C.request.json) request bytes, and local `*.sources.json` independent source/packet dossiers. Nothing was uploaded or sent.
- Package SHA-256: `338703d5b331f6d98e84e58be4977adb49cf80a269af2fb49cacbe74b0d99183`.

| Probe | Exact request SHA-256 |
| --- | --- |
| A | `135f684427912c0231d0a97f09f7773ff73882e033aed5045fd59fd350c886f6` |
| B | `f2f4bc4b23793f45a8d40f85db5ceeb83ef3f90aa0b3c375570083431abf4fa9` |
| C | `fee358bc2cf3ea27bd757ed75dcd9b66edbc1ba35665513153e17e4e08f26b2a` |

These are **public synthetic payload/document identities, never key fingerprints**. The manifest is immutable proposed content with all eight owner decisions blank, `activation_authorized=false`, and pricing/tokenizer verification false. It is not an executable credential or grant. Source packets are historical preparation artifacts, not current application authorization; any future dispatch must establish current authority and reapprove hashes if rematerialization changes the payload.

**Recommendation: NO-GO for live execution.** Separate [owner approval](G4_2B_1_APPROVAL_CHECKLIST.md), verified pricing/token accounting, strict-schema compatibility procedure, credential binding and clock-stable execution remain required. Stop at preparation.
