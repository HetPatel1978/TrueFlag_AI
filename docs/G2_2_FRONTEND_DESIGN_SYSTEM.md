# G2.2 — Frontend design system

## 1. Scope

- Presentation and existing workflow integration only. Branch: `codex/project-initialization`, HEAD `a3b2ba49cd92c4aa0401842fa4999897fdc28713` plus preserved working-tree changes.
- Reuses G2.1 evidence retrieval, financial analytics, verified investigation coordinator and real assessment/batch APIs. No backend application, database schema, authorization, time guard or scientific behavior is redesigned.
- Apple-inspired hierarchy, restraint and system typography; no Apple assets, proprietary fonts, remote fonts or new icon dependencies. Existing approved TrueFlag logo and faded login watermark retained.
- Live demo images/schema are unchanged. The isolated preview uses this working tree, not the running demo's frontend image. Final identity and actual screenshots/results are in [visual QA](G2_2_VISUAL_QA_REPORT.md).

## 2. Shared implementation

| File | Responsibility |
|---|---|
| `frontend/src/design-system.css` | Shared color, radius, spacing, typography, motion and accessibility tokens |
| `frontend/src/ui.tsx` | Semantic PageHeader, StatusBadge, original SVG line Icon components |
| `frontend/src/terminology.ts` | Central business terminology, 27 declared predictor labels, processing/coverage labels and lossless decimal-string presentation |
| `frontend/src/styles.css` | Global shell, forms, tables, tabs, assessment components and responsive layout |
| `frontend/src/investigation.css` | Evidence/analysis layouts using shared tokens |
| `frontend/src/batch.css` | Batch layouts migrated from hardcoded colors to shared tokens |

Native links/buttons/selects/details remain semantic controls. Component labels do not change API values. No generic design library or new service is introduced.

## 3. Tokens

| Token family | Selected values / behavior |
|---|---|
| Surfaces | Page `#f6f7f9`; white surfaces; secondary `#f8f9fb`; subtle gray separators |
| Text | Charcoal `#23272f`; secondary `#606775`; system font stack with no downloads |
| Accent | Blue `#245fbb`; secondary teal `#157286` for signed contribution charts |
| Feedback | Distinct text/background/border tokens for warning and error; text labels accompany status dots |
| Shape | 7 / 11 / 14px radius tokens; minimal existing shadow |
| Spacing | 4 / 8 / 12 / 16 / 20 / 24 / 32px shared scale |
| Typography | Restrained case headers; tabular numerals for financial data; monospace identifiers confined mainly to source/advanced details |
| Interaction | >=40px main control height, visible 3px focus ring, 140ms color transitions; reduced-motion preference disables transitions/animation |
| Layout | 232px light sidebar; narrower tablet sidebar; stacked/wrapping mobile navigation; local horizontal scrolling for wide tables |

## 4. Business terminology

| Earlier implementation language | User-facing term |
|---|---|
| RF score | Alert Risk Assessment |
| SHAP explanation | Key Risk Drivers |
| Feature contributions | Contributing Risk Factors |
| Policy recommendation | Review Recommendation |
| Investigation packet | Investigation Summary |
| Evidence retrieval | Supporting Evidence |
| Transaction analytics | Transaction Activity Analysis |
| Source provenance | Evidence Source Details |
| Worker/job status | Processing Status |
| Human disposition | Case Resolution |
| Audit log | Activity History; naming reserved where a generic audit screen does not exist |
| Regulatory RAG / LLM output | Regulatory Guidance / AI-Assisted Findings; reserved names, no feature or route activated |
| `succeeded` / `abstained` | Completed / Further evidence needed; stored states unchanged |

- Score remains the existing model signal, never a likelihood/probability of actual money laundering. Contributions describe model behavior, not criminal causation.
- Recommendations never become analyst decisions. Existing review-reduction recommendation is presented as **Review prioritization suggested**; no dismissal/closure action is added.
- Feature labels reference the declared-input semantics in `docs/PHASE3_2_EVIDENCE_FOUNDATION.md`. The ambiguous `nbrCollections3y` window is explicitly **source period unconfirmed**, not asserted to be three years. PEP/home ownership remain declared indicators, not verified findings.
- Technical model/version/hash/SHAP terminology remains available in Advanced model details and source/summary verification disclosures. CSV mapping retains exact contract identifiers alongside readable labels.

## 5. Screens and hierarchy

| Area | Changes |
|---|---|
| Login | Existing logo/watermark, flat navy brand panel, system typography and consistent controls |
| Global shell | Light sidebar, original line icons, active links, case-context navigation, real case breadcrumbs, memory-session sign-out |
| Alerts & Cases | Existing authorized queue, filters/sorting/pagination; shared header and clean table styling; no fabricated aggregate dashboard |
| Case overview | Short case identifier, wrapping source reference, assigned investigator, Case Resolution distinction, real assessment/drivers/history |
| Investigation | Always-visible assessment/recommendation/coverage summary derived from authorized context; dedicated Customer Profile, Transaction Activity Analysis, Supporting Evidence and Investigation Summary sections |
| Financial analysis | Backend-authoritative amounts, currency/window, velocity and concentration; exact Decimal strings grouped for reading without Number conversion or rounding |
| Investigation Summary | Explicit generation, actual processing state, independently verified observations, questions/gaps/limitations, supporting records and requester-scoped history; technical hashes in disclosure |
| Batch Processing | Existing upload→map→validate→approve→import→assess→export workflow, shared status/palette, readable field names; explicit unit/import approvals preserved |

No invented global Overview, Investigations directory, cross-case assessment history, Regulatory Guidance or Administration destination is added. Every navigation link targets an existing authorized route. Case views and sidebar links share those routes.

## 6. Security and interaction preservation

- API clients, request payloads, policy values, idempotency keys and scientific contracts are preserved. Presentation labels do not mutate stored states.
- Permission/revision rechecks, abort cleanup, bounded polling, safe retry receipts and protected-state clearing remain in place. Clock uncertainty becomes a service-unavailable message; evidence remains withheld.
- Existing import checkboxes remain explicit approvals. No unsafe automatic mutation retry, case-resolution control or extra approval workflow is introduced.
- Missing income remains distinct from observed zero. Monetary strings retain exact digits/scale, including values beyond JavaScript's safe integer precision.
- Private assets/features, credentials and browser tokens are not added to UI storage or new diagnostics. Backend authorization remains authoritative.

## 7. Verification and remaining scope

- See [coverage matrix](G2_2_FEATURE_UI_COVERAGE_MATRIX.md) and [visual QA](G2_2_VISUAL_QA_REPORT.md) for observed results, limitations and screenshots.
- Original G1 dataset and known clock-stability blockers remain unchanged. Local visual acceptance is not native-Linux or production release acceptance.
- G2.3 candidates: investigator assignment workflow, better case discovery/resume navigation and usability review with analysts. Team-wide summary sharing, generic audit browsing and new analyst decisions require separate backend/security scope.
- No commit, push, deployment, G3 human decisions, G4/G5 work or external AI/regulatory activation is performed.
