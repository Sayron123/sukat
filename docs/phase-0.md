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
