# API structure

How the backend (`api/`) is organized, and where new code goes.

## Layout

```
api/app/
├── main.py          # app setup: CORS, error handler, mounts every feature under /v1
├── models.py        # imports every table (for Alembic)
├── core/            # shared: settings, DB session, base model, errors, storage, /health
├── auth/            # accounts, login, JWT, role checks, login rate limit
├── stores/          # staff and invites
├── products/        # products, aliases, unit conversions, starter catalog
├── inventory/       # photo upload, scans, transactions, stock movements
└── ai/              # AI list reader: interface, provider choice, Claude implementation
```

Every feature folder has the same files:

| File | Holds | Must not |
|---|---|---|
| `models.py` | Database tables (SQLAlchemy) | contain business rules |
| `schemas.py` | Request/response shapes (Pydantic) | touch the database |
| `service.py` | Business rules and queries. Functions take `db` and `store_id` and raise `AppError`s | import FastAPI or read the HTTP request |
| `router.py` | HTTP endpoints: role check, read input, call the service, shape the response | contain business rules |

`inventory/` is bigger, so it has two services: `scan_service.py` (photos, AI reading, review lines) and `stock_service.py` (saving stock changes).

## A request, step by step

```
Browser -> Next.js proxy (adds the token from the httpOnly cookie)
        -> FastAPI /v1/... -> auth deps (valid token? still an active member? right role?)
        -> router.py -> service.py -> database
```

`store_id` always comes from the verified token (`current.store_id`), and every service function filters by it. Another store's data is reported as "not found".

## Errors

Services raise errors from `app/core/errors.py`: `BadRequest` 400, `Unauthorized` 401, `Forbidden` 403, `NotFound` 404, `Conflict` 409, `Invalid` 422, `TooManyRequests` 429. One handler in `main.py` turns them into `{"detail": "..."}` with that status. Business code never imports FastAPI to report an error.

## Endpoints

All paths start with `/v1`, except `GET /health`. The live list with request/response shapes is at http://localhost:8000/docs.

| Feature | Endpoints |
|---|---|
| auth | `POST /auth/signup`, `POST /auth/login`, `GET /auth/me` |
| stores (staff) | `POST /staff/invites`, `POST /staff/invites/accept`, `GET /staff`, `GET /staff/{id}`, `POST /staff/{id}/deactivate` |
| products | `GET/POST /products`, `GET /products/catalog`, `POST /products/import`, `GET/PATCH /products/{id}`, `POST /products/{id}/archive`, `POST /products/{id}/unarchive` |
| inventory | `POST /scans/upload-url`, `PUT /uploads/local/{key}` (dev only), `POST /scans` (stock_in or sale), `GET /scans/{id}`, `POST /scans/{id}/retry`, `GET/POST /transactions`, `GET /transactions/{id}`, `POST /transactions/{id}/void` |

## Adding something new

1. **A new endpoint in an existing feature:** add the rule to `service.py` (with a docstring), add the endpoint to `router.py`, add shapes to `schemas.py`, add tests.
2. **A new feature** (e.g. `sales/`): create the four files above, then mount the router in `main.py`.
3. **A table change:** edit `models.py`, run `uv run alembic revision --autogenerate -m "..."`, read the generated file, then run `uv run alembic upgrade head` and `uv run alembic check`.
4. **A new AI provider:** implement `VisionReader` (`app/ai/base.py`) in its own module, and select it in `app/ai/provider.py`.

## Checks before pushing

```bash
cd api
uv run ruff check . && uv run ruff format --check .
uv run pyright
uv run pytest
```
