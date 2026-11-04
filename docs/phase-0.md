# Phase 0 — What and why

Short notes on every tool and file added in Phase 0.

## Step 1 — Backend scaffold (`api/`)

**What**
- `pyproject.toml` — the project file. Lists the Python version and the packages the API needs.
- `uv.lock` — exact versions of every package, so everyone installs the same thing.
- `.python-version` — tells uv which Python to use (3.12+).
- `app/main.py` — creates the FastAPI app. This is the entry point uvicorn runs.
- `app/core/config.py` — reads settings (`DATABASE_URL`, `CORS_ORIGINS`) from `api/.env`.
- `app/core/db.py` — creates the database engine and a `get_db` function that gives each request its own DB session.
- `app/<feature>/` — empty folders for each part of the app: `core`, `auth`, `stores`, `products`, `inventory`, `sales`, `insights`, `ai`.
- `.env.example` — sample settings. Copy to `.env` and edit. `.env` is never committed.

**Tools**
- **uv** — installs Python and packages, and runs commands inside the project's virtual environment (`uv run ...`). Fast replacement for pip + venv.
- **FastAPI** — the web framework. You write Python functions, it turns them into HTTP endpoints.
- **uvicorn** — the server that runs the FastAPI app.
- **SQLAlchemy 2.x** — talks to the database from Python.
- **psycopg** — the PostgreSQL driver SQLAlchemy uses under the hood.
- **Alembic** — manages database changes (migrations) over time.
- **pydantic-settings** — loads and validates settings from environment variables / `.env`.
- **pytest** (dev) — runs tests. **httpx** (dev) — needed by FastAPI's test client. **ruff** (dev) — lints and formats code.

**Why**
- Feature folders keep code for one area (e.g. sales) together, so the project stays easy to navigate as it grows.
- Settings live in `.env` so secrets and machine-specific values stay out of the code.

## Step 2 — Database

**What**
- `docker-compose.yml` (root) — starts PostgreSQL 16 in Docker.
  - **Named volume** `sukat_pgdata` — keeps your data when the container is stopped or recreated.
  - **Healthcheck** — runs `pg_isready` so Docker knows when the database is actually ready.
  - **Port 5432** — so the API on your machine can reach the database at `localhost:5432`.
- `api/alembic.ini` — Alembic's config file (logging, script location).
- `api/alembic/env.py` — runs migrations. It reads `DATABASE_URL` from our settings, so the app and migrations always use the same database.
- `api/alembic/versions/` — where migration files will go. Empty for now (no tables yet).

**Tools**
- **Docker / Docker Compose** — runs Postgres in a container, so you don't have to install it on Windows directly.
- **PostgreSQL** — the database.
- **Alembic** — tracks database changes as numbered migration files you can apply (`uv run alembic upgrade head`) or roll back.

**Why**
- One source of truth for the DB URL (`api/.env`) avoids "works in the app but not in migrations" bugs.
- Migrations make DB changes repeatable on every machine and in production.
