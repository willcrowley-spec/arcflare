---
name: arcflare-debugging
description: >-
  Debug and operate the Arcflare platform on Railway. Covers log retrieval,
  service topology, common failure patterns, Celery worker diagnostics,
  database migrations, and Salesforce API errors. Use when the user reports
  a production error, asks to check logs, mentions Railway, or needs to
  troubleshoot metadata sync, vectorization, or discovery pipeline failures.
---

# Arcflare Debugging & Operations

## Railway Project Topology

Project: **arcflare** | Environment: **production**

| Service | Railway ID | Role |
|---------|-----------|------|
| `arcflare-backend` | `57464ead-...` | FastAPI app (uvicorn on port 8000) |
| `arcflare-worker` | `edcc6b0a-...` | Celery worker (prefork, 48 concurrency) |
| `arcflare-frontend` | `b8d4c23e-...` | React SPA |
| `Postgres` | `32428df8-...` | Primary PostgreSQL (linked in CLI config) |
| `Postgres-XWtI` | `75810583-...` | Secondary/staging PostgreSQL |
| `Redis` | `2278eeb6-...` | Celery broker + result backend + progress cache |

**IMPORTANT**: The Railway CLI is linked to the Postgres service by default. You must always pass `--service <name>` when pulling logs for backend/worker/frontend.

## Pulling Logs

```bash
# Worker logs (metadata sync, vectorization, discovery)
railway logs --lines 200 --since 30m --service arcflare-worker

# Backend logs (API requests, OAuth callbacks, migrations)
railway logs --lines 200 --since 30m --service arcflare-backend

# Error-only (works for Postgres, not worker/backend)
railway logs --lines 200 --filter "@level:error" --service arcflare-worker

# Build logs for a deployment
railway logs --build --latest --service arcflare-backend

# HTTP request logs
railway logs --http --lines 50 --service arcflare-backend
```

Key flags: `--lines N` (historical, no streaming), `--since 30m/2h/1d`, `--latest` (include failed deploys).

## Pipeline Architecture

Celery tasks (registered in `app/workers/`):

| Task name | File | What it does |
|-----------|------|-------------|
| `metadata.sync_metadata` | `metadata_sync.py` | Full metadata pull → parse → graph → classify → vectorize |
| `documents.vectorize_document` | - | Document chunk + embed |
| `processes.discover` | - | LLM-based process discovery pipeline |
| `prompts.run_prompt_optimization` | - | Prompt tuning |
| `telemetry.poll_telemetry` | - | Salesforce usage telemetry |

### Metadata Sync Pipeline Phases

Order within `sync_metadata_task._pipeline()`:

1. **Resolve org_id** — DB lookup on `PlatformConnection`
2. **Set status** → `syncing`
3. **`sync_metadata()`** — the big one:
   - `check_mdapi_access()` — pre-flight MDAPI permission check
   - `pull_object_describes()` — REST describe for all objects
   - `pull_usage_data()` — record counts + velocity
   - `_mdapi_retrieve_files()` — MDAPI `retrieve()` via zeep
   - `_query_flow_definition_versions()` — Tooling API FlowDefinitionView
   - `_collect_mdapi_zip_results()` — parse XML/Apex from zip
   - Delete old rows → insert new rows
   - `pull_custom_metadata_types()` — CMDT records
4. **`build_dependency_graph()`** — edge extraction + bulk insert
5. **`detect_metadata_communities()`** — Leiden clustering
6. **`run_classification()`** — object/field classification
7. **`vectorize_org_metadata()`** — text generation + embeddings
8. **Set status** → `connected`

## Common Failure Patterns

### 1. Event Loop Mismatch
```
RuntimeError: got Future attached to a different loop
```
**Cause**: Multiple `asyncio.run()` calls sharing a module-level async engine.
**Fix**: The worker creates a fresh `create_async_engine()` inside `_pipeline()` and disposes it in `finally`. If this recurs, someone reintroduced a shared engine.

### 2. MDAPI Insufficient Access
```
MDAPIInsufficientAccessError: Metadata API retrieve failed with INSUFFICIENT_ACCESS
```
**Cause**: Connected SF user lacks "Modify All Data" permission.
**Fix**: Re-auth with an admin user. `check_mdapi_access()` runs at sync start and fails fast.

### 3. FlowDefinitionView Not Supported
```
SalesforceMalformedRequest: sObject type 'FlowDefinitionView' is not supported
```
**Cause**: API version too old. `FlowDefinitionView` requires v43.0+.
**Fix**: `get_sf_client()` dynamically queries `GET /services/data/` for the org's latest version. If this error appears, the version resolution failed — check `_get_latest_api_version()`.

### 4. Salesforce API Version Stale
The SF client resolves the org's latest API version at connect time via `_get_latest_api_version()`. No hardcoded version. If `simple_salesforce` is upgraded and changes its default, ours still overrides it.

### 5. LIMIT_EXCEEDED on MDAPI Retrieve
```
MDAPIRetrieveError: LIMIT_EXCEEDED
```
**Cause**: Zip too large for single retrieve. The code falls back to per-type retrieves automatically (this is in `mdapi_retrieve.py`).

### 6. Celery Unpickleable Exception
```
UnpickleableExceptionWrapper
```
**Cause**: `simple_salesforce` exceptions can't be pickled by Celery. The task still fails correctly — this is just Celery's serialization wrapper. Read the original traceback above it for the real error.

### 7. Database Migration Failure
Check backend startup logs:
```bash
railway logs --lines 50 --service arcflare-backend --filter "alembic"
```
Migrations run on backend startup. Look for `Running upgrade X -> Y`.

### 8. PostgreSQL SSL EOF / Connection Reset
```
SSL error: unexpected eof while reading
could not receive data from client: Connection reset by peer
```
**Normal** — Railway recycles connections during deploys. Not an error unless it cascades into app failures.

## Salesforce Client Details

- **Client creation**: `get_sf_client()` in `app/services/salesforce/metadata.py`
- **API version**: Dynamically resolved per-org via `_get_latest_api_version()`
- **MDAPI workaround**: `simple_salesforce.mdapi.retrieve()` is broken (PR #623 never merged). We use `zeep` directly via `mdapi_retrieve.py`.
- **OAuth**: Tokens stored encrypted in `PlatformConnection.oauth_tokens_encrypted`. Refresh via `app/services/salesforce/oauth.py`.

## Key Connection ID

The current dev Salesforce connection: `4f3d4145-3512-4da5-b572-2dfdbcc1d952` (org: `epms.my.salesforce.com`)

## Database Access

```bash
# Direct SQL via Railway CLI
railway connect Postgres

# Check migration state
railway logs --lines 20 --service arcflare-backend --filter "alembic"
```

## Quick Triage Checklist

1. **Which service?** Sync/vectorize/discover errors → `arcflare-worker`. API/auth errors → `arcflare-backend`.
2. **Pull logs**: `railway logs --lines 200 --since 30m --service <name>`
3. **Read the traceback bottom-up** — the last `File "..."` line before the exception is where it broke.
4. **Check if it's a known pattern** above.
5. **If DB-related**: Check if migration ran (`alembic` in backend logs). Check if Postgres is healthy.
6. **If SF-related**: Check API version resolved correctly. Check OAuth tokens aren't expired.
7. **Fix, commit, push** — Railway auto-deploys from `master`. Build takes ~2 min.
