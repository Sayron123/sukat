# Phase 1 — What and why

Phase 1 adds accounts, stores, staff, and roles. Every request knows **who** is calling and **which store** they are in.

## Step 0 — Fixes to Phase 0

**What**
- Replaced the `httpx` dev package with `httpx2`. Starlette (used by FastAPI) now wants `httpx2` for its test client and warned that `httpx` support is going away.
- Added `connect_timeout=5` to the database engine. Before, `/health` could hang for a long time if the database host did not answer. Now it returns `503` within about 5 seconds.

## Step 1 — Database tables (migration)

**What**
- `api/app/core/base.py` — the shared `Base` class for all models, plus helpers for UUID ids and timestamps.
- `api/app/auth/models.py` — `users` table: email, password hash, full name.
- `api/app/stores/models.py` — `stores`, `store_members`, `invites` tables, and the `Role` list (`manager`, `secretary`, `member`).
- `api/app/models.py` — imports every model so Alembic can see all tables.
- `api/alembic/versions/0001_auth_tables.py` — the migration that creates the tables.

| Table | Purpose |
|---|---|
| `stores` | One row per hardware store (one tenant). |
| `users` | One row per person. Email is unique and always lowercase. |
| `store_members` | Links a user to a store with a `role` and an `active` flag. One row per (store, user). |
| `invites` | A pending invitation: `email`, `role`, `token_hash`, `expires_at`, `accepted_at`. |

**Ideas**
- **UUID primary keys** — random ids like `3f1c…`. They can't be guessed or counted (unlike 1, 2, 3), which matters when ids appear in URLs.
- **TIMESTAMPTZ in UTC** — every timestamp stores an exact moment. The app connects with `timezone=UTC`, so times come back in UTC. Convert to Philippine time (UTC+8) only when showing it.
- **Check constraints** — the database itself refuses a bad role or an uppercase email, even if the code has a bug.
- **Invite token hash** — only a SHA-256 hash of the invite token is stored, not the token itself. If the database leaks, the invite links still can't be used. (This is the `token` field from the plan, stored safely.)
- **Migrations** — run `uv run alembic upgrade head` to create the tables. `uv run alembic downgrade base` undoes them.

## Step 2 — Signup and login

**What**
- `api/app/auth/security.py` — hashes passwords with **argon2** (via `pwdlib`) and creates/checks **JWT** tokens.
- `api/app/auth/router.py`:
  - `POST /auth/signup` — creates the store, the user, and a manager membership.
  - `POST /auth/login` — checks email and password, returns an access token.
  - `GET /auth/me` — who am I, which store, which role.
- `api/app/auth/deps.py` — `get_current_member`: reads the token and loads the caller's active membership.
- `api/app/core/config.py` — new settings: `JWT_SECRET`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `INVITE_EXPIRE_HOURS`, `APP_ENV`.

**Ideas**
- **One transaction** — signup adds three rows and saves them with a single `commit()`. If anything fails, none of them are saved. There is a test that proves it.
- **argon2** — a slow-on-purpose password hash. Even if someone steals the database, guessing passwords is very expensive. Plain passwords are never stored.
- **JWT access token** — a signed string holding the user id and the `store_id`. The server can check the signature, so nobody can change the `store_id` inside it.
- **store_id comes from the token, never from the request body.** Every query uses `current.store_id`. A user can't send `"store_id": "<other store>"` to reach another store.
- **Membership is re-checked on every request.** A deactivated staff member's old token stops working right away.
- **Same error for wrong password and unknown email**, so attackers can't use login to find out which emails have accounts.
- **Production guard (fails closed)** — `APP_ENV` defaults to `production`. Unless `APP_ENV` is exactly `development`, the API refuses to start with the public default `JWT_SECRET` or one shorter than 32 characters. A server with no `APP_ENV`, or a typo like `prod`, is therefore still protected. Your own PC uses `APP_ENV=development` from `.env.example`; tests set it themselves.

## Step 3 — Role checks

**What**
- `require_role(...)` in `api/app/auth/deps.py`. Use it on a route to allow only certain roles:

```python
Manager = Annotated[CurrentMember, Depends(require_role("manager"))]

@router.post("/staff/invites")
def invite_staff(body: InviteIn, current: Manager, db: DbSession): ...
```

**Ideas**
- A wrong role gets **403 Forbidden** ("you are logged in, but not allowed").
- No token, or a bad token, gets **401 Unauthorized** ("log in first").
- A typo like `require_role("manger")` fails when the app starts, not silently later.

## Step 4 — Staff

**What** (`api/app/stores/router.py`)

| Endpoint | Who | What it does |
|---|---|---|
| `POST /staff/invites` | manager | Creates an invite and returns a one-time `token`. |
| `POST /staff/invites/accept` | anyone with the token | Creates the account (or uses the existing one) and joins the store. Returns an access token. |
| `GET /staff` | manager, secretary | Lists everyone in your store. |
| `GET /staff/{member_id}` | manager, secretary | One staff member. |
| `POST /staff/{member_id}/deactivate` | manager | Turns off a staff member's access. |

**Ideas**
- Invites expire after `INVITE_EXPIRE_HOURS` (default 72) and work only once.
- Sending a new invite to the same email cancels the older one.
- If the invitee already has an account (e.g. from another store), they confirm with their own password.
- Inviting a deactivated person again turns them back on.
- A manager can't deactivate themselves, so a store can't lock itself out by accident.
- Email sending is not built yet. For now, the manager shares the token.

## Step 5 — Tenant isolation and role tests

**What**
- `api/tests/test_isolation.py` — builds Store A and Store B, then checks:
  - Store A's manager gets **404** for Store B's staff (read and deactivate), and Store B's data is unchanged.
  - Store A's staff list shows only Store A.
  - A `store_id` in the request body is ignored.
  - A token for a store the user doesn't belong to is refused.
  - A member can't invite, list, or deactivate. A secretary can list but can't invite or deactivate.
- `api/tests/conftest.py` — test setup. Tests run against a real Postgres database `sukat_test` (created automatically), migrated with Alembic, and wiped before each test.

**Ideas**
- **Multi-tenant** means many stores share one database. The most important rule: **one store must never see another store's data.** These tests guard that rule.
- **404, not 403**, for another store's data. 403 would confirm "this exists, you just can't touch it". 404 reveals nothing.
- Tests use a real database because isolation bugs live in SQL queries. A fake database would hide them.

Run tests (Postgres must be running): `cd api && uv run pytest`

## Step 6 — Web pages

**What**
- `/signup`, `/login` — forms (`web/src/components/auth-form.tsx`).
- `/staff` — server page that shows your store and the staff list (`web/src/app/staff/page.tsx`).
- `web/src/app/api/auth/{signup,login,logout}/route.ts` — **route handlers** on the Next.js server.
- `web/src/lib/server/` — server-only helpers: calling the API, reading the cookie, setting the cookie.
- `web/src/components/ui.tsx` — `Card`, `Button`, `Field` using the design tokens (`rounded-card`, `rounded-button`, `bg-accent`, …).

**How the token is stored safely**
1. The form sends email and password to `/api/auth/login` (our Next.js server, same site).
2. That route handler calls the FastAPI `/auth/login`.
3. It puts the token in a cookie that is:
   - **httpOnly** — JavaScript in the page can't read it, so a script injection (XSS) can't steal it.
   - **SameSite=Lax** — the browser doesn't send it with POSTs from other websites (CSRF protection).
   - **Secure** in production — sent only over HTTPS.
4. The token is never returned to the browser code. The `/staff` page reads the cookie on the server and calls the API with it.

**Other details**
- Route handlers reject requests from other origins.
- Forms use `method="post"` and the button stays disabled until the page is ready. Without this, a fast click could put the password in the URL.
- `API_URL` (server) and `NEXT_PUBLIC_API_URL` (browser) are in `web/.env.example`.
- Invite and deactivate are API-only for now. They have no web screens yet.

## Step 8 — Fixes from code review

### Limit failed logins (rate limiting)

**What**
- `api/app/auth/rate_limit.py` and a new `auth_failures` table (migration `0002_auth_failures.py`).
- Each failed login or invite-accept saves one row per key: `email:<email>` and `ip:<address>`.
- If a key has too many failures in the last 15 minutes, the API answers **429 Too Many Requests**, even if the password is right. The `Retry-After` header says how many seconds to wait.
- A correct password resets the email's counter.

| Setting (`api/.env`) | Default | Meaning |
|---|---|---|
| `AUTH_FAILURE_WINDOW_MINUTES` | 15 | How far back to count |
| `AUTH_MAX_FAILURES_PER_EMAIL` | 10 | Per account |
| `AUTH_MAX_FAILURES_PER_IP` | 30 | Per network address |

**Why**
- Without a limit, an attacker can try passwords forever.
- **Stored in Postgres, not memory**, so limits survive restarts and work with several API servers.
- **Unknown emails are counted too**, so a 429 does not reveal which emails have accounts.
- **Email limit is the main protection.** The IP can be faked unless the hosting proxy sets it correctly. The email can't be faked.
- Trade-off: someone can block a person's login for 15 minutes by typing wrong passwords for their email. That is the usual price of this protection.

**Deploying:** the API only trusts `X-Forwarded-For` from addresses in `FORWARDED_ALLOW_IPS` (uvicorn setting, default `127.0.0.1`). If Next.js runs on a different machine than the API, set `FORWARDED_ALLOW_IPS` to the Next.js server's address. Otherwise every user looks like the same IP.

### Staff page when the API is down

**What:** `/staff` shows "API not reachable" instead of an error screen.

**Why:** `fetch()` doesn't return an error status when the server is off. It **throws**. The page now catches that.

### Same-origin check behind HTTPS

**What:** `isSameOrigin` (`web/src/lib/server/auth-route.ts`) compares only the **host** of the browser's `Origin` with the request's `x-forwarded-host` (or `host`).

**Why:** on a real host, HTTPS usually ends at a proxy. The browser says `https://sukat.ph` but Next.js sees `http://`. Comparing the full origin blocked every login. Comparing the host is the same check Next.js uses for its own Server Actions.
