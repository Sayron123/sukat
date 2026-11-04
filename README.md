# Sukat

Sukat is a multi-tenant SaaS for Philippine hardware stores: products, inventory, sales, and insights in one app that works on phones (PWA).

This repo is at **Phase 0**: project setup only. No auth, no tables yet.

## Folder structure

```
sukat/
├── api/                  # Backend: FastAPI + SQLAlchemy + Alembic (Python, uv)
│   ├── app/
│   │   ├── main.py       # FastAPI app entry point
│   │   ├── core/         # config, db session, health route
│   │   ├── auth/  stores/  products/  inventory/
│   │   └── sales/  insights/  ai/      # feature folders (empty for now)
│   ├── alembic/          # database migrations
│   ├── tests/            # pytest tests
│   ├── pyproject.toml    # Python deps
│   └── .env.example
├── web/                  # Frontend: Next.js 16 + TypeScript + Tailwind (PWA)
│   ├── src/app/
│   └── .env.example
├── docs/phase-0.md       # What and why for each Phase 0 step
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
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0
```

API runs at http://localhost:8000. Check http://localhost:8000/health.

**3. Start the web app** (new terminal)

```powershell
cd web
copy .env.example .env.local
npm install
npm run dev
```

Open http://localhost:3000. You should see **API connected**.

## Useful commands

```powershell
cd api
uv run pytest          # run tests
uv run ruff check .    # lint
uv run alembic upgrade head   # apply migrations
```

```powershell
docker compose down    # stop the database (data is kept)
```
