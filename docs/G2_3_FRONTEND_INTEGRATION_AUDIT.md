# G2.3 — Frontend integration audit

## 1. Coverage matrix

Verified connections below use real APIs and persisted synthetic PostgreSQL records in Chromium; component tests use explicitly synthetic contract fixtures. See [QA](G2_3_VISUAL_AND_FUNCTIONAL_QA.md) for actual outcomes and failed attempts.

| Capability | UI / actual API | Classification / evidence |
|---|---|---|
| Login/current user/logout | `App.tsx`: `/auth/token`, `/auth/me`; memory-only token and abort-on-logout | Integrated; React and browser login/role/revocation/logout |
| Case search/filters/sort/paging | `Dashboard`, `/#/`; `/case-queue` reuses `list_cases` | Integrated; per-role counts/search/paging, real browser queue |
| Assignment/reassignment | Case overview; `/assignment-options`, existing PUT `/assignment` | Integrated; manager-only dialog, server CAS/eligibility/rollback tests, real assignment/revocation |
| Enriched case overview | `/#/cases/{id}`; `/cases/{id}/workflow` | Integrated; scoped summary/name/stored recommendation, no predictors |
| Activity/Assignment History | `/#/cases/{id}/activity`; `/cases/{id}/activity` | Integrated; canonical-FK audit projection, paging/filter/redaction tests, real assignment history |
| Single assessment request/status | `/assessment` case tab; POST case `/assessments`, GET `/assessment-jobs/{id}` | Existing integration retained; real RF/Policy/SHAP worker, downtime/reassessment/idempotency browser tests |
| Saved scores/policy/SHAP/provenance/history | Case overview `Results`/`Explanation`; GET case `/assessments` and detail | Existing integration retained; verified saved outputs, version history and advanced provenance |
| Authorized customer/account/relationship evidence | Investigation Customer Profile; GET `/evidence`, POST `/customers`, `/related` | Existing integration retained; case/source/snapshot checks and missing/conflict displays |
| Transaction records/financial analytics | Transaction Activity Analysis; POST `/transactions`, `/activity` under case `/evidence` | Existing integration retained; explicit UTC window/currency, exact server Decimal results, coverage/limitations |
| Evidence sources/versions | Supporting Evidence from authorized context | Existing integration retained; permitted references only, source revocation clears evidence |
| Investigation requests/progress/verified packets | Investigation Summary; POST/GET case `/investigations`, run detail | Existing integration retained; deterministic coordinator and real worker; no LLM claim |
| Requester packet history | Investigation History inside workbench; GET case `/investigations` | Existing integration retained; requester scope unchanged; distinct from shared case Activity History |
| CSV contract/template/upload/resume | Admin Batch Processing, `/#/batch`; `/batch-uploads/contract`, `/template`, POST upload, GET metadata | Existing integration retained; upload progress/errors and explicit resume ID/link |
| Mapping/validation/error paging | Batch mapping/preview; columns, validation and errors APIs | Existing integration retained; exact 30-column contract and units; no fabricated missing values |
| Approval/durable import/progress | Batch import; POST validation `/imports`, GET import and `/rows` | Existing integration retained; explicit approval, idempotent lost-response/restart tests |
| Explicit batch assessment/results | Batch assessment; POST import `/assessments`, GET batch and `/results` | Existing integration retained; bounded existing dispatcher and real workers |
| Safe CSV export/case drill-down | Batch results; GET batch `/export`, existing case links | Existing integration retained; field allowlist/formula protection and permission checks |
| Release identity | Admin advanced footer; `/internal/release` | Existing integration retained; real candidate/source/schema identity |
| Legacy listing/overview/raw alert detail | `/cases`, `/overview`, `/cases/{id}` | Backend compatibility retained; UI uses sanitized workflow projections. Raw predictors deliberately not exposed. |
| Synthetic single-alert ingestion | POST `/alerts` | Backend-only integration API; CSV UI reaches existing ingestion internally, no additional raw-feature form needed. |
| Evidence manifests/model-signal helper reads | Existing evidence services/APIs | Backend-only alternate projections by design; workbench already exposes authorized context and stored model explanation. |
| Admin audit-event feed/internal metrics/health | `/admin/audit-events`, internal metrics/health/readiness | Backend-only operational surfaces; no generic admin or raw-audit destination. Case Activity History is the safe analyst projection. |
| Source admission/cohort provisioning/worker registration/recovery | Internal bounded Python services | Backend-only administration by design; no arbitrary tool runner in UI. |
| Regulatory search/citation resolution | Existing case `/references` gateway | Blocked from frontend activation pending human source approval/independent labels; no unapproved citations/publication. |
| Provider-backed draft/finding generation | Existing isolated draft foundations | Backend-only restricted foundation; live provider integration/evaluation deferred to G4. No provider credentials or egress activated. |
| Human notes/escalation/disposition/SAR | No new controls | Not implemented; G3 requires separately authorized human workflow. |
| Global investigation directory, graph intelligence, customer editing | No placeholder menu | Not implemented; not implied by case-scoped investigation. |
| All-upload discovery | Resume ID/link only | Existing API limitation; no fake complete import directory. |

## 2. State and security audit

- Visible controls call actual clients or change local view/filter state. Disabled controls express prerequisites, bounds, permissions or in-flight operations, not future-feature placeholders.
- Existing session transport handles 401/403/404 by clearing protected views; network/409/413/422/429/503 messages are sanitized. Clock uncertainty retains its explicit reason and fail-closed evidence clearing.
- Protected current-case reads recheck server authorization; assignment updates increment case version and remount dependent views. No frontend authorization claim replaces server checks.
- Model signals, exact financial strings and activity originate from stored/verified services; local presentation performs no financial inference or criminal attribution.
- Shared case activity is a historical event projection, **not** permission to read another requester's packet. Actor/source/worker/run/payload details are withheld.
- No mock production fallback, local-storage token, automatic dismissal/closure, AI-provider request or regulatory publication introduced.

## 3. Remaining integration boundaries

- Independent clock-stable release acceptance and controlled live-demo promotion remain separate prerequisites. Current demo schema remains untouched.
- Current polling can retain already-displayed data until the next check (normally 10 seconds); this is not immediate cross-browser notification.
- History page count and metadata are authorized at transaction time, not a frozen multi-page export. Concurrent events can shift offset pages; stable audit export/cursors are future work.
- Accessibility testing is automated WCAG-tagged axe plus specific keyboard/layout checks, not certification or a full assistive-technology audit.
