# syntax=docker/dockerfile:1
# ROOTMEM HTTP server image (ADR 0040). NOTE: this file could not be built on
# the development machine (Docker Desktop is broken there); CI builds it and
# smoke-tests /healthz. See docs/operations.md.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# The package itself, plus the two extras `scripts/migrate.py` needs at run
# time (they are dev-only dependencies of the project, not runtime ones).
COPY pyproject.toml ./
COPY src ./src
RUN pip install . yoyo-migrations psycopg2-binary

# Migrations and the runner live beside the app, not inside site-packages.
COPY scripts/migrate.py ./scripts/migrate.py
COPY src/rootmem/storage/postgres/migrations ./migrations

RUN useradd --system --uid 10001 --no-create-home rootmem
USER rootmem

# Defaults for a container: serve HTTP, listen on all interfaces (the network
# boundary is the reverse proxy in front), and find the migrations.
ENV ROOTMEM_TRANSPORT=http \
    ROOTMEM_HTTP_HOST=0.0.0.0 \
    ROOTMEM_HTTP_PORT=8765 \
    ROOTMEM_HTTP_ALLOW_NON_LOOPBACK=true \
    ROOTMEM_MIGRATIONS_DIR=/app/migrations

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/healthz', timeout=4).status == 200 else 1)"

CMD ["python", "-m", "rootmem.integration.mcp.server"]
