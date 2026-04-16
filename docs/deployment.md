# Arcflare Deployment Guide

Internal reference for deployment and local development setup.

## Prerequisites

- Node.js 20+
- Python 3.12+
- Docker & Docker Compose (for local PostgreSQL + Redis)
- Clerk account
- OpenAI API key
- Anthropic API key
- Salesforce Connected App credentials

## Local Development Setup

### 1. Clone and install

```bash
git clone <repo-url>
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

alembic upgrade head
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
| `DATABASE_URL` | PostgreSQL async connection string |
| `REDIS_URL` | Redis connection string |
| `CLERK_SECRET_KEY` | Clerk backend secret |
| `CLERK_PUBLISHABLE_KEY` | Clerk frontend publishable key |
| `OPENAI_API_KEY` | OpenAI API key for embeddings |
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude |
| `GEMINI_API_KEY` | Google Gemini API key |
| `SALESFORCE_CLIENT_ID` | Connected App consumer key |
| `SALESFORCE_CLIENT_SECRET` | Connected App consumer secret |
| `SALESFORCE_REDIRECT_URI` | OAuth callback URL |
| `ENCRYPTION_KEY` | Fernet key for token encryption |
| `FRONTEND_URL` | Frontend origin for CORS |
| `LLM_PROVIDER` | `openai`, `anthropic`, or `gemini` |
| `LLM_FAST_MODEL` | Model for quick tasks |
| `LLM_STRONG_MODEL` | Model for complex analysis |
| `LLM_LITE_MODEL` | Model for cheap/bulk tasks |

## Railway Deployment

Five services in a single Railway project:

| Service | Source | Port |
|---------|--------|------|
| `arcflare-backend` | `backend/` Dockerfile | `$PORT` (Railway-assigned) |
| `arcflare-worker` | `backend/` Dockerfile (different start command) | none |
| `arcflare-frontend` | `frontend/` Dockerfile | `$PORT` (Railway-assigned) |
| PostgreSQL | Railway managed | 5432 |
| Redis | Railway managed | 6379 |

### Step 1 -- Create the project

1. Go to [railway.com](https://railway.com) > **New Project** > **Deploy from GitHub repo**
2. Select the `willcrowley-spec/arcflare` repository

### Step 2 -- Add PostgreSQL

1. In the project canvas: **+ New** > **Database** > **Add PostgreSQL**
2. Enable extensions:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   CREATE EXTENSION IF NOT EXISTS pgcrypto;
   ```

### Step 3 -- Add Redis

1. **+ New** > **Database** > **Add Redis**

### Step 4 -- Configure the Backend service

1. **Settings**:
   - **Root Directory**: `backend`
   - **Builder**: Dockerfile
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Health Check Path**: `/health`
2. **Variables**: `DATABASE_URL`, `REDIS_URL` (use Railway refs), plus all API keys and Clerk/Salesforce config.
3. Generate a domain.

### Step 5 -- Configure the Celery Worker service

1. Same repo, **Root Directory**: `backend`
2. **Start Command**: `celery -A app.workers.celery_app worker --loglevel=info`
3. Same variables as backend. No domain needed.

### Step 6 -- Configure the Frontend service

1. Same repo, **Root Directory**: `frontend`
2. **Start Command**: `serve -s dist -l $PORT`
3. Variables: `VITE_CLERK_PUBLISHABLE_KEY`, `VITE_API_URL` (Vite vars are baked at build time -- set before first deploy)
4. Generate a domain.

### Step 7 -- Run migrations

```bash
alembic upgrade head
```

### Step 8 -- Verify

- `https://<backend>/health` > `{"status":"ok"}`
- `https://<backend>/docs` > Swagger UI
- `https://<frontend>` > Arcflare UI

## API Documentation

Once the backend is running, interactive API docs are available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
