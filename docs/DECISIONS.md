# Architecture decisions

| ID | Decision | Status / rationale |
|---|---|---|
| ADR-001 | New sibling repository cloned from the explicit TrueFlag_AI remote; work on `codex/project-initialization` | Executed; preserve teammate folder, private package and existing main/archive branches |
| ADR-002 | Target intelligent alert/investigation overlay; first deliver secure foundation | Five-week scope; streaming/graph/behavioral models are expansion |
| ADR-003 | Modular FastAPI service plus isolated RF worker | Avoid premature microservices and incompatible scientific/service dependencies |
| ADR-004 | API package `app`; retain serialized `trueflag` names privately | Resolve regular-package collision without renaming serialized classes |
| ADR-005 | PostgreSQL source of truth, explicit Alembic migrations | Preserve cases/evidence/scores/decisions/audit separately; no auto create_all in application startup |
| ADR-006 | Locally provisioned Argon2/JWT accounts for demonstration | No public registration/default admin; role from database; OIDC and abuse controls remain deployment work |
| ADR-007 | Exact RF/preprocessing/policies stay immutable | No training/tuning or silent feature changes; replay is identity validation, not independent performance |
| ADR-008 | Teammate source remains ignored/local until redistribution rights clarified | No supplied license; copy only selected artifacts and references; never publish private data/models |
| ADR-009 | One provider-neutral investigation interface | Week 3 implementation; no mock endpoint, autonomous actions or mandatory multi-agent framework |
| ADR-010 | No automatic model learning from review actions | Reviewed outcomes, dataset curation and offline promotion require separate acceptance |
| ADR-011 | Containers publish loopback only | Local demonstration; no external deployment or certification claim |
| ADR-012 | Patched frontend tooling and minimatch 11 override | Initial dependency audit exposed vulnerable test/glob tooling; updated compatible lint/test versions and verified matcher override with lint, tests and build; remove override once upstream ranges are patched |
| ADR-013 | Host ports 8010 / 8088, configurable through .env | Port 8000 was already occupied; preserve the existing listener rather than stopping another project |

## Decisions still required

- Institution/jurisdiction and corpus source-use permissions.
- External LLM provider and allowed data boundary.
- Domain authorization/approval matrix and permitted workflow transitions.
- Hosting/TLS/identity strategy and performance envelope.
- Publication rights for teammate code and eventual repository license.

## Upstream engineering references

See TECH_STACK for framework documentation. Guidance informs implementation choices; it does not certify AML compliance or establish actual-data access rights.
