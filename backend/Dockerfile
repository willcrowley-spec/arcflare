# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt \
    && python -m spacy download en_core_web_lg \
    && python -m spacy download en_core_web_sm

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    ARCBRAIN_CODEGRAPH_ENABLED=true \
    ARCBRAIN_CODEGRAPH_PROVIDER=codebase_memory \
    ARCBRAIN_CODEGRAPH_BINARY=/usr/local/bin/codebase-memory-mcp \
    ARCBRAIN_CODEGRAPH_REPOS=arcflare-backend=/app \
    ARCBRAIN_CODEGRAPH_MODE=fast

WORKDIR /app

ARG CODEBASE_MEMORY_MCP_VERSION=0.6.1
ARG CODEBASE_MEMORY_MCP_SHA256=a24c04fd1fd61b08158e011685cf08d860e3594e4ce057ffda57d1cc2f4afdd1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL "https://github.com/DeusData/codebase-memory-mcp/releases/download/v${CODEBASE_MEMORY_MCP_VERSION}/codebase-memory-mcp-linux-amd64.tar.gz" -o /tmp/codebase-memory-mcp.tar.gz \
    && echo "${CODEBASE_MEMORY_MCP_SHA256}  /tmp/codebase-memory-mcp.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/codebase-memory-mcp.tar.gz -C /usr/local/bin codebase-memory-mcp \
    && chmod +x /usr/local/bin/codebase-memory-mcp \
    && rm /tmp/codebase-memory-mcp.tar.gz \
    && useradd --create-home --uid 1000 --shell /usr/sbin/nologin arcflare

COPY --from=builder /opt/venv /opt/venv

COPY app ./app
COPY alembic.ini .
COPY alembic ./alembic

USER arcflare

EXPOSE 8000

CMD sh -c 'if [ "$WORKER_MODE" = "true" ]; then celery -A app.workers.celery_app worker --loglevel=info; else alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}; fi'
