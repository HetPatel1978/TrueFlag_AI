# TrueFlag AI — Project Context

## What This Project Is

TrueFlag AI is an explainable AI system for AML (Anti-Money Laundering) alert triage in mid-market US banks. Banks generate thousands of compliance alerts per year from their Transaction Monitoring Systems (Verafin, NICE Actimize, Patriot Officer). Roughly 95% of these alerts are false positives that waste analyst time. Our system processes these alerts through an evidence-constrained AI pipeline and produces: a disposition (suspicious / not suspicious / needs review), evidence-linked rationale, validated regulatory citations, counterfactual sensitivity analysis, and optionally a draft SAR narrative — all with a complete audit trail.

This is a capstone project for Penn State Great Valley's MS in AI program (AI 894, Fall 2026) AND a real product being built for production use.

## The 6 Objectives

- **OB1 — Core Triage Engine:** The 8-stage pipeline that owns the AML triage decision. Everything else consumes its output.
- **OB2 — Regulatory Citation Engine:** Extends validated Core citations with regulatory context, supporting guidance, limitations/exceptions, and alternative interpretations.
- **OB3 — SAR Narrative Auto-Drafter:** Generates case-adaptive SAR draft narratives from validated evidence and citations for suspicious cases. Human review required before filing.
- **OB4 — Explainability Dashboard:** Visual decision support for analysts — factor weight chart, reliability indicator, regulatory context, decision trace, counterfactual sensitivity.
- **OB5 — Secure Data Boundary (cross-cutting):** PII tokenization at ingestion, encrypted mapping table, controlled de-tokenization only for authorized display and final regulatory output. Applies across OB1-OB4.
- **OB6 — Comprehensive Evaluation:** 200+ case benchmark, classification metrics, suspicious-case safety, workload reduction, citation/SAR quality, bias testing.

## The 8-Stage Core Pipeline (OB1)

```
CSV/API Input
  → S1: Secure Ingestion (validate file, batch creation, quarantine raw file)
  → S2: PII Tokenization (replace customer identifiers with tokens, encrypted mapping table)
  → S3: Rules Engine Pre-Filter (auto-resolve obvious cases, ~60-70% eliminated, zero AI cost)
  → S4: Pattern/Context Cache (reuse typology matches, regulatory retrievals, baseline summaries)
  → S5: Evidence Retrieval (typology matching + regulatory context lookup + customer context)
  → S6: Constrained LLM Reasoning (evidence bundle → structured factors + rationale + citations)
  → S7: Counterfactual Sensitivity Check (modify key factors, test decision robustness)
  → S8: Validation Layer (evidence tracing + citation validation + confidence calc + sufficiency check)
  → Validated disposition → DB persistence → OB2/OB3/OB4 consume downstream
```

## Architecture Principles

1. **The AI never sees real customer data.** PII is tokenized at S2. The LLM receives tokens (CUST_a8f2e1), never real names. Real PII exists only in the encrypted mapping table.
2. **The AI does not self-assess confidence.** It returns structured evidence factors with weights. The SYSTEM calculates confidence from those factors + counterfactual robustness. Before calibration data exists, scores are labeled "uncalibrated."
3. **Every citation is validated.** The LLM can only cite regulations that were provided in the S5 evidence bundle. S8 validates every citation against the knowledge base. Hallucinated statutes are stripped.
4. **Every factual claim is traced.** S8 checks that facts in the rationale match the input data. Untraceable claims are flagged as potential hallucinations.
5. **Human-in-the-loop always.** The system recommends; the analyst decides. Approve, override (with mandatory note), or escalate.
6. **Immutable audit trail.** Append-only audit_log table. DB triggers prevent UPDATE/DELETE. SHA-256 hash chain for tamper detection.
7. **Temperature = 0** in production. Same input must produce same output. Determinism is a regulatory requirement.

## Tech Stack

- **Language:** Python 3.11+
- **Backend:** FastAPI, Pydantic (validation), SQLAlchemy (ORM), Alembic (migrations)
- **Database:** PostgreSQL
- **AI/LLM:** Anthropic Claude API (primary), OpenRouter (multi-model fallback), OpenAI API
- **Frontend:** React or HTML/CSS/JS, Recharts or D3.js
- **Security:** bcrypt (passwords), python-jose (JWT), cryptography (AES-256)
- **Infrastructure:** Docker, Docker Compose, GitHub Actions
- **Evaluation:** scikit-learn, pandas, matplotlib

## Project Structure

```
trueflag-ai/
├── CLAUDE.md                    # This file — project context
├── README.md                    # Setup instructions
├── docker-compose.yml           # Full stack deployment
├── Dockerfile                   # Application container
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment variable template
├── .gitignore                   # Git ignore rules
│
├── src/
│   ├── __init__.py
│   │
│   ├── core/                    # OB1: Core Triage Pipeline
│   │   ├── __init__.py
│   │   ├── ingestion.py         # S1: File upload, validation, batch creation
│   │   ├── tokenizer.py         # S2: PII detection and tokenization
│   │   ├── rules_engine.py      # S3: Deterministic rules pre-filter
│   │   ├── cache.py             # S4: Pattern/context cache
│   │   ├── evidence.py          # S5: Typology matching + regulatory retrieval + customer context
│   │   ├── reasoning.py         # S6: Constrained LLM reasoning with structured output
│   │   ├── counterfactual.py    # S7: Counterfactual sensitivity checks
│   │   ├── validation.py        # S8: Evidence tracing, citation check, confidence, sufficiency
│   │   └── pipeline.py          # Orchestrator: runs S1-S8 in sequence
│   │
│   ├── regulatory/              # OB2: Regulatory Citation Engine
│   │   ├── __init__.py
│   │   ├── knowledge_base.py    # Load and query the regulatory KB
│   │   ├── context.py           # Generate regulatory context for validated citations
│   │   └── data/
│   │       └── regulations.json # Structured KB: USC, CFR, FinCEN, FFIEC entries
│   │
│   ├── sar/                     # OB3: SAR Narrative Auto-Drafter
│   │   ├── __init__.py
│   │   ├── drafter.py           # Generate SAR narrative from validated evidence
│   │   └── templates.py         # FinCEN narrative structure templates
│   │
│   ├── api/                     # REST API
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app, routes, middleware
│   │   ├── schemas.py           # Pydantic request/response models
│   │   ├── auth.py              # JWT authentication, RBAC
│   │   └── middleware.py        # CORS, security headers, logging, error handling
│   │
│   ├── db/                      # Database layer
│   │   ├── __init__.py
│   │   ├── models.py            # SQLAlchemy table definitions
│   │   ├── session.py           # Connection management, pooling
│   │   ├── queries.py           # Common query functions
│   │   └── audit.py             # Audit trail management, hash chain
│   │
│   ├── security/                # OB5: Secure Data Boundary
│   │   ├── __init__.py
│   │   ├── pii.py               # PII field detection
│   │   ├── encryption.py        # AES-256 encryption for mapping table
│   │   └── detokenizer.py       # Controlled de-tokenization for authorized contexts
│   │
│   ├── dashboard/               # OB4: Explainability Dashboard
│   │   └── (React app or HTML/JS files)
│   │
│   └── prompts/                 # System prompt versions
│       ├── system_v1.md         # Core triage prompt
│       ├── sar_v1.md            # SAR drafting prompt
│       └── counterfactual_v1.md # Counterfactual prompt template
│
├── alembic/                     # Database migrations
│   ├── alembic.ini
│   ├── env.py
│   └── versions/
│
├── eval/                        # OB6: Evaluation framework
│   ├── datasets/
│   │   ├── synthetic/           # 200+ custom cases
│   │   ├── ibm_aml/             # IBM AML benchmark data
│   │   └── fincen_files/        # ICIJ FinCEN Files data
│   ├── benchmark.py             # Evaluation runner
│   ├── metrics.py               # Classification, safety, workload metrics
│   └── reports/                 # Evaluation results
│
├── tests/
│   ├── test_ingestion.py
│   ├── test_tokenizer.py
│   ├── test_rules.py
│   ├── test_evidence.py
│   ├── test_reasoning.py
│   ├── test_validation.py
│   ├── test_api.py
│   └── test_audit.py
│
└── docs/
    ├── architecture.md          # System architecture documentation
    ├── pipeline.md              # Pipeline stage documentation
    └── api.md                   # API endpoint documentation
```

## Database Schema

```sql
-- Core tables
alerts (
  id UUID PK,
  batch_id UUID FK,
  external_id VARCHAR,          -- bank's own alert ID
  transaction_amount FLOAT,
  transaction_type VARCHAR,
  customer_token VARCHAR,        -- tokenized, never real name
  customer_id_token VARCHAR,     -- tokenized
  counterparty_country VARCHAR,
  alert_reason TEXT,
  customer_context TEXT,         -- tokenized context
  account_age_days INTEGER,
  risk_tier VARCHAR,
  submitted_at TIMESTAMPTZ,
  is_active BOOLEAN DEFAULT true
)

triage_results (
  id UUID PK,
  alert_id UUID FK → alerts.id,
  disposition VARCHAR,           -- suspicious | not_suspicious | needs_review
  evidence_factors JSON,         -- array of {factor, direction, weight, basis}
  confidence_score INTEGER,      -- calculated, not LLM self-reported
  calibration_status VARCHAR,    -- 'uncalibrated' until empirically validated
  rationale TEXT,
  recommended_action VARCHAR,    -- close | escalate | file_sar
  regulatory_citations JSON,
  counterfactual_results JSON,
  validation_results JSON,       -- {hallucinations, citations_stripped, sufficiency}
  decision_source VARCHAR,       -- rule | cache | tier1_model | tier2_model | safe_default
  model_used VARCHAR,
  prompt_version VARCHAR,
  latency_ms INTEGER,
  analyst_action VARCHAR,        -- NULL until reviewed: approved | overridden | escalated
  override_disposition VARCHAR,
  override_note TEXT,
  reviewed_by UUID FK → users.id,
  reviewed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ
)

audit_log (
  id UUID PK,
  entity_type VARCHAR,
  entity_id UUID,
  action VARCHAR,
  actor_type VARCHAR,            -- system | analyst | admin
  actor_id UUID,
  payload JSON,
  hash VARCHAR,                  -- SHA-256(entry_data + previous_entry.hash)
  created_at TIMESTAMPTZ
  -- NO UPDATE OR DELETE: enforced by DB trigger
)

users (
  id UUID PK,
  email VARCHAR UNIQUE,
  hashed_password VARCHAR,
  full_name VARCHAR,
  role VARCHAR,                  -- admin | analyst | viewer | examiner
  bank_id UUID,
  is_active BOOLEAN,
  created_at TIMESTAMPTZ
)

batches (
  id UUID PK,
  bank_id UUID,
  file_hash VARCHAR,             -- SHA-256 of uploaded file for dedup
  total_count INTEGER,
  completed_count INTEGER DEFAULT 0,
  suspicious_count INTEGER DEFAULT 0,
  clean_count INTEGER DEFAULT 0,
  review_count INTEGER DEFAULT 0,
  status VARCHAR,                -- uploading | validating | processing | complete | failed
  uploaded_by UUID FK → users.id,
  created_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ
)

pii_mappings (
  -- SEPARATE DATABASE OR SCHEMA with independent access controls
  token VARCHAR PK,
  encrypted_value BYTEA,         -- AES-256 encrypted real PII
  field_type VARCHAR,            -- customer_name | customer_id | account_number
  bank_id UUID,
  created_at TIMESTAMPTZ
)

rules (
  id UUID PK,
  bank_id UUID,                  -- NULL = global rule, UUID = bank-specific
  name VARCHAR,
  condition JSON,                -- structured rule definition
  action VARCHAR,                -- auto_close | auto_flag | pass
  version INTEGER,
  is_active BOOLEAN,
  created_by UUID,
  created_at TIMESTAMPTZ
)
```

## Regulatory Knowledge Base Structure

The knowledge base is a JSON file (src/regulatory/data/regulations.json) with ~40-60 entries:

```json
{
  "statutes": [
    {
      "code": "31 USC § 5324",
      "title": "Structuring Transactions to Evade Reporting Requirements",
      "source_url": "https://www.law.cornell.edu/uscode/text/31/5324",
      "summary": "Prohibits breaking transactions into smaller amounts to avoid CTR reporting thresholds",
      "keywords": ["structuring", "smurfing", "sub-10K", "CTR evasion"],
      "applicable_typologies": ["structuring"],
      "conditions": "Pattern of transactions below $10,000 threshold with no documented business purpose"
    }
  ],
  "cfr_requirements": [...],
  "fincen_advisories": [...],
  "ffiec_sections": [...]
}
```

Sources (all public domain / government published):
- US Code Title 31, Chapter 53: https://uscode.house.gov
- ECFR Title 31: https://www.ecfr.gov/current/title-31
- FFIEC BSA/AML Manual: https://bsaaml.ffiec.gov
- FinCEN Advisories: https://fincen.gov/resources/advisoriesbulletinsfact-sheets

## Security Requirements (Non-Negotiable)

These 20 controls must be implemented from day one, not bolted on later:

1. All secrets in environment variables, never in code. Pre-commit hook blocks commits containing key patterns.
2. .env in .gitignore BEFORE first commit.
3. PostgreSQL connections use SSL (sslmode=require).
4. Every DB query filters by bank_id — tenant isolation at ORM level.
5. PII fields encrypted (AES-256) in the mapping table. Main DB stores only tokens.
6. JWT auth on every endpoint except /health and /auth/login.
7. Role-based access: admin, analyst, viewer, examiner.
8. audit_log is INSERT-ONLY — DB trigger rejects UPDATE/DELETE.
9. Cookies: HTTPOnly, Secure, SameSite=Strict.
10. Passwords: bcrypt, 12 rounds minimum.
11. Login rate limiting: 5 failed attempts → 15-min lockout.
12. API rate limiting: 60 requests/minute per IP.
13. All DB access via SQLAlchemy — zero raw SQL.
14. Pydantic validation on every endpoint. CSV validation on every row.
15. XSS protection: sanitize all user-provided text before rendering.
16. File uploads: .csv/.xlsx only, max 10MB, quarantine → validate → delete raw file.
17. API responses trimmed — never leak internal UUIDs or system metadata.
18. Security headers: CSP, HSTS, X-Frame-Options, X-Content-Type-Options.
19. HTTPS everywhere in production.
20. pip-audit in CI pipeline — block on HIGH/CRITICAL vulnerabilities.

## Coding Standards

- **Python:** Follow PEP 8. Type hints on all function signatures. Docstrings on all public functions.
- **Naming:** snake_case for Python, camelCase for JavaScript. Descriptive names — `calculate_evidence_confidence` not `calc_conf`.
- **Error handling:** Never silently swallow exceptions. Log with structured JSON. Return clear error messages to the API consumer.
- **Testing:** Every pipeline stage has unit tests. Every API endpoint has integration tests. Target 80%+ coverage on critical paths.
- **Git:** Conventional commits (feat:, fix:, docs:, test:, refactor:). Feature branches + PR workflow.
- **Logging:** Structured JSON logs. NEVER log PII. Log tokens only.
- **Documentation:** Update docs/ when architecture changes. Keep CLAUDE.md current.

## Key Datasets

1. **IBM AML Data** (github.com/IBM/AML-Data): Transaction-level synthetic data. Needs transformation into alert-case format.
2. **ICIJ FinCEN Files** (icij.org/investigations/fincen-files): Real SAR-related material. Reported-suspicious, not confirmed criminal ground truth.
3. **Custom Synthetic Set** (eval/datasets/synthetic/): 200+ hand-crafted alert cases with ground truth labels, difficulty ratings, and provenance.

## Team

- **Het Patel**
- **Indranil Bera** 
- **Purvi Mehta** 
- **Zheng Tang** 

## What to Build First

Phase 1: Project scaffold + S1 + S2 + database + auth
1. Initialize FastAPI app with health endpoint
2. PostgreSQL + SQLAlchemy models + Alembic migrations for all tables
3. JWT authentication (login, token refresh, RBAC middleware)
4. S1: CSV upload endpoint with file validation and batch creation
5. S2: PII tokenizer with encrypted mapping table
6. Audit trail with hash chain and DB trigger
7. Docker Compose for local development
8. Basic test suite

Phase 2: S3 + S4 + S5 + S6 + regulatory KB
1. Rules engine with initial 6 rules (shadow/candidate mode)
2. Pattern/context cache (DB table implementation)
3. Evidence retrieval: typology matcher + regulatory KB loader + customer context
4. Constrained LLM reasoning with system prompt v1 and structured output
5. Multi-model fallback chain with circuit breaker
6. Prompt versioning system

Phase 3: S7 + S8 + OB2 + OB3
1. Counterfactual sensitivity checks with per-typology variation table
2. Validation layer: evidence tracing + citation validation + confidence calc + sufficiency
3. Regulatory context extension (OB2)
4. SAR narrative drafter (OB3)

Phase 4: OB4 + analyst workflow + reports
1. Explainability dashboard
2. Analyst review workflow (approve/override/escalate)
3. PDF/CSV report export
4. End-to-end integration