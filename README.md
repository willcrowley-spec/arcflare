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

Five services in a single Railway project:

| Service | Source | Port |
|---------|--------|------|
| `arcflare-backend` | `backend/` Dockerfile | `$PORT` (Railway-assigned) |
| `arcflare-worker` | `backend/` Dockerfile (different start command) | none |
| `arcflare-frontend` | `frontend/` Dockerfile | `$PORT` (Railway-assigned) |
| PostgreSQL | Railway managed | 5432 |
| Redis | Railway managed | 6379 |

### Step 1 — Create the project

1. Go to [railway.com](https://railway.com) → **New Project** → **Deploy from GitHub repo**
2. Select the `Crowley155/arcflare` repository
3. Railway creates one service automatically (may fail to build — that's fine, we'll configure it)

### Step 2 — Add PostgreSQL

1. In the project canvas: **+ New** → **Database** → **Add PostgreSQL**
2. Once provisioned, connect to the DB and enable extensions:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   CREATE EXTENSION IF NOT EXISTS pgcrypto;
   ```
   You can run this via Railway's **Data** tab, or connect with psql using the credentials from the PostgreSQL service's **Variables** tab.

### Step 3 — Add Redis

1. **+ New** → **Database** → **Add Redis**
2. No extra configuration needed

### Step 4 — Configure the Backend service

1. Click the auto-created service (or **+ New** → **GitHub Repo** → same repo)
2. **Settings** tab:
   - **Root Directory**: `backend`
   - **Builder**: Dockerfile
   - **Dockerfile Path**: `Dockerfile`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Health Check Path**: `/health`
3. **Variables** tab — add these (use Railway variable references where noted):

   | Variable | Value |
   |----------|-------|
   | `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (auto-linked) |
   | `DATABASE_URL_SYNC` | Same URL but replace `postgresql+asyncpg://` → `postgresql://` |
   | `REDIS_URL` | `${{Redis.REDIS_URL}}` (auto-linked) |
   | `CLERK_SECRET_KEY` | Your Clerk secret key |
   | `CLERK_PUBLISHABLE_KEY` | Your Clerk publishable key |
   | `CLERK_ISSUER` | `https://<your-instance>.clerk.accounts.dev` |
   | `OPENAI_API_KEY` | Your OpenAI key |
   | `ANTHROPIC_API_KEY` | Your Anthropic key |
   | `SALESFORCE_CLIENT_ID` | Connected App consumer key |
   | `SALESFORCE_CLIENT_SECRET` | Connected App consumer secret |
   | `SALESFORCE_REDIRECT_URI` | `https://<backend-domain>.up.railway.app/api/v1/connections/salesforce/callback` |
   | `ENCRYPTION_KEY` | Generate with: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
   | `FRONTEND_URL` | `https://<frontend-domain>.up.railway.app` |
   | `CORS_ORIGINS` | `https://<frontend-domain>.up.railway.app` |
   | `ENVIRONMENT` | `production` |

4. **Settings** → **Networking** → **Generate Domain** (note the URL for other service configs)

### Step 5 — Configure the Celery Worker service

1. **+ New** → **GitHub Repo** → same repo
2. **Settings**:
   - **Root Directory**: `backend`
   - **Builder**: Dockerfile
   - **Dockerfile Path**: `Dockerfile`
   - **Start Command**: `celery -A app.workers.celery_app worker --loglevel=info`
   - No health check needed (not an HTTP service)
   - No domain needed
3. **Variables**: Copy all backend variables (or use Railway's **Shared Variables** feature)

### Step 6 — Configure the Frontend service

1. **+ New** → **GitHub Repo** → same repo
2. **Settings**:
   - **Root Directory**: `frontend`
   - **Builder**: Dockerfile
   - **Dockerfile Path**: `Dockerfile`
   - **Start Command**: `serve -s dist -l $PORT`
3. **Variables**:

   | Variable | Value |
   |----------|-------|
   | `VITE_CLERK_PUBLISHABLE_KEY` | Your Clerk publishable key |
   | `VITE_API_URL` | `https://<backend-domain>.up.railway.app` |

   > Vite env vars are baked at build time. Set them **before** the first deploy.

4. **Settings** → **Networking** → **Generate Domain**

### Step 7 — Run database migrations

Open the backend service **Shell** tab (or use `railway run` from CLI):

```bash
alembic upgrade head
```

### Step 8 — Verify

- `https://<backend-domain>.up.railway.app/health` → `{"status":"ok"}`
- `https://<backend-domain>.up.railway.app/docs` → Swagger UI
- `https://<frontend-domain>.up.railway.app` → Arcflare UI

## Multi-Tenancy

Every API request is scoped to the authenticated user's Clerk organization. All database queries filter by `org_id`. No cross-tenant data access is possible through the API layer.

## API Documentation

Once the backend is running, interactive API docs are available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## License

Proprietary. All rights reserved.
