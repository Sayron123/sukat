# Sukat

Sukat is a multi-tenant SaaS for Philippine hardware stores: products, inventory, sales, and insights in one app that works on phones (PWA).

This repo is at **Phase 1**: stores, accounts, staff invites, and roles (manager, secretary, member).
See `docs/phase-0.md` and `docs/phase-1.md` for what each part does and why.

## Folder structure

```
sukat/
├── api/                  # Backend: FastAPI + SQLAlchemy + Alembic (Python, uv)
│   ├── app/
│   │   ├── main.py       # FastAPI app entry point
│   │   ├── core/         # config, db, base model, errors, storage, /health
│   │   ├── auth/         # accounts, login, JWT, role checks
│   │   ├── stores/       # staff and invites
│   │   ├── products/     # products, aliases, units, starter catalog
│   │   ├── inventory/    # photo upload, scans, transactions, stock
│   │   └── ai/           # AI list reader
│   │   (each feature: models.py, schemas.py, service.py, router.py)
│   ├── alembic/          # database migrations
│   ├── tests/            # pytest tests
│   ├── pyproject.toml    # Python deps
│   └── .env.example
├── web/                  # Frontend: Next.js 16 + TypeScript + Tailwind (PWA)
│   ├── src/app/
│   └── .env.example
├── docs/                 # api-structure.md + what and why for each phase
└── docker-compose.yml    # PostgreSQL 16
```

## Run locally (Windows)

Install first: [Docker Desktop](https://www.docker.com/products/docker-desktop/), [uv](https://docs.astral.sh/uv/getting-started/installation/), and [Node.js](https://nodejs.org/) 20.9+.

**1. Start the database** (from the repo root)

```powershell
docker compose up -d
```

**2. Start the API** (new terminal)

```powershell
cd api
copy .env.example .env
# .env must keep APP_ENV=development. Without it the API acts as production and
# refuses the public JWT_SECRET. Never use .env.example values on a server.
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 0.0.0.0
```

API runs at http://localhost:8000 (endpoints under `/v1`; list at http://localhost:8000/docs). Check http://localhost:8000/health.

**3. Start the web app** (new terminal)

```powershell
cd web
copy .env.example .env.local
npm install
npm run dev
```

Open http://localhost:3000. You should see **API connected**. Click **Create store** to sign up.

## Useful commands

```powershell
cd api
uv run pytest          # run tests (needs the database running; uses a sukat_test DB)
uv run ruff check .    # lint
uv run pyright         # type check
uv run alembic upgrade head   # apply migrations
```

```powershell
docker compose down    # stop the database (data is kept)
```
