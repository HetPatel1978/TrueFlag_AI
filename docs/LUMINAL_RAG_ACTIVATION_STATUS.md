# Luminal and regulatory activation status

Latest first-probe work: [preflight findings and blockers](LUMINAL_FIRST_PROBE_PREFLIGHT.md).

Later implementation: [G4.2B.4](G4_2B_4_BOOTSTRAP.md) adds a disabled one-attempt bootstrap; fixture restoration, billing proof and current terms remain blocked.

Review: November 18, 2026. **Live activation is incomplete; actual inference requests: 0.**

## Provider

- The owner withdrew the earlier $200 floor. The default `bounded_probe_v3` no longer uses balance or an account-wide floor as a prerequisite. The original three-probe package retains a $1 application reservation ceiling and at most three attempts, with no automatic paid retry. These are application limits, not a verified invoice cap.
- `LLM_API_KEY` is accepted as a server-side fallback; the existing `INVESTIGATION_PROVIDER_API_KEY` takes precedence. The local demonstration worker intentionally has no provider key. No `.env` change or provider request was made.
- Adapter remains fixed to Luminal, `https://flash.luminal.cloud/v1/chat/completions`, `deepseek-ai/DeepSeek-V4.1-Flash`, strict schema and independent evidence verification. Model identity, response content, strict schema compatibility, usage, latency, charge and output verification were **not measured** against the provider.
- The existing probe approval requires the reviewed exact payload and a defensible charge bound. Public [pricing](https://www.luminal.com/pricing) includes reasoning tokens in output charges, but does not establish that the exact approved `max_tokens` bounds all billed reasoning or that admitted input bytes bound provider token accounting. The application does not have a separately authorized exact-payload bootstrap that can verify compatibility without declaring the contract verified first. `bounded_probe_v3` therefore fails closed before transport; neither the $200 floor nor an unverified balance blocks it.
- Future safe work: verify applicable vendor token/cost limits and pricing, implement an exact-payload, one-attempt bootstrap using the immutable ledger and current source/clock authorization, then conduct the already authorized synthetic probes. Any changed payload or broader live use needs the applicable separate authorization and evaluation. Do not set the contract-verified flag as a substitute for a successful response.

## Regulatory research

- Existing locally staged eCFR November 2, 2026 bank provisions and FinCEN SAR FAQ bytes matched their recorded acquisition hashes. They remain unapproved historical candidates; FinCEN's historical validity remains unverified. The [FFIEC manual](https://bsaaml.ffiec.gov/manual) was viewed publicly, not ingested or approved. No new document was published, approved or inserted into the user's database.
- An admin-only, rate-limited research endpoint searches metadata of already admitted, unapproved versions in PostgreSQL. It returns at most 20 results, no passage text, and explicitly marks them ineligible for AI grounding. The administration screen labels these results unapproved and only links HTTPS official sources. The existing analyst retrieval path continues to require approved, published sources and case authorization. With an empty catalog, research returns no results.
- No qualified regulatory approvals, independent expert labels, approved context or legal citation validation against real model output exist. The current simulated draft does not inject regulatory context. Evidence-only offline investigation remains available; real evidence-only AI and regulatory grounding remain unimplemented until their gates pass.

## Verification

- Offline provider and historical/new policy tests: **93 passed, 3 skipped, 3 deselected**; no provider egress. The first attempt had one Windows temporary-directory permission error; a fresh project-local temporary directory passed.
- Real isolated PostgreSQL provider, regulatory and draft tests: **88 passed**. After the final bounded-query change, the new research and policy acceptance tests separately passed **2/2**.
- React: **147 passed**. Chromium: offline investigation **6 passed**; provider administration, research, analyst denial and revocation **3 passed**. An initial provider browser test failed because the financial details were collapsed; the corrected test passed.
- After restarting the existing isolated local application, the administrator screen reported the provider blocked and the unapproved-research API returned HTTP 200 with zero catalog entries. The direct FFIEC raw-file download failed; no raw document was ingested from it. Existing queued assessment work resumed.
- Pinned Linux ML: **178 passed**. Frozen parity: RF **4,000/4,000**, policy **12,000/12,000**, SHAP **4,000/4,000**, zero mismatches; RF max error 0, SHAP max reconstruction residual `3.1086244689504383e-15`.
- Prior clock instability remains a release risk; no clock guard was relaxed. This is not a production acceptance or legal certification.
