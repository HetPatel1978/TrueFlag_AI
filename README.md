# TrueFlag AI

TrueFlag AI is an explainable AI system for AML (Anti-Money Laundering) alert triage in mid-market US banks. Banks generate thousands of compliance alerts per year from their Transaction Monitoring Systems (Verafin, NICE Actimize, Patriot Officer), and roughly 95% of these alerts are false positives that waste analyst time. TrueFlag AI processes alerts through an evidence-constrained AI pipeline and produces a disposition (suspicious / not suspicious / needs review), evidence-linked rationale, validated regulatory citations, counterfactual sensitivity analysis, and optionally a draft SAR narrative — all with a complete audit trail. This is a capstone project for Penn State Great Valley's MS in AI program (AI 894, Fall 2026) and a real product being built for production use.

## Setup

### Prerequisites

- Docker and Docker Compose
- Python 3.11+ (for local development outside Docker)
- Git

### Steps

1. Clone the repository:
   ```bash
   git clone https://github.com/HetPatel1978/TrueFlag_AI.git
   cd TrueFlag_AI
   ```

2. Create your environment file from the template and fill in the required values (database credentials, JWT secret, LLM API keys, etc.):
   ```bash
   cp .env.example .env
   ```

3. Start the full stack:
   ```bash
   docker-compose up
   ```

4. The API will be available at `http://localhost:8000` (see `/health` for a basic liveness check). Run database migrations if they haven't been applied automatically:
   ```bash
   docker-compose exec app alembic upgrade head
   ```

## Project Structure

```
trueflag-ai/
├── src/
│   ├── core/          # OB1: 8-stage core triage pipeline (ingestion → validation)
│   ├── regulatory/    # OB2: Regulatory citation engine + knowledge base
│   ├── sar/           # OB3: SAR narrative auto-drafter
│   ├── api/           # FastAPI app, routes, auth, middleware
│   ├── db/            # SQLAlchemy models, sessions, queries, audit trail
│   ├── security/      # OB5: PII tokenization, encryption, de-tokenization
│   ├── dashboard/      # OB4: Explainability dashboard (React/HTML/JS)
│   └── prompts/       # Versioned system prompts
├── alembic/           # Database migrations
├── eval/              # OB6: Evaluation framework, datasets, metrics, reports
├── tests/             # Unit and integration tests
├── docs/              # Architecture, pipeline, and API documentation
├── docker-compose.yml # Full stack deployment
├── Dockerfile         # Application container
└── requirements.txt   # Python dependencies
```

## Team

- Het Patel
- Indranil Bera
- Purvi Mehta
- Zheng Tang
