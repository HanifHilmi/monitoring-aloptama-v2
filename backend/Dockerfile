# ---------- Stage 1: Builder ----------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------- Stage 2: Runtime ----------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/install/bin:${PATH}" \
    PYTHONPATH="/code:${PYTHONPATH}"

RUN groupadd -r app && useradd -r -g app app \
    && apt-get update \
    && apt-get install -y --no-install-recommends curl procps netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

WORKDIR /code
COPY --chown=app:app app ./app
COPY --chown=app:app migrations ./migrations
COPY --chown=app:app docker ./docker

USER app

EXPOSE 8000

# Lightweight liveness probe — no DB dependency, so the container stays
# healthy during first-boot backfill (which runs in the worker container).
HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost:8000/health >/dev/null || exit 1

# Single worker: the ingestion worker + backfill run in the dedicated
# worker container; duplicate API workers would duplicate loop tasks.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers"]