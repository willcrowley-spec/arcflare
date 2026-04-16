# Arcflare

**Enterprise platform for Salesforce metadata intelligence, business process mining, and AI-driven automation recommendations.**

Arcflare connects to client Salesforce orgs, ingests metadata and operational telemetry, vectorizes business documents, auto-generates process maps, and produces AI-driven automation recommendations with quantified ROI in dollars.

## Architecture

```
┌─────────────────┐     ┌──────────────────────────────────────────────┐
│  React Frontend │────▶│              FastAPI Backend                  │
│  (Vite + TS)    │     │                                              │
│                 │     │  ┌─────────────┐  ┌──────────────────────┐   │
│  • Analysis     │     │  │  Salesforce  │  │  Document Processor  │   │
│  • Organization │     │  │  Connector   │  │  (parse + vectorize) │   │
│  • Processes    │     │  └──────┬──────┘  └──────────┬───────────┘   │
│  • Recommends   │     │         │                    │               │
│  • Agents       │     │  ┌──────┴──────┐  ┌──────────┴───────────┐   │
│                 │     │  │   Process    │  │   Recommendation     │   │
│  Clerk Auth     │     │  │   Miner     │  │   Engine             │   │
│  React Flow     │     │  └─────────────┘  └──────────────────────┘   │
│  Recharts       │     │                                              │
└─────────────────┘     └──────────────┬───────────────────────────────┘
                                       │
                        ┌──────────────┼───────────────┐
                        ▼              ▼               ▼
                 ┌────────────┐ ┌───────────┐  ┌─────────────┐
                 │ PostgreSQL │ │   Redis   │  │   Railway   │
                 │ + pgvector │ │  (Celery) │  │   Volume    │
                 └────────────┘ └───────────┘  └─────────────┘
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TypeScript, Vite, TailwindCSS |
| State | Zustand |
| Visualizations | React Flow (process maps), Recharts (charts) |
| Auth | Clerk (multi-tenant orgs, SSO/SAML, MFA) |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic |
| Task Queue | Celery + Redis |
| Database | PostgreSQL 16 + pgvector |
| AI/ML | OpenAI embeddings, Anthropic Claude, LangChain |
| Deployment | Railway (5 services) |

## Project Structure

```
arcflare-demo/
├── frontend/           React SPA
│   └── src/
│       ├── components/ Shared UI components
│       ├── pages/      Analysis, Organization, Processes, Recommendations, Agents
│       ├── hooks/      Custom React hooks
│       ├── stores/     Zustand state management
│       ├── api/        Typed API client
│       ├── types/      TypeScript interfaces
│       └── lib/        Utilities and formatters
├── backend/            FastAPI application
│   ├── app/
│   │   ├── api/        Route handlers
│   │   ├── core/       Config, security, database
│   │   ├── models/     SQLAlchemy ORM models
│   │   ├── schemas/    Pydantic request/response schemas
│   │   ├── services/   Business logic per domain
│   │   └── workers/    Celery task definitions
│   └── alembic/        Database migrations
├── docs/               Design specs and documentation
├── docker-compose.yml  Local development environment
└── railway.toml        Railway deployment config
```

## Prerequisites

- Node.js 20+
- Python 3.12+
- Docker & Docker Compose (for local PostgreSQL + Redis)
- Clerk account (for authentication)
- OpenAI API key (for embeddings)
- Anthropic API key (for analysis)
- Salesforce Connected App credentials

## Local Development Setup

### 1. Clone and install

```bash
git clone <repo-url> arcflare-demo
cd arcflare-demo
```

### 2. Environment variables

```bash
cp .env.example .env
# Fill in all required values (see .env.example for descriptions)
```

### 3. Start infrastructure

```bash
docker compose up -d
# Starts PostgreSQL (with pgvector) and Redis
```

### 4. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Run database migrations
alembic upgrade head

# Start the API server
uvicorn app.main:app --reload --port 8000
```

### 5. Celery Worker (separate terminal)

```bash
cd backend
source .venv/bin/activate
celery -A app.workers.celery_app worker --loglevel=info
```

### 6. Frontend

```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:5173
```

## Environment Variables

| Variable | Description |
|----------|------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `CLERK_SECRET_KEY` | Clerk backend secret |
| `CLERK_PUBLISHABLE_KEY` | Clerk frontend publishable key |
| `OPENAI_API_KEY` | OpenAI API key for embeddings |
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude |
| `SALESFORCE_CLIENT_ID` | Connected App consumer key |
| `SALESFORCE_CLIENT_SECRET` | Connected App consumer secret |
| `SALESFORCE_REDIRECT_URI` | OAuth callback URL |
| `ENCRYPTION_KEY` | Fernet key for token encryption |
| `FRONTEND_URL` | Frontend origin for CORS |

## Key Features

### Salesforce Connector
OAuth 2.0 Web Server Flow — connect any Salesforce org without requiring setup in the target environment. Ingests metadata (objects, fields, Flows, Apex), record counts, and automation configuration.

### Document Repository
Upload business documents (PDF, DOCX, XLSX, PPTX). Automatically parsed, chunked, and vectorized with OpenAI embeddings. Stored in pgvector for RAG-powered search.

### Process Mining
Auto-generates business process maps from Salesforce metadata (Flows, triggers, object relationships) and extracted document content. Interactive React Flow visualization with drag-and-drop editing.

### Recommendation Engine
Cross-references metadata patterns, record telemetry, and document content to produce ranked automation recommendations with estimated ROI, implementation steps, and business impact metrics.

### Business Entity Profiler
Builds organizational hierarchy from Salesforce User/Role data. Models human capital cost deflection — hours saved, cost avoidance, and future hires deflected per recommendation.

### Agent Management
Track deployed AI agents with cost caps, token usage, accuracy metrics, and fleet-level analytics.

## Railway Deployment

Five services deployed to Railway:

| Service | Description |
|---------|------------|
| `arcflare-frontend` | Static React build served via `serve` |
| `arcflare-backend` | FastAPI on uvicorn |
| `arcflare-worker` | Celery worker (same Docker image, different entrypoint) |
| `arcflare-postgres` | Railway-managed PostgreSQL 16 + pgvector |
| `arcflare-redis` | Railway-managed Redis 7 |

## Multi-Tenancy

Every API request is scoped to the authenticated user's Clerk organization. All database queries filter by `org_id`. No cross-tenant data access is possible through the API layer.

## API Documentation

Once the backend is running, interactive API docs are available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## License

Proprietary. All rights reserved.
