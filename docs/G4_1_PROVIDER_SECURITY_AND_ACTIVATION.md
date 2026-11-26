# G4.1 — Provider security and activation gate

## 1. Current decision

- **Not authorized for live inference. Zero live inference requests executed.** Existing `.env` and credentials are not overwritten, displayed or activated.
- Tests use explicit synthetic, nonworking keys, fake approval IDs/digests, MockTransport and isolated PostgreSQL. These are not real approvals, legal determinations or live compatibility evidence.
- The default external enable flag is false; key/approval/digest are empty, contract verification false, rates and spend ceiling zero. Existing legacy `LLM_PROVIDER`/`LLM_API_KEY` placeholders do not activate this adapter.
- No external provider controls or new AI button are added to React. Ordinary case access never constitutes consent for data export or provider approval.

## 2. Server configuration

| Setting / configuration | Required behavior |
|---|---|
| `INVESTIGATION_EXTERNAL_ENABLED` | Explicit switch, false by default. Simulation remains separately configured; mixed simulation/candidate execution is rejected rather than silently falling back. |
| `INVESTIGATION_PROVIDER_API_KEY` | Server-side `SecretStr`; never persisted in run configuration/audit or supplied to frontend. Sent only as bearer header to the fixed HTTPS host. |
| `INVESTIGATION_PROVIDER_APPROVAL_ID` | Nonempty operator-held grant reference; must match immutable candidate configuration. Reusing a grant preserves its cumulative reservations. |
| `INVESTIGATION_PROVIDER_TERMS_SHA256` | Exact human-reviewed terms dossier digest; must match candidate config. No real approved digest is fabricated by this task. |
| `INVESTIGATION_PROVIDER_CONTRACT_VERIFIED` | False until a separately authorized capability probe confirms model, auth, schema, envelope, usage and billing semantics. Mock tests cannot justify setting this in a deployed environment. |
| `INVESTIGATION_PROVIDER_INPUT_USD_PER_MILLION`, `...OUTPUT_USD_PER_MILLION` | Explicit approved rates, zero by default; exact match to candidate config. Public pricing is never silently applied as consent. |
| `INVESTIGATION_PROVIDER_SPEND_LIMIT_USD` | Retained approval-wide reservation ceiling, default 0, maximum 5 USD. Per-run cost must also fit. All completed/failed/ambiguous attempt reservations count. |
| `LiveProviderConfig` | Registered Luminal model/host only; synthetic-only data, approval/digest, versioned prompt/output, bytes/tokens/timeouts/attempts/rates/cost. Extra keys (including credentials) rejected. |

Configuration is an operator attestation, not independent proof that a qualified human approved the terms. Anyone controlling trusted application code/DB/worker credentials remains inside the trusted administrative boundary; this is not a hostile-code sandbox or multi-tenant provider billing system.

## 3. Controls and failure semantics

| Boundary | Control / limit |
|---|---|
| Egress target | Fixed `https://flash.luminal.cloud/v1/chat/completions`; no arbitrary URL, model discovery, redirects, tools or model-initiated retrieval. TLS verification retained; environment proxies disabled. Deployment network/DNS allowlisting remains an operator prerequisite. |
| Input | Existing independent packet verifier and minimizer; no actor/case/customer/account IDs, raw predictors, source prose, credentials or security tokens. Opaque record/fact/assessment references and synthetic observed values remain sensitive transfer context requiring consent. |
| Input integrity | Immutable parent/config/prompt/input fingerprints; fresh authorization and clock checks before dispatch and independent source/numeric checks before publication. No snapshot bypass or expiry extension. |
| Prompt injection | Source content treated as data in a distinct user message; fixed system prompt; strict selection grammar; no accepted free-text allegations or executable tools. These are containment tests, not live-model injection-resistance proof. |
| Transport bounds | One connection/request, no hidden retries, bounded streamed response, no compressed response, bounded JSON parsing and no upstream body/error reflection. Child stdout/stderr and resource bounds apply. |
| Cancellation | Parent checks cancellation and kills the Linux child process group on cancel/deadline. Already-delivered bytes cannot be recalled and billing may remain unknown. Process death/recovery never assumes a paid request did not run. |
| Retry | Candidate retry only on explicit 429 rejection, within attempts/budget, bounded backoff. Numeric Retry-After capped at 30 seconds; longer/provider-date hints need confirmation in G4.2. No automatic timeout/network/5xx/incomplete replay. |
| Spending | PostgreSQL advisory lock serializes approval-wide reservations across API/worker processes. No refund based only on absent response. Rates/tokens are configured/reported estimates, not authoritative vendor invoices. A verified tokenizer/context cap and provider/account-side hard spending cap remain required for any actual spending guarantee. |
| Publication | JSON validity alone is insufficient. Current case/source/assessment/clock verification and exact selectors/numbers are mandatory. No unauthorized or stale draft is published. |
| Audit/logging | Existing immutable attempt/receipt plus atomic draft/audit/status writes. Receipts retain response digest, typed usage and elapsed time; no raw model text or customer features in logs/audits. Failures use fixed safe codes. |

No regulatory corpus is sent. Regulatory context stays `unavailable_unapproved`, citations empty, final decisions/human conclusions empty. Provider output cannot dismiss, close, escalate automatically or submit a SAR.

## 4. Required human actions before any live test

1. Approve the exact synthetic payload scope, provider/model/endpoint, backup-provider routing, retention/training/region/subprocessor terms, maximum calls and total spend. Review [official terms](https://dash.luminal.com/terms), [pricing](https://www.luminal.com/pricing) and independently obtain the unavailable detailed privacy terms; archive exact versions/digests.
2. Establish an isolated runner and provider-side/account spending restriction. Do not treat WSL/Docker as an independent clock source or a local token estimate as a hard vendor billing cap.
3. Separately authorize and run a minimal capability probe using an approved test procedure before setting contract verification true. This worker does not self-certify compatibility or run such a probe automatically.
4. Provision a scoped server key and immutable grant/terms/rates/configuration; use a new reviewed grant for intentional budget expansion. Recheck approval when terms, endpoint behavior, model aliases or rates change.
5. Perform G4.2 independent evaluation. Activation of the analyst workflow still requires its separate acceptance; no G4.3 AI button appears solely because a key exists.

## 5. Residual risks

- Upstream retention/backup routing details and actual structured-output support remain unverified. API availability or model aliases may change.
- Cancellation cannot undo egress; timeouts may incur charges. Conservative retained reservations intentionally trade availability for billing safety.
- Selection/reference integrity is not semantic entailment, causal proof or legal correctness. G4.2 requires independent human judgments and held-out cases.
- Local clock instability continues to block release acceptance. This task changes neither host synchronization nor the existing evidence-clock safeguards.
- No provider approval, security certification, legal certification, regulatory publication, live demo change or deployment occurs in G4.1.
