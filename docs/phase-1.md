# Phase 1 — What and why

Phase 1 adds accounts, stores, staff, and roles. Every request knows **who** is calling and **which store** they are in.

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
- `api/app/core/config.py` — new settings: `JWT_SECRET`, `ACCESS_TOKEN_EXPIRE_DAYS`, `INVITE_EXPIRE_HOURS`, `APP_ENV`.

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
| `POST /staff/invites` | manager, secretary | Creates an invite and returns a one-time `token`. A manager can invite any role. A secretary can only invite a `member`. |
| `POST /staff/invites/preview` | anyone with the token | Shows the store, role and email before joining. Does not use up the link. |
| `POST /staff/invites/accept` | anyone with the token | Creates the account (or uses the existing one) and joins the store. Returns an access token. |
| `GET /staff` | any staff | Lists everyone in your store. Members do not get email addresses. |
| `GET /staff/{member_id}` | manager, secretary | One staff member. |
| `PATCH /staff/{member_id}/role` | manager | Changes a staff member's role. Applies on their next request. |
| `PATCH /staff/{member_id}/alias` | manager | Sets the name shown for this person in this store. Their account name does not change. |
| `GET /staff/{member_id}/attendance` | manager | The person's latest 31 attendance days, newest first. |
| `POST /staff/{member_id}/attendance` | manager | Saves one day: present, late, half day or absent. Saving the same date replaces it. |
| `POST /staff/{member_id}/deactivate` | manager | Turns off a staff member's access. |

**Ideas**
- Invites expire after `INVITE_EXPIRE_HOURS` (default 72) and work only once. Manager links expire sooner, after `MANAGER_INVITE_EXPIRE_HOURS` (default 24), because they give full control.
- Sending a new invite to the same email cancels the older one.
- If the invitee already has an account (e.g. from another store), they confirm with their own password.
- Inviting a deactivated person again turns them back on.
- A manager can't deactivate themselves or change their own role, so a store always keeps a manager.
- Staff changes in one store run one at a time (the store row is locked), so two managers can't remove each other at the same moment.
- Invites are not emailed. The manager creates a link on the Staff screen and shares it.
- The manager must choose Manager, Secretary or Member for each link. The link decides the role, so the person joining cannot pick a different one.
- The person who created the store is its owner (`store_members.is_owner`, migration `0014`). Other managers cannot change or remove the owner, so a second manager is a backup, not a takeover risk.
- A manager link stops working if the manager who made it is removed or demoted before it is used.
- A secretary's invite cannot bring back someone a manager removed, and cannot replace a manager's open secretary or manager link.
- Managers open a person from the Staff list (`/staff/{id}`) to see their details, set an alias and save attendance. The Invite someone button opens `/staff/invite`.
- A branch is a separate store for now. The store name box suggests the form "Hardware (Branch)".
- A new person joining by link only sets a password. The email comes from the invite, and their name starts as the part of the email before the @.
- New passwords need 8 or more characters, a capital letter, a small letter, a number and a symbol. The server checks this for sign up, invites, reset and change password. Older passwords still work at sign in. The form can also suggest a strong password, and browsers that support it offer to save it. Sukat never stores the plain password.
- Sign up asks "Manager" or "Member". A manager creates a store. A member cannot make an account alone, because every account must belong to a store, so the app asks for the invite link instead.

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
- Managers change roles and create invite links on `/staff`. Deactivate is API-only: it has no web screen yet.

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
- Trade-off: someone can block a person's login for 15 minutes by typing wrong passwords for their email. Forgot password still works during the block, and a successful reset clears it.

**Deploying:** set the same `INTERNAL_API_SECRET` on the API and the web app. The web app sends each visitor's IP with that secret, and the API ignores the IP header without it. Otherwise every user looks like the same IP. See `docs/deploy.md`.

### Staff page when the API is down

**What:** `/staff` shows "API not reachable" instead of an error screen.

**Why:** `fetch()` doesn't return an error status when the server is off. It **throws**. The page now catches that.

### Same-origin check behind HTTPS

**What:** `isSameOrigin` (`web/src/lib/server/auth-route.ts`) compares only the **host** of the browser's `Origin` with the request's `x-forwarded-host` (or `host`).

**Why:** on a real host, HTTPS usually ends at a proxy. The browser says `https://sukat.ph` but Next.js sees `http://`. Comparing the full origin blocked every login. Comparing the host is the same check Next.js uses for its own Server Actions.

## Step 9 — Account security

**What**

| Endpoint | Who | What it does |
|---|---|---|
| `POST /auth/logout` | signed in | Ends the session on the server. |
| `PATCH /auth/me` | signed in | Changes your own name. |
| `POST /auth/change-password` | signed in | Needs the current password. Returns a new token for this device. |
| `POST /auth/forgot-password` | anyone | Emails a reset link, but only to an email that is proven: confirmed with a link, or the owner's own sign-up email. An invited person's unconfirmed email gets nothing, so a made-up or mistyped address can't be used to take over the account. Same answer in every case. |
| `POST /auth/reset-password` | anyone with the link | Sets a new password. The person then signs in normally. |
| `POST /auth/verify-email` | anyone with the link | Confirms the email. |
| `POST /auth/resend-verification` | signed in | Sends a new confirmation link. |

Web pages: `/forgot-password`, `/reset-password`, `/verify-email`, `/more/settings` (your name, password, and a light, dark or system look, saved on each device), and a role picker on `/staff`. An unconfirmed user sees a notice with a resend link on the More tab.

Migration `0010` adds `users.email_verified_at`, `users.token_version`, and the `auth_tokens` table. Accounts that existed before it count as confirmed. Migration `0011` adds `email_outbox`.

**Ideas**
- **Signing out everywhere.** A JWT stays valid until it expires, so the server needs a way to cancel it. Each user has a `token_version`, every token carries it, and `get_current_member` compares the two. Logout and any password change add 1, which cancels every token that user holds, on all devices.
- **One-time links.** `auth_tokens` stores only a SHA-256 hash of each link's token, its purpose, and when it expires or was used. A leaked database can't be used to open the links. A link works once, and a newer link cancels the older one of the same kind.
- **Confirming email protects AI spending.** Reading a photo and asking the AI cost money, so `POST /scans`, `POST /scans/{id}/retry`, `POST /scans/{id}/rescan`, and `POST /insights/chat` need a confirmed email (403 with code `email_not_verified`). Everything else works without it. Only the person who set up the store (the owner) must confirm first. Staff who join by invite can use the AI right away, because a manager or secretary vouched for them. Their email is **not** marked as confirmed, though: the person who made the invite may have typed it, so nobody has proved it is theirs. `GET /auth/me` returns `email_confirmation` for the More tab's notice.
- **Limits on emails.** Reset and confirmation emails are limited to 3 per address and 20 per IP in 15 minutes. Signups are limited to 20 per IP, because each one sends an email.
- **Emails can't get lost.** The email is saved in the `email_outbox` table in the same database transaction as the change that caused it, so a failed signup never sends one and a successful one always has one waiting. A background loop in the API (`app/core/outbox.py`) sends waiting emails every few seconds. If sending fails it retries after 2, 4, 8, 16, then 32 minutes, and gives up on the 6th failure. A sent email is deleted right away, because its body contains a working link. Several API servers can run this safely: `FOR UPDATE SKIP LOCKED` stops two of them from taking the same email. If a server dies just after sending, one email can go out twice, which is harmless.
- **Staying signed in.** Sign-in does not time out: the token lasts 10 years. Browsers keep a cookie for at most 400 days, so the cookie is renewed whenever the app loads `/auth/me`. A session ends only with Sign out, a password change, deactivation, or more than 400 days without opening the app. Anyone holding an unlocked phone stays signed in, so shared phones should use Sign out.
- **Links use `WEB_APP_URL`, never the request's host**, so a forged `Host` header can't point a reset email at another site.
- **The reset and confirm pages send no referrer**, so the token in the URL doesn't leak to other sites.
- **Pages ask for a button press**, so an email scanner that opens links can't use up the token.

| Setting (`api/.env`) | Default | Meaning |
|---|---|---|
| `WEB_APP_URL` | `http://localhost:3000` | Where links in emails point |
| `PASSWORD_RESET_EXPIRE_MINUTES` | 30 | Reset link lifetime |
| `EMAIL_VERIFY_EXPIRE_HOURS` | 48 | Confirmation link lifetime |
| `AUTH_EMAILS_MAX_PER_EMAIL` | 3 | Emails per address per window |
| `AUTH_EMAILS_MAX_PER_IP` | 20 | Emails and signups per IP per window |
| `EMAIL_BACKEND` | `console` | `console` (development only) or `smtp` |
| `EMAIL_WORKER_ENABLED` | `true` | Runs the loop that sends waiting emails |
| `EMAIL_POLL_SECONDS` | 5 | How often it checks |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` | port 587 | Mail server, used with `smtp` (needs STARTTLS) |

**Deploying:** set `EMAIL_BACKEND=smtp`, the `SMTP_*` values, and `WEB_APP_URL`. The API refuses to start with `console` unless `APP_ENV=development`.
