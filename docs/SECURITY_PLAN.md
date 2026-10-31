# Security foundation and progressive controls

Scope: synthetic local demonstration. A passing foundation test is not a penetration test, regulatory approval or production acceptance.

| Control | Initialization status | Evidence / remaining work |
|---|---|---|
| Password storage | Implemented | Argon2 hash; explicit CLI provisioning; no default accounts; hash and login tests |
| Authentication | Implemented | Short-lived JWT; signature, issuer, audience, required expiry; invalid-token tests |
| Server RBAC | Implemented for available endpoints | Admin audit endpoint checks current DB role; missing auth/analyst rejection and deactivation tests |
| Case/tenant authorization | Pending | No case endpoints yet; assignment/organization policies before exposing evidence |
| Strict request validation | Implemented for login | Extra role field rejected; exact predictor validation belongs to Week 2 |
| Secrets | Local implementation | Generated ignored .env; no displayed credential values; production secret manager/rotation pending |
| Audit | Limited implementation | Auth/bootstrap events; no passwords/tokens recorded; tamper-resistant storage, denied actions and case events pending |
| Transport | Local loopback only | TLS at trusted deployment ingress required before network exposure; no claim of local HTTPS |
| Database | Partial | Named-volume PostgreSQL, readiness and constraints; Compose initialization account is not a least-privilege runtime role |
| Sensitive content | Boundary implemented | No private assets in build contexts/Git; synthetic-only alert DB constraint; external AI data policy pending |
| Prompt injection/leakage | Planned Week 3 | Treat evidence as untrusted data, enforce tool permissions before retrieval, validate citations, bound tokens/time/cost; test adversarial passages |
| Human approval | Planned domain/workflow | Separate scores/routes/dispositions; no consequential business endpoint enabled yet |
| Abuse protection | Pending Week 1 | Login rate limit, request-size limits and operational monitoring before network exposure |
| Browser protection | Partial | In-memory account verification, no token localStorage; container CSP; full workbench/XSS and browser acceptance pending |

## Required gates

- Week 1: authentication negative tests, permission tests, account provisioning procedure, login abuse controls and safe logs.
- Week 2: trusted artifacts only; never deserialize user-supplied pickle/joblib; unsupported inputs fail to review without successful-capture or dismissal credit.
- Week 3: approved provider/data boundary; source permissions, institution/jurisdiction/as-of filtering; fabricated citations and provider failures cause abstention.
- Week 4: case ownership, optimistic concurrency, approval permissions, authorized export, transactional actor audit, runtime DB roles, browser tests.
- Week 5: TLS, dependency review, backup/restore, rollback, rotation, bounded load and explicit deployment acceptance.

New data sources, public hosting, institutional use and actual customer data require separately agreed scope. No automatic filing, model promotion or retraining is authorized by a review action.
