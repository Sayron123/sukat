# Deploying Sukat

Sukat has three parts:

| Part | What it is | Where it runs |
|---|---|---|
| Database | PostgreSQL 16 | A managed Postgres (Neon, Supabase, Render, RDS, …) |
| API | FastAPI, `api/Dockerfile` | Any host that runs a Docker image (Fly.io, Render, Railway, a VPS) |
| Web | Next.js app in `web/` | Vercel, or any Node 22 host (`npm run build` then `npm start`) |

Photos go to Cloudflare R2. The AI is Anthropic (Claude) or Google (Gemini).

Everything must be on **HTTPS**. The API refuses to start in production if a setting is unsafe (see step 4).

---

## 1. Before you start

You need:
- a domain, for example `sukat.example.com` (web) and `api.sukat.example.com` (API);
- a Cloudflare account (R2);
- an Anthropic or Google AI Studio account with **billing turned on** (paid API plans don't use your data for training; the Privacy page says so);
- optional: a Sentry account for error reports.

Make secrets with:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

## 2. Database

1. Create a PostgreSQL 16 database.
2. Create a user for the app with its own strong password. Don't use `sukat:sukat`: the API refuses it.
3. Note the connection string in this form:
   `postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME?sslmode=require`
4. Turn on daily backups in your provider (keep at least 7 days).

You don't run migrations by hand: the API image runs `alembic upgrade head` each time it starts.

## 3. Cloudflare R2 (photos)

1. R2 → **Create bucket**, e.g. `sukat-photos`. Keep it private (no public access).
2. R2 → **Manage API tokens** → create a token with **Object Read & Write** on that bucket. Note the Access Key ID and Secret.
3. Note your **Account ID** (R2 overview page).
4. Bucket → **Settings → CORS policy**, allow uploads from the web app:

   ```json
   [
     {
       "AllowedOrigins": ["https://sukat.example.com"],
       "AllowedMethods": ["PUT"],
       "AllowedHeaders": ["Content-Type", "Content-Length"],
       "MaxAgeSeconds": 3600
     }
   ]
   ```

## 4. API

### Settings

Set these on your host (not in a file in git). `api/.env.example` explains each one.

| Setting | Value |
|---|---|
| `APP_ENV` | `production` |
| `DATABASE_URL` | from step 2 |
| `JWT_SECRET` | a new random value (step 1), 32+ characters |
| `CORS_ORIGINS` | `https://sukat.example.com` (comma-separate several; each must be `https://`) |
| `PUBLIC_API_URL` | `https://api.sukat.example.com` |
| `STORAGE_BACKEND` | `r2` |
| `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET` | from step 3 |
| `AI_PROVIDER` | `anthropic` or `gemini` |
| `ANTHROPIC_API_KEY` or `GEMINI_API_KEY` | the key for that provider |
| `SENTRY_DSN` | optional, from Sentry (a Python project) |
| `RELEASE` | optional, e.g. the git commit, shown in Sentry |
| `WEB_CONCURRENCY` | workers, default `2` (about 1 per CPU) |
| `FORWARDED_ALLOW_IPS` | the IP of the proxy in front of the API (see below) |

The API refuses to start in production when: `JWT_SECRET` is missing, the default or short; `DEBUG` is on; `DATABASE_URL` uses `sukat:sukat`; or `CORS_ORIGINS` is empty, `*` or not HTTPS. The error says which one.

**`FORWARDED_ALLOW_IPS`:** login and signup limits count per IP. The API only believes `X-Forwarded-For` from these addresses. Set it to your load balancer's IP (or its range). If the API can only be reached through your host's proxy (no public port), `*` is fine. Leaving the default (`127.0.0.1`) is safe but makes everyone share one IP for limits.

### Build and run

```bash
docker build -t sukat-api ./api
```

```bash
docker run --env-file api.env -p 8000:8000 sukat-api
```

On start the container:
1. runs database migrations (set `RUN_MIGRATIONS=false` on all but one instance if you start several at once);
2. starts uvicorn with `WEB_CONCURRENCY` workers on `PORT` (default 8000), as a non-root user.

Point your host's health check at `GET /health`. It returns 200 when the API and database are fine, 503 when the database is down. The image also has a Docker `HEALTHCHECK`.

### Check it

```bash
curl -i https://api.sukat.example.com/health
```

You should see `{"status":"ok","db":"ok"}` and an `x-request-id` header. `https://api.sukat.example.com/docs` should be 404 (API docs are off in production).

## 5. Web

### Settings

| Setting | Value |
|---|---|
| `API_URL` | `https://api.sukat.example.com` (server-side calls) |
| `NEXT_PUBLIC_API_URL` | `https://api.sukat.example.com` |
| `NEXT_PUBLIC_CONTACT_EMAIL` | the email for privacy requests (shown on /privacy and /terms) |
| `SENTRY_DSN`, `NEXT_PUBLIC_SENTRY_DSN` | optional, from Sentry (a Next.js project; can be the same DSN) |
| `APP_ENV`, `NEXT_PUBLIC_APP_ENV` | `production` |

`NEXT_PUBLIC_*` values are built into the app: set them **before** building, and rebuild when they change.

### Build and run

On Vercel: import the repo, set **Root Directory** to `web`, add the settings, deploy.

On your own server (Node 22):

```bash
cd web && npm ci && npm run build
```

```bash
cd web && PORT=3000 npm start
```

Put it behind HTTPS (Caddy, nginx, or your host's load balancer). In production the web app sends HSTS and a strict Content-Security-Policy, and the sign-in cookie is `__Host-` + Secure, so plain HTTP won't work.

## 6. First run check

1. Open `https://sukat.example.com/signup`, create a store (tick the Terms box).
2. Add a product, do a stock-in, scan a photo list. The photo upload checks R2 and its CORS.
3. Ask the AI tab "sales today". This checks the AI key.
4. More → **Download store data** → Products. A CSV downloads.
5. Sign out, sign in again.
6. If Sentry is on: check the project receives events, with no emails or names in them.

## 7. Before you announce it

- Read `/privacy` and `/terms` and fix anything that isn't true for how you run Sukat (hosting, retention, contact). Change `LAST_UPDATED` in `web/src/lib/legal.ts` and `TERMS_VERSION` in `api/app/auth/schemas.py` together.
- Set log retention on your host to 90 days or less, and Sentry's data retention to match (the Privacy page says "up to 90 days").
- Check database backups are running, and try one restore.
- Set AI spending limits in the Anthropic or Google console.

## Updating

1. Merge to `main` (CI must be green: lint, tests, web build, API image).
2. Deploy the new API image. It runs any new migrations on start.
3. Deploy the web app.

Deploy the API first: so far, migrations only add things, so the old web app keeps working while the API updates. Check new migrations before deploying.

## When something goes wrong

- Every API response has an `X-Request-ID`. Each log line shows it in `[brackets]`, and Sentry tags events with `request_id`. Search the logs for it.
- API won't start: read the first error line. Unsafe settings name the setting to fix.
- `/health` returns 503: the API can't reach the database. Check `DATABASE_URL` and the database's allowed IPs.
- Photo uploads fail: check the R2 CORS rule has the exact web origin, and the R2 keys.
- "Too many sign-ups / failed attempts" for everyone: `FORWARDED_ALLOW_IPS` is wrong, so all users look like one IP.
