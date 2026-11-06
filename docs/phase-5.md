# Phase 5 — What and why

Phase 5 adds **reports**: today's sales on Home, low stock, photos waiting for review, a filterable History, and each product's stock history. No new tables; one new index.

## Step 1 — Report functions

**What** (`api/app/insights/reports.py`, shapes in `schemas.py`)

| Function | Returns |
|---|---|
| `sales_summary(range)` | Sales total and count, plus an earlier period and the % change. A finished range is compared with the same number of days just before. A range that includes today is compared with yesterday / last week from Monday / last month from the 1st, cut at the same time (`previous.until`). `compared_to` says which in words ("same time yesterday") |
| `top_products(range, limit, by)` | Best sellers by quantity (base unit) or by revenue |
| `low_stock()` | Active products with `stock_qty <= low_stock_level`, lowest first |
| `stock_movements(filters)` | Every stock change, newest first, 20 per page. Filters: dates, product, kind (sale / stock_in / adjustment / void), staff member |
| `product_history(product_id, range)` | One product's changes, each with the stock right after it |
| `stock_check()` | Products whose stock doesn't equal the sum of their movements |
| `scans_to_review()` | Photos from the last 7 days read but not saved, or whose read failed in a way "Try again" can fix, including reads stuck in "pending" (`status` "read" or "failed"), newest first, max 50 (`has_more` when there were more) |

**Ideas**
- **Dates are Manila days.** A range like `2026-11-05..2026-11-05` becomes `2026-11-04 16:00 UTC` to `2026-11-05 16:00 UTC`, because the database stores UTC. So a sale at **11:30 PM counts for that day**, not the next. The zone is the `STORE_TIMEZONE` setting.
- **Voided sales never count** in sales numbers or best sellers.
- **Today is compared fairly.** Today isn't over, so at 9:15 AM it's compared with yesterday 00:00–9:15 AM, not all of yesterday (that showed a red drop every morning). Same for any range that includes today, lined up with the calendar: this week so far (from Monday) vs last week up to the same weekday and time; this month so far (from the 1st) vs last month up to the same day and time, capped at last month's last day. Other ranges that include today use the same number of days just before. `previous.until` says where the cut is (`null` for a finished range), and `compared_to` says it in words for the screen. A range from Monday that is only one day (today is Monday) counts as "today" and is compared with yesterday.
- **Dates must be between 2000-01-01 and 2100-12-31.** Year 1 or 9999 used to crash (500) when turned into UTC; now it's a 422. The period before the earliest allowed range may start in 1999; that's fine (it just has no sales).
- **Needs review includes failed reads that can be retried.** A photo the AI couldn't read is also a paper list not recorded yet; reopening it shows "Try again". That covers reads stuck in "pending" (cut off by a restart), which the phone also shows as retryable. A failure that retrying can't fix isn't listed. A failed scan the user replaced with "Take another photo" stays listed until it is 7 days old, because scans don't record that they were replaced.
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
- **Bad ranges are refused** (end before start, more than 366 days, before 2000 or after 2100) with a clear 422.

## Step 3 — Index

**What:** migration `0009` adds `stock_movements (store_id, created_at)`.

**Why:** the store-wide history is sorted and filtered by date. `transactions (store_id, created_at)` and `stock_movements (product_id, created_at)` already existed, so only this one was missing.

## Step 4 — Tests

`api/tests/test_reports.py` (12 tests; 16 after the audit fixes below):
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
| Home | Today's sales (big number, % vs the same time yesterday), **Low stock** and **Needs review** counts, recent activity. Each card opens its list. |
| Low stock (`/stock/low`) | Products at or below their alert, lowest first. |
| Needs review (`/scans/review`) | Photos read but not saved ("Review"), or not read ("Failed"). Tapping one reopens its review (`/scan/review/{id}`), so nothing has to be scanned twice. The API returns at most 50 and says if there were more (`has_more`); only then do the screen and Home show "50+". |
| History (`/transactions`) | Dates: Today, This week (from Monday), This month, Custom. Types: All, Sale, Stock in, Adjustment. Grouped by day, newest first. Tap a row for the detail. Filters are in the URL, so Home can link to "today's sales". |
| Product (`/stock/{id}`) | Stock, price, low-stock alert, and its stock history. Open to all staff; the edit form moved to `/stock/{id}/edit` (managers and secretaries). |

**Why**
- **"Today" is decided in Manila time everywhere** (server and screens), so a phone with the wrong time zone still shows the right day. The zone is set twice, `STORE_TIMEZONE` (api) and `STORE_TZ` (`web/src/lib/dates.ts`); change both together.
- **History clears the list when loading fails**, so the error isn't shown above rows from the previous filter.
- **Needs review** catches photos that were scanned and then forgotten, which would otherwise mean missing stock or sales.

## Audit fixes

- **A product's base unit can't change once stock has moved.** Stock movements and sale lines store a quantity but not its unit, so after a change the history showed "+10 roll" as "+10 m" and best sellers added rolls and metres together. `PATCH /products/{id}` with a new `base_unit` is now a 409 if the product has stock or any movement or transaction line ("Archive this product and add a new one with the new unit"); the old "bring stock to 0 first" advice was a dead end, since reaching 0 takes a movement. The check locks the product row first, so a sale saving at the same moment can't slip past it. A product that never moved can still change it.
- **Extreme dates** (before 2000, after 2100) are a 422 instead of a 500.
- **Today vs yesterday** compares the same part of the day (see Step 1). Home shows the API's `compared_to` under the number ("2 sales today · same time yesterday ₱500").
- **History** doesn't show stale rows under an error.
- **Needs review** lists failed reads too, with a "Failed" badge, and shows "50+" only when the API says more were left out (`has_more`; exactly 50 shows "50"). The web no longer keeps its own copy of the 50 limit.

Tests: `test_base_unit_cannot_change_after_stock_has_moved`, `test_base_unit_can_change_before_any_movement` (`test_products.py`); `test_extreme_dates_are_422_not_500`, `test_earliest_and_latest_allowed_ranges_work`, `test_today_is_compared_with_yesterday_up_to_the_same_time`, `test_unfinished_range_is_compared_up_to_the_same_point`, `test_week_so_far_is_compared_with_last_week_up_to_the_same_weekday_and_time`, `test_month_so_far_is_compared_with_last_month_up_to_the_same_day_and_time`, `test_scans_to_review_includes_failed_reads`, `test_scans_to_review_skips_failures_that_cant_be_retried`, `test_scans_to_review_includes_reads_stuck_in_pending`, `test_scans_to_review_says_when_there_are_more` (`test_reports.py`); `test_base_unit_change_with_stock_gives_the_archive_advice`, `test_base_unit_change_waits_for_a_stock_save_in_progress` (`test_products.py`).
