# Sukat API image.
#   docker build -t sukat-api ./api
#   docker run --env-file api/.env.production -p 8000:8000 sukat-api
# On start it runs "alembic upgrade head", then uvicorn with WEB_CONCURRENCY workers.

# ---------- build: install dependencies with uv ----------
FROM python:3.12-slim AS build
RUN pip install --no-cache-dir uv==0.11.32
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
# Dependencies first (cached until pyproject.toml / uv.lock change). No dev tools.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini docker-entrypoint.sh ./

# ---------- run: no uv, no build tools, non-root user ----------
FROM python:3.12-slim
RUN groupadd --system --gid 10001 sukat \
    && useradd --system --uid 10001 --gid sukat --no-create-home --shell /usr/sbin/nologin sukat
WORKDIR /app
COPY --from=build --chown=root:root /app /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    WEB_CONCURRENCY=2 \
    FORWARDED_ALLOW_IPS=127.0.0.1 \
    RUN_MIGRATIONS=true
USER sukat
EXPOSE 8000
# Healthy only when the API answers and can reach Postgres (/health returns 503 if not).
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health', timeout=4)" || exit 1
ENTRYPOINT ["/app/docker-entrypoint.sh"]
