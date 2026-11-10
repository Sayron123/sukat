# Audit: Phases 0–3

Audited `main` at commit `c38a045`. No application code was changed for this audit.

## Summary

There are **2 High findings**, and both should be fixed before the first real deployment:

- **H1:** a list line with no unit is saved in the product's base unit, with no warning.
- **H2:** if `APP_ENV` and `JWT_SECRET` are not set, the API runs with a public signing secret. Anyone can then forge a login for any store.

I found no way to read or change another store's data through the API, as long as a private `JWT_SECRET` is set.

| Rule checked | Result | Details |
|---|---|---|
| Queries filter by `store_id` from the token | Pass, with gaps | No cross-store access found. Three queries have no filter but are not exploitable (L10). A database key has a gap (M3). |
| Role checks on every write endpoint | Partly | All endpoints are guarded, but members can write product aliases through stock-in (M1). |
| All stock changes go through `stock_movements` | Pass in the app | The only line that writes stock is `stock_service.py:222`. The database does not enforce this (L3). |
| Saves use one transaction with row locks | Pass, with a gap | One commit at `stock_service.py:241`. Locks at `:87-91` and `:176-185`. New products can still deadlock (L6). |
| `client_request_id` unique per store | Pass | `UNIQUE (store_id, client_request_id)` exists in the database and is tested. |
| Conversions never guess | **Fail** | H1 and M2. |
| Unknown units raise an error | Pass | `"dozen"` returns 422 with a clear message. |
| Money is integer centavos | Pass, with small gaps | Product and sales money is `INTEGER` or `BIGINT`. See L11, L12 and L13. |
| Quantities are `NUMERIC` | Pass | All are `NUMERIC(12,3)`. Factors are `NUMERIC(18,6)`. Rounding: L4. |
| Timestamps are `TIMESTAMPTZ` UTC | Pass | All 17 timestamp columns are `TIMESTAMPTZ`, and none are without a time zone. The connection sets `timezone=UTC` (`core/db.py:13`). |
| Secrets not committed, `.env` ignored | Pass | `.env` files are ignored, and only `.env.example` files were ever committed. All 57 commits were searched for common key formats, which found only the placeholder `sk-ant-...` and the public dev secret. |
| R2 keys prefixed by `store_id` | Pass, with a small gap | The server creates the key and checks the prefix. One regex edge case: L2. |
| Tests | Gaps | See [Missing tests](#missing-tests). |
| Docs match the code | Gaps | See [Docs that do not match the code](#docs-that-do-not-match-the-code). |

**Severity**

- **High:** wrong stock under normal use, or one missed setting exposes every store.
- **Medium:** breaks a stated rule or guarantee, but needs specific conditions or does limited damage.
- **Low:** an edge case, cleanup, or something that is not reachable today.

## How to reproduce

Python steps use the fixtures in `api/tests/conftest.py`: `api`, `db`, `manager`, `signup`, `storage` and `reader`. Put them in a temporary file such as `api/tests/test_tmp_audit.py`, run `uv run pytest tests/test_tmp_audit.py -s` from `api/`, then delete the file. Postgres must be running. The tests only touch the `sukat_test` database.

The "Observed" results come from running these on the audited commit.

## High

### H1. A missing unit silently becomes the base unit

**Where**
- `api/app/ai/convert.py:58`
- `api/app/inventory/scan_service.py:183`
- `api/app/ai/prompts/read_list.md:15`

**Problem:** the prompt tells the AI to use the product's unit when no unit is written, and the code does the same for an empty unit. A row like "10 pako 4" could mean 10 boxes (250 kg) but is shown as 10 kg. The line gets no "Check" tag, so staff have no reason to look at it. Because the AI fills in the unit itself, the code usually can't tell that the unit was missing.

**Reproduce**

```python
from decimal import Decimal
from uuid import UUID
from app.ai.convert import to_scan_line
from app.ai.schemas import CatalogEntry, RawLine
from tests.conftest import make_product, upload_photo

def test_missing_unit(api, manager, storage, reader):
    p = make_product(api, manager, name="Nail 4", category="Nails & Screws", base_unit="kg",
                     conversions=[{"from_unit": "box", "factor": "25"}])
    raw = RawLine(raw_text="10 nail 4", product_ref="P1", suggested_new_name=None,
                  qty=Decimal("10"), unit="", unit_price=None, line_total=None, confidence=0.95)
    reader.lines = [to_scan_line(raw, {"P1": CatalogEntry(UUID(p["id"]), p["name"], "kg")})]
    key = upload_photo(api, manager, storage)
    print(api.post("/scans", json={"photo_key": key}, headers=manager).json()["lines"][0])
```

**Observed:** `unit: "kg"`, `qty_base: "10.000"`, `needs_check: false`, `check_reasons: []`.

### H2. The default settings use a public signing secret

**Where**
- `api/app/core/config.py:16`
- `api/app/core/config.py:23`
- `api/app/core/config.py:71-74`
- `api/.env.example:6-8`

**Problem:** the secret check only runs when `APP_ENV` is exactly `production`, and the default is `development`. The default `JWT_SECRET` is in the public repo. If a server starts without these two settings, it gives no error or warning, and anyone can sign a token for any user and store. This defeats store isolation completely. Nothing is deployed yet, so this is a risk for the first deployment rather than a live problem.

**Reproduce**

1. Sign up through the API and keep the token.
2. Re-sign its claims with the public secret:

```python
import datetime as dt, jwt
from app.core.config import DEV_JWT_SECRET
from tests.conftest import auth_header

def test_forged_token(api, signup):
    # Run with the default secret. Your api/.env must not set a different JWT_SECRET.
    claims = jwt.decode(signup()["access_token"], options={"verify_signature": False})
    now = dt.datetime.now(dt.UTC)
    forged = jwt.encode({**claims, "iat": now, "exp": now + dt.timedelta(hours=1)},
                        DEV_JWT_SECRET, algorithm="HS256")
    print(api.get("/auth/me", headers=auth_header(forged)).status_code)
```

**Observed:** `200`. Separately, `Settings(_env_file=None)` starts with no error and uses the public secret.

## Medium

### M1. Members can change product aliases through stock-in

**Where:** `api/app/inventory/stock_service.py:235-236` and `:262-263`

**Problem:** `POST /transactions` is open to any active staff member, and it adds a `product_aliases` row when a line's product differs from the AI's match. The role check at `:144` only covers new products. Aliases affect future AI matching and search, and `docs/phase-2.md:81` says members get 403 on every write. Either the rule or the code needs to change.

**Reproduce**

1. Create products A and B, and log in as a member.
2. Send `PATCH /products/{A}` with `{"aliases": ["x y z"]}`. **Observed:** `403`.
3. Make the fake reader match "5 mystery item" to B, and create a scan.
4. Send `POST /transactions` with that `scan_id` and a line using product A and `scan_line: 0`.

**Observed:** `201`, and product A's aliases are now `["mystery item"]`.

### M2. Conflicting conversions: the first match silently wins

**Where**
- `api/app/products/units.py:123-126`
- `api/app/products/schemas.py:43-49`

**Problem:** when a unit has no direct conversion, `convert()` uses the first metric conversion it finds. Nothing stops a product from having two conversions that disagree, so the result depends on sort order and no error is raised.

**Reproduce**

1. Create a product with base unit `pc` and conversions `1 m = 0.5` and `1 cm = 0.1`.
2. Save a stock-in of `1000 mm`.

**Observed:** `201` with `qty_base: 10.000`. Going through `m` would give `0.5`, which is 20 times less.

### M3. A stock movement can point to another store's line

**Where**
- `api/app/inventory/models.py:164-166`
- `api/alembic/versions/0004_inventory_scans.py:232-234`

**Problem:** `stock_movements.transaction_item_id` references `transaction_items(id)` only, not `(id, store_id)`. The other store-owned references are composite, and `docs/phase-3.md:19` says this applies to every child row. The API can't trigger this today, but Phase 4 adds more code that writes movements, and this key is harder to fix once real data exists.

**Reproduce**

1. Create two stores, each with a saved stock-in.
2. Insert a new `transaction_items` row for Store B.
3. With SQL, insert a `stock_movements` row using Store A's `store_id`, product and transaction, with `transaction_item_id` set to the Store B line.

**Observed:** the insert succeeds. For comparison, using Store B's `product_id` in the same insert fails with `ForeignKeyViolation`.

### M4. Signup has no rate limit and reveals which emails exist

This is outside the requested checklist.

**Where**
- `api/app/auth/service.py:33-34`
- `api/app/auth/router.py:14-17`

**Problem:** login hides whether an email has an account, but signup does not. Signup also has no failure limit, so anyone can test emails without restriction. A new email creates a store and runs a costly password hash each time.

**Reproduce:** sign up with an email, then send `POST /auth/signup` with the same email 50 times.

**Observed:** every response is `409 An account with this email already exists`, and none is `429`.

**Update:** signups are now limited to 20 per IP in 15 minutes (`AUTH_EMAILS_MAX_PER_IP`). Signup still reveals which emails exist.

## Low

### L1. Upload links can be used more than once

**Where:** `api/app/core/storage.py:56-67` and `:116-132`

**Problem:** nothing makes a link single-use, so a photo can be replaced with different bytes of the same size until the link expires (5 minutes by default). No hash of the photo is stored. `docs/phase-3.md:26` says the link allows exactly one upload.

**Reproduce:** with local storage, request an upload URL, then `PUT` to it twice with different bytes.

**Observed:** `204` both times. R2 was not tested live, but its presigned link has no single-use check in our code either.

### L2. A photo key with a trailing newline passes the check

**Where:** `api/app/inventory/scan_service.py:30` and `:40-41`

**Problem:** in Python, `$` also matches just before a final newline. This doesn't cross stores, because the prefix is still checked, but it gets around the one-scan-per-photo rule.

**Reproduce:** send `POST /scans` with a valid key, then again with the same key plus `"\n"`.

**Observed:** `201` both times, with two separate scan rows. The second has status `failed`.

### L3. The database does not protect the stock history

**Where**
- `api/app/inventory/models.py:164-166`
- `api/app/products/models.py:55`

**Problem:** the app code follows the rule, but the database would accept a stock change with no movement. Deleting a transaction line also deletes its movement without changing stock, which removes the audit record.

**Reproduce:** after a stock-in of 5, run `UPDATE products SET stock_qty = 999` and `DELETE FROM transaction_items WHERE transaction_id = ...`.

**Observed:** stock is `999.000` and no movements remain for that transaction.

### L4. Rounding can change very small quantities a lot

**Where**
- `api/app/inventory/scan_service.py:158-159`
- `api/app/inventory/stock_service.py:196`

**Problem:** `qty_base` is rounded to 3 decimals with no warning. For a bag product with `1 kg = 0.025 bag`, 21 g becomes 0.000525 bag, then rounds to 0.001 bag, which is 40 g.

**Reproduce:** run `quantize_qty(Decimal("0.021") * Decimal("0.025"))`, or save a 21 g stock-in on such a product.

**Observed:** the function returns `0.001`. I did not run the API version.

### L5. A very large total causes a 500

**Where**
- `api/app/inventory/stock_service.py:206` and `:238`
- `api/app/inventory/models.py:95`

**Problem:** each line passes validation, but the sum can exceed `BIGINT`. The save does roll back, so no data is damaged.

**Reproduce:** save 10 lines on 10 products, each with qty `999999999.999` and price `999999999`.

**Observed:** an unhandled `DataError: bigint out of range`.

### L6. Saves that create new products can deadlock

**Where:** `api/app/inventory/stock_service.py:166-168`, `:118-122` and `:278-287`

**Problem:** new products are inserted before the ordered locks, in whatever order the request lists them. Postgres then cancels one save, and `save_stock_in_once` only handles `IntegrityError` and `ScanAlreadySaved`, so the error would reach the user as a 500. A retry works, because the failed save rolled back. `docs/phase-3.md:85` suggests saves can't deadlock.

**Reproduce:** with the `_run_parallel` pattern from `tests/test_transactions.py`, run two saves at once that create the same 120 new products in opposite order.

**Observed:** in all 5 runs, one save succeeded and the other raised `OperationalError/DeadlockDetected`. I called `save_stock_in` directly, so the 500 comes from reading the handler rather than from running it.

### L7. A huge AI quantity breaks the scan permanently

**Where:** `api/app/inventory/scan_service.py:159`, `:165`, `:183` and `:201`

**Problem:** `to_scan_line` accepts any positive number, but `quantize` fails on very large ones and `review_line` doesn't catch it. The scan is saved as `read` first, so every later view fails and retry is refused.

**Reproduce:** set `reader.lines = [scan_line(product_id, unit="kg", qty=Decimal("1E+30"))]`, then send `POST /scans` twice with the same key.

**Observed:** an unhandled `InvalidOperation` both times.

### L8. Simultaneous retries each pay for an AI read

This is outside the requested checklist.

**Where:** `api/app/inventory/scan_service.py:296-303` and `:100-102`

**Problem:** retry checks the status without locking the row, so a double tap can start two paid reads. The saved result stays safe because of the later lock (`:136-145`).

**Reproduce:** make a scan fail, then call `retry_scan` from 4 threads at once with a slow fake reader.

**Observed:** AI calls per run were `[2, 4, 4, 4, 4, 4, 4, 4]`.

### L9. Two managers can lock a store out

**Where:** `api/app/stores/service.py:160-164`

**Problem:** self-deactivation is blocked, but there is no check that one active manager remains. There is also no in-app way to recover.

**Reproduce:** with two managers, authenticate both, then have each call `deactivate` on the other at the same moment.

**Observed:** 0 active members remain, and `/auth/me` returns `401` for both.

### L10. Three queries have no `store_id` filter

**Where**
- `api/app/inventory/stock_service.py:305`
- `api/app/inventory/stock_service.py:308-310`
- `api/app/inventory/scan_service.py:139-144`

**Problem:** these look up rows by an ID that was already checked for the store, so they can't leak data today. The first one relies on the composite key on `transaction_items`. They do contradict `docs/api-structure.md:38`, and they break the simple rule that a reviewer can check.

**Reproduce:** read the queries. I could not get cross-store data from them through the API: `GET /transactions/{id}` returns 404 for another store's transaction, and that check runs first.

### L11. `ai_usage.cost_centavos` is not an integer

**Where**
- `api/app/ai/models.py:26`
- `api/alembic/versions/0004_inventory_scans.py:37`

**Problem:** this is `NUMERIC(14,4)`, so the name and the type disagree with the integer-centavos rule. It is deliberate (`docs/phase-3.md:21`) and is not customer money, so either record it as an exception or store it in a smaller whole unit.

**Reproduce:** in `sukat_test`, run `SELECT data_type, numeric_scale FROM information_schema.columns WHERE table_name='ai_usage' AND column_name='cost_centavos';`.

**Observed:** `numeric`, scale `4`.

### L12. A price worked out from a written total can lose a centavo

**Where:** `api/app/ai/convert.py:61-63`

**Problem:** when only a line total is written, the unit price is rounded and the line total is then recalculated from it. The written total is not kept.

**Reproduce:** call `to_scan_line` with qty `3`, `line_total` `100` and no unit price, then `line_total(qty, price)`.

**Observed:** the unit price is `3333` and the stored total is `9999`, not `10000`.

### L13. The review screen total can differ from the saved total

**Where:** `web/src/app/scan/lines.ts:45`

**Problem:** the preview uses floating point, while the server uses exact decimals. Only the preview is affected.

**Reproduce:** use qty `1.005` and price `100` centavos. In Node, `Math.round(1.005 * 100)` gives `100`. On the server, `line_total(Decimal("1.005"), 100)` gives `101`.

### L14. Production can start with local photo storage

**Where:** `api/app/core/config.py:35`, `:38` and `:75-78`

**Problem:** production doesn't require R2, and `PUBLIC_API_URL` still defaults to `localhost`. Photos would go to the server's disk, and upload links would point to the wrong address.

**Reproduce:** run `Settings(_env_file=None, APP_ENV="production", JWT_SECRET="x"*40)`.

**Observed:** it starts with `STORAGE_BACKEND=local` and `PUBLIC_API_URL=http://localhost:8000`.

## Missing tests

To confirm any row, search the named files for the behaviour. None of these has a test today.

| Rank | Rule | What is not tested | Where it belongs |
|---|---|---|---|
| High | Units | A line with no unit (H1) | `tests/test_ai_client.py`, `tests/test_scans.py` |
| Medium | Web | The web app has **no test files and no `test` script**, including the proxy allow-list fix (`route.ts:20`) and price and quantity parsing (`format.ts:10-25`). The review screen's "10 shows as 1" bug has no regression test. | `web/package.json:5-10` |
| Medium | Checks | There is **no CI** (no `.github/`), so tests, `alembic check` and secret scanning run only if someone remembers. | Repo root |
| Medium | Column types | Nothing checks for `TIMESTAMPTZ`, `NUMERIC` or integer money. `alembic check` passes today, but no test runs it. | New schema test |
| Medium | Stock | Nothing checks that movements add up to `stock_qty` after several saves. | `tests/test_transactions.py` |
| Medium | Roles | A member's save creating an alias (M1). The current test only covers new products. | `tests/test_transactions.py:190` |
| Medium | Auth | No test for 401 without a token on `POST /products`, `PATCH /products/{id}`, archive, unarchive, `POST /scans`, `GET /scans/{id}`, retry, `POST /transactions`, `GET /transactions/{id}`, or `GET /staff/{id}`. They do return 401 today. | `tests/test_products_access.py:125`, `tests/test_inventory_access.py` |
| Medium | Isolation | A movement pointing to another store's line (M3) | `tests/test_inventory_access.py` |
| Medium | Secrets | Default settings with no `APP_ENV` (H2). The existing test only covers `APP_ENV=production`. | `tests/test_auth.py:113` |
| Medium | Units | Conflicting conversions (M2) | `tests/test_units.py` |
| Low | R2 keys | A key with a trailing newline (L2) | `tests/test_uploads.py:85-97` |
| Low | Uploads | Reusing an upload link (L1) | `tests/test_uploads.py` |
| Low | R2 | `R2Storage.read`. Only the presigned URL is tested. | `tests/test_uploads.py:99` |
| Low | Stock | Total overflow (L5), new-product deadlock (L6), huge AI quantity (L7) | `tests/test_transactions.py`, `tests/test_scans.py` |
| Low | Races | Simultaneous retries (L8), managers deactivating each other (L9) | `tests/test_scans.py`, `tests/test_staff.py` |

## Docs that do not match the code

| Rank | Doc | What it says | What the code does |
|---|---|---|---|
| Medium | `docs/phase-3.md:19` | Composite keys on every child row | `transaction_item_id` is not composite (M3) |
| Medium | `docs/phase-2.md:81` | Every member write gets 403 | Members can create aliases through stock-in (M1) |
| Low | `docs/phase-2.md:95` | The proxy allows `products`, `catalog` and `auth/me` | It allows `products`, `auth/me`, `scans` and `transactions` (`route.ts:13`) |
| Low | `docs/phase-2.md:51` | Stock movements come in a later phase | They shipped in Phase 3. `api/app/products/models.py:54` says the same. |
| Low | `docs/phase-3.md:26` | The link allows exactly one upload | It can be reused until it expires (L1) |
| Low | `docs/phase-3.md:55` | `api/app/inventory/scans.py` | No such file. The code is in `router.py` and `scan_service.py`. |
| Low | `docs/phase-3.md:85` | Saves can't deadlock | They can when creating new products (L6) |
| Low | `docs/phase-3.md:145` | `SaveError`, mapped to HTTP in the router | `SaveError` no longer exists. One handler in `main.py:22-25` renders errors. |
| Low | `docs/phase-3.md:149` | A read takes up to about a minute | Up to about 3 minutes: 90 s × 2 attempts (`config.py:53-54`) |
| Low | `docs/phase-1.md:39-41`, `:77-81`; `docs/phase-2.md:42-48`; `docs/phase-3.md:26`, `:33`, `:56-57`, `:73` | Paths like `/products` | The real paths start with `/v1` (`main.py:17`), except `/health` |
| Low | `README.md:5-6` | The repo is at Phase 1 | Phases 2 and 3 are merged. This isn't a `phase-X` doc, but it has the same problem. |

To confirm these, compare the doc line with the code location shown. For the `/v1` row, `GET /products` returns 404 and `GET /v1/products` works.

## Role checks by endpoint

I called every route without a token, as a member, and as a secretary. Manager access comes from reading the role checks in the routers.

| Access | Endpoints |
|---|---|
| Public | `POST /auth/signup`, `POST /auth/login`, `POST /staff/invites/accept`, `GET /health` |
| Signed link, no login | `PUT /uploads/local/{key}` (local storage only) |
| Any active staff member | `GET /auth/me`, `GET /products`, `GET /products/catalog`, `GET /products/{id}`, `POST /scans/upload-url`, `POST /scans`, `GET /scans/{id}`, `POST /scans/{id}/retry`, `POST /transactions`, `GET /transactions/{id}` |
| Manager or secretary | `POST /products`, `PATCH /products/{id}`, archive, unarchive, `POST /products/import`, `GET /staff`, `GET /staff/{id}` |
| Manager only | `POST /staff/invites`, `POST /staff/{id}/deactivate` |

## What this audit did not cover

- **Cloudflare R2:** no real bucket was used. Only the local storage path and the presigned URL's format were checked.
- **The real AI:** every read used the fake reader, so how often the real model fills in a missing unit is unknown.
- **Deployment:** nothing is deployed, so hosting, HTTPS and proxy settings weren't checked.
- **The web app in a browser:** I read the money, unit and proxy code, and ran only the lint and build steps. I did not click through it.
- **Phase 4:** `phase-4-sales-scan` isn't on `main`. M3, L3 and L6 matter more once that branch is merged, so check them against it.
- **Database Row-Level Security:** it is off on the tables I checked. It isn't required by the checklist, so it isn't listed as a finding, but it would be a useful second safeguard for store isolation.
