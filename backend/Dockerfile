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
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 --shell /usr/sbin/nologin arcflare

COPY --from=builder /opt/venv /opt/venv

COPY app ./app
COPY alembic.ini .
COPY alembic ./alembic

USER arcflare

EXPOSE 8000

CMD sh -c 'if [ "$WORKER_MODE" = "true" ]; then celery -A app.workers.celery_app worker --loglevel=info; else alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}; fi'
