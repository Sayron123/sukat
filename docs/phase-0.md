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
- **pytest** (dev) — runs tests. **httpx2** (dev) — needed by FastAPI's test client (Starlette replaced `httpx` with `httpx2`). **ruff** (dev) — lints and formats code.

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

## Step 3 — Health route

**What**
- `api/app/core/health.py` — `GET /health`. Runs `SELECT 1` on Postgres.
  - DB reachable → `200 {"status":"ok","db":"ok"}`
  - DB down → `503 {"status":"ok","db":"error"}` (the API itself is up, the database is not)
- `api/app/main.py` — adds the health route and **CORS** middleware.
- `api/tests/test_health.py` — tests the route without a real database.

**Tools / ideas**
- **Dependency injection** — the route asks for `get_db`. In tests we swap it with a fake (`app.dependency_overrides`), so tests run fast and need no Postgres.
- **CORS** — browsers block a web page on `localhost:3000` from calling an API on `localhost:8000` unless the API says it's allowed. `CORS_ORIGINS` in `.env` lists the allowed web origins.
- **TestClient** (uses httpx2) — sends fake HTTP requests to the app inside the test.

**Why**
- A health route is the simplest way to check "is the API up, and can it reach the DB?" — useful for the web app, for Docker, and later for hosting.
- 503 means "service unavailable", so monitoring tools can tell something is wrong.

Run tests: `cd api && uv run pytest`

## Step 4 — Frontend (`web/`)

**What**
- Created with `create-next-app`: Next.js 16, TypeScript (strict), Tailwind CSS, App Router, `src/` folder.
- `src/app/layout.tsx` — wraps every page. Loads the **Inter** font and sets the theme color.
- `src/app/page.tsx` — the home page (a card with the API status).
- `src/app/api-status.tsx` — a client component. In the browser it calls `NEXT_PUBLIC_API_URL + /health` and shows **"API connected"** or **"API not reachable"**.
- `src/app/manifest.ts` — the PWA manifest (name "Sukat", theme color `#C2410C`, white background). Next.js serves it at `/manifest.webmanifest`.
- `public/icon-192.png`, `public/icon-512.png`, `public/apple-touch-icon.png` — placeholder app icons. Replace with real ones later.
- `src/app/globals.css` — the **design tokens** in Tailwind's `@theme` block.
- `.env.example` — sample `NEXT_PUBLIC_API_URL`. Copy to `.env.local`.

**Design tokens → Tailwind classes**

| Token | Value | Example class |
|---|---|---|
| background | `#FFFFFF` | `bg-background` |
| surface | `#F5F5F4` | `bg-surface` |
| border | `#E7E5E4` | `border-border` |
| text | `#1C1917` | `text-text` |
| muted | `#57534E` | `text-muted` |
| accent | `#C2410C` | `bg-accent` |
| accent-pressed | `#9A3412` | `active:bg-accent-pressed` |
| red / green / amber | `#DC2626` / `#16A34A` / `#D97706` | `text-red`, `bg-green`, `bg-amber` |
| radius button/input | 12px | `rounded-button` |
| radius card | 16px | `rounded-card` |

**Tools / ideas**
- **Next.js** — React framework with routing, building, and serving built in.
- **App Router** — each folder in `src/app` is a route; `page.tsx` is the page.
- **TypeScript strict** — catches type mistakes before the code runs.
- **Tailwind CSS v4** — style with small classes (`p-4`, `bg-surface`). Tokens are defined in CSS with `@theme` (v4 has no `tailwind.config.js` by default).
- **PWA (Progressive Web App)** — the manifest lets users "Add to Home Screen" on phones, so Sukat opens like an app.
- **`NEXT_PUBLIC_` env vars** — only variables with this prefix are sent to the browser. Never put secrets in them.

**Why**
- Tokens in one place keep colors and corners consistent and easy to change.
- The health check proves the full chain works: browser → API → database.

## Step 5 — Docs

**What**
- `.gitignore` (root) — tells git which files to never commit: Python caches and virtual env, `node_modules`, Next.js build output, and all `.env` files (but keeps `.env.example`).
- `README.md` — what Sukat is, the folder layout, and how to run it on Windows.
- `docs/phase-0.md` — this file.

**Why**
- `.env` files hold passwords and keys. Ignoring them prevents leaking secrets to GitHub.
- `.env.example` files are committed so others know which settings they need.
- A good README lets anyone (including future you) start the project in minutes.
