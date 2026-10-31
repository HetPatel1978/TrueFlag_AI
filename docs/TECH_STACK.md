# Technology choices

| Layer | Choice | Rationale / boundary |
|---|---|---|
| Service | Python 3.11, FastAPI | Typed validation and existing backend concepts; service package `app` avoids research namespace collision |
| Persistence | PostgreSQL 17, SQLAlchemy 2, Alembic | Transactional domain and explicit schema changes; SQLite only for disposable unit tests |
| Authentication | Argon2 via pwdlib; short-lived HS256 JWT via PyJWT | Explicit provisioned demo accounts; validate signature/issuer/audience/expiry and look up active role each request; OIDC is a later deployment decision |
| Frontend | React 19, TypeScript 5, Vite 7, Node 24 | Typed UI and local proxy; exact transitive installation in package-lock.json |
| Checks | pytest, Ruff, Vitest, ESLint, Prettier | Security behavior tests, type/build checks and reproducible formatting |
| Baseline ML | Separate Python 3.11 environment, exact recorded sklearn/SHAP pins | Preserve fitted pipeline behavior; no torch dependency needed for RF inference |
| Evidence | Local ignored assets initially; versioned object-store boundary | Avoid forcing a cloud vendor or putting private content in Git |
| RAG/AI | Provider-neutral Protocol now; approved provider and scoped retrieval in Week 3 | No installed SDK/provider, mock investigation or live retrieval claim |
| Deployment | Docker Compose; non-root app containers; loopback ports | Practical local demonstration; TLS, runtime DB least privilege and operational controls remain deployment gates |
| CI | GitHub Actions with PostgreSQL service | Tests, lint/build, migration consistency, publication checks; no private baseline dependency |

`backend/requirements.lock` is the resolved service environment; `backend/ml-requirements.txt` preserves scientific direct pins. Do not combine environments to resolve conflicts by upgrading the retained model dependencies.

## Reference documentation

- [FastAPI authentication](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/)
- [SQLAlchemy transactions](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html)
- [Alembic tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
- [Vite prerequisites](https://vite.dev/guide/)

Dependency audit findings and tested versions belong in SETUP_STATUS. Do not use automatic major-version audit fixes without compatibility checks.
