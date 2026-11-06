# Phase 5 — What and why

Phase 5 adds **reports**: today's sales on Home, low stock, photos waiting for review, a filterable History, and each product's stock history. No new tables; one new index.

## Step 1 — Report functions

**What** (`api/app/insights/reports.py`, shapes in `schemas.py`)

| Function | Returns |
|---|---|
| `sales_summary(range)` | Sales total and count, plus the period of the same length just before (today vs yesterday) and the % change |
| `top_products(range, limit, by)` | Best sellers by quantity (base unit) or by revenue |
| `low_stock()` | Active products with `stock_qty <= low_stock_level`, lowest first |
| `stock_movements(filters)` | Every stock change, newest first, 20 per page. Filters: dates, product, kind (sale / stock_in / adjustment / void), staff member |
| `product_history(product_id, range)` | One product's changes, each with the stock right after it |
| `stock_check()` | Products whose stock doesn't equal the sum of their movements |
| `scans_to_review()` | Photos read in the last 7 days but not saved |

**Ideas**
- **Dates are Manila days.** A range like `2026-11-05..2026-11-05` becomes `2026-11-04 16:00 UTC` to `2026-11-05 16:00 UTC`, because the database stores UTC. So a sale at **11:30 PM counts for that day**, not the next. The zone is the `STORE_TIMEZONE` setting.
- **Voided sales never count** in sales numbers or best sellers.
- **`store_id` always comes from the token.** Each function filters every query by it.
- **Typed in and out (Pydantic).** The AI chat in Phase 6 will call these same functions as tools, so their inputs and outputs need to be exact.
- **`stock_check` should always be empty.** Stock only changes together with a movement in the same database transaction. If something shows up, it's a bug or someone edited the database by hand.
- **`tzdata` package added.** Windows Python has no built-in time zone list, so `Asia/Manila` needs it.

## Step 2 — Endpoints

**What** (`/v1/reports/...`, `api/app/insights/router.py`)

| Endpoint | Who |
|---|---|
| `GET /reports/sales-summary?start=&end=` (default today) | any staff |
| `GET /reports/low-stock` | any staff |
| `GET /reports/stock-movements?start=&end=&product_id=&kind=&created_by=&page=` | any staff |
| `GET /reports/products/{id}/history?start=&end=&page=` | any staff |
| `GET /reports/scans-to-review` | any staff |
| `GET /reports/top-products?start=&end=&limit=&by=qty\|revenue` | manager, secretary |
| `GET /reports/stock-check` | manager only |

`GET /transactions` also takes `start` / `end` (Manila days) and the `adjustment` type, for the History screen.

**Why**
- **Members see what they need to work** (today's sales, what's low, history), but not best-seller and revenue rankings.
- **Stock check is for the owner**: it's an audit tool.
- **Bad ranges are refused** (end before start, more than 366 days) with a clear 422.

## Step 3 — Index

**What:** migration `0009` adds `stock_movements (store_id, created_at)`.

**Why:** the store-wide history is sorted and filtered by date. `transactions (store_id, created_at)` and `stock_movements (product_id, created_at)` already existed, so only this one was missing.

## Step 4 — Tests

`api/tests/test_reports.py` (12 tests):
- **Midnight**: an 11:30 PM sale counts for that day; a 12:30 AM sale counts for the next. The History list uses the same day boundaries.
- **Voided sales** are left out of the summary and best sellers.
- **Low stock**: equal to the level counts; no level or archived doesn't.
- **Pagination**: 25 movements → 20 + 5, newest first, with the right `stock_after`.
- **Stock check** is empty after a sale and a void, and catches a stock change that skipped the movement log.
- **Who can read what**, and **tenant isolation** (store B sees none of store A's numbers; A's product history is 404 for B).

Each key rule was broken on purpose (UTC days instead of Manila days, counting voided sales, no store filter, `<` instead of `<=`): the matching test fails.

## Step 5 — Web

| Screen | What |
|---|---|
| Home | Today's sales (big number, % vs yesterday), **Low stock** and **Needs review** counts, recent activity. Each card opens its list. |
| Low stock (`/stock/low`) | Products at or below their alert, lowest first. |
| Needs review (`/scans/review`) | Photos read but not saved. Tapping one reopens its review (`/scan/review/{id}`), so nothing has to be scanned twice. |
| History (`/transactions`) | Dates: Today, This week (from Monday), This month, Custom. Types: All, Sale, Stock in, Adjustment. Grouped by day, newest first. Tap a row for the detail. Filters are in the URL, so Home can link to "today's sales". |
| Product (`/stock/{id}`) | Stock, price, low-stock alert, and its stock history. Open to all staff; the edit form moved to `/stock/{id}/edit` (managers and secretaries). |

**Why**
- **"Today" is decided in Manila time everywhere** (server and screens), so a phone with the wrong time zone still shows the right day.
- **Needs review** catches photos that were scanned and then forgotten, which would otherwise mean missing stock or sales.
