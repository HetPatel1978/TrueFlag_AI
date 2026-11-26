# G4.2B — Luminal compatibility and evaluation preparation

## Decision

**PREPARATION ONLY. Live execution is NOT AUTHORIZED / NOT EXECUTED.** The request explicitly requires separate provider, privacy, transfer and spending authorization. No key, case evidence or benchmark input was sent externally. Public documentation was read without authentication; those reads are not inference probes or model-quality evidence.

| Item | Verified status |
| --- | --- |
| Branch / HEAD | `codex/project-initialization` / `a3b2ba49cd92c4aa0401842fa4999897fdc28713`; prior work preserved, no commit/push/deployment. |
| Candidate | `deepseek-ai/DeepSeek-V4.1-Flash`, fixed `https://flash.luminal.cloud/v1/chat/completions`. The model string is listed on [official pricing](https://www.luminal.com/pricing); this does not establish authenticated availability, a specific weight revision or strict-schema support. |
| API documentation | [Official terms](https://dash.luminal.com/terms) describe chat-completions compatibility. An exact field-level specification for strict `json_schema`, returned model/usage and rejection semantics was not obtained. Documentation/host attempts that were inaccessible were not treated as compatibility evidence. |
| Credential mapping | Local `.env` has a populated **`LLM_API_KEY`**, while `Settings`/adapter require **`INVESTIGATION_PROVIDER_API_KEY`**. The expected setting is empty. Presence does not verify vendor identity or credential validity. No automatic alias, copying, key replacement or `.env` edit. |
| Correct process | Original backend is stopped; no investigation-draft worker container exists. Existing assessment/import workers run without this key and are not provider workers. They were not changed or restarted. Host `Settings` is only a configuration observation, not proof of delivery to a live Linux provider process. |
| Gates | External execution false; simulation false in host configuration; approval ID/digest absent; contract flag false; approved rates/spend zero. Test fixtures use separate synthetic configuration and mock HTTP. |
| Actual live usage | **0** authenticated provider requests; **0** transmitted benchmark records; actual provider latency/tokens/quality **unmeasured**. No billing/account API called. |

## Changes and reuse

- Added `backend/app/services/provider_readiness.py` and `scripts/check_provider_readiness.py`: read-only, allowlisted configuration inventory; no DB, network, secret serialization or activation. Three tests reject any inference that configured flags constitute authorization. Run `.venv/Scripts/python.exe -B scripts/check_provider_readiness.py` locally; output contains key-presence booleans only.
- Reused unchanged Luminal adapter, strict output schema, minimizer, draft workers/attempt accounting, source/numeric verifier, immutable persistence and evaluation framework. No new model pipeline, provider calls, public inference API, schema migration or AI prompt tuning.
- Strengthened the existing browser revocation regression with explicit phase checkpoints and actual protected job-state verification. See [regression/readiness report](G4_2B_REGRESSION_AND_FRONTEND_READINESS.md).

## Compatibility procedure — proposed, not executable approval

1. Resolve the [approval/cost checklist](G4_2B_PROVIDER_APPROVAL_AND_COST_CONTROL.md), stable-runner and credential-binding blockers. Approve an exact synthetic minimized input, model/host, schema/prompt digests, one-attempt call allowance and conservative spend reservation. Do not mark an unverified contract as verified merely to bypass the first-probe gate.
2. Use one separately authorized, minimal missing-evidence input through the existing adapter contract. No customer identifiers, real records, tools, retrieval, uploaded documents or regulatory content. Freeze input/request hashes. The adapter's schema overhead must fit its input byte/token admission bound before sending.
3. Require strict `response_format.type=json_schema`, `strict=true`, exact model string, single assistant choice, complete response, no tools/redirects, bounded content and valid usage. The probe must test the actual schema, not a simple free-text echo. Unsupported format, unexpected alias/fallback, refusal, missing usage or malformed output is a failure; no downgrade/retry.
4. Record monotonic request latency, exact input/output hashes, returned identity, vendor token breakdown (including reasoning/cache accounting), configured-rate estimate and uncertainty. Keep actual billing distinct from estimates. Stop after the approved attempt, including timeout/unknown delivery; retain its reservation.
5. Only a successful, independently reviewed compatibility dossier can support a later bounded benchmark request. Compatibility alone cannot authorize production, establish semantic quality, approve privacy terms or turn on the frontend.

Current technical blockers include lack of an authenticated contract probe, no approved grant-wide call ceiling/expiry mechanism, no verified recipient/fallback restriction, unavailable stable-clock acceptance and missing independent semantic review. Existing flags and spend reservations are useful controls, not a complete owner-signed evaluation grant.

## Exact offline preparation identities

| Artifact | Canonical content SHA-256 |
| --- | --- |
| Dataset `contracts/investigation_eval_dataset_v1.json` | `e069fa565ae595372bd6c1e814c3a0c37ee80a8ac664ea882a42b308036710fa` |
| Dataset raw file SHA-256 | `afcdbbeb5701d62b46cae2282e2f03db1cd4a27e10f77b0637413d1cacff2c79` |
| Rubric `contracts/investigation_eval_rubric_v1.json` | `c67f2fd64a24e135298f73adeb9a1526ad56212e6b9ffdce336ce7f7349c19ba` |
| Existing live prompt, version `trueflag.ai-evidence-prompt.v1` | `5222a2cac72b2e0c0b5e2679f4084ab0d2e0d8df94e9f06fab55d7430fe07c5a` |
| Existing strict output schema | `a42923a45b297adafc3b2070f4e4447e289341523bb8a6a54e8977c5835459be` |

Canonical content hashes use existing `digest` normalization; raw file hashes bind exact bytes and are labeled separately. Protected `evaluation-approval-dossier.json` under the directory identified by `runtime/g4-2b/current.json` enumerates all **36** cases (18 development / 18 held-out), their fixture identities and blank independent human-review fields. It grants no transfer permission. Historical fixture authority is not current dispatch authority.
