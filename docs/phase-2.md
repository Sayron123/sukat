# Phase 2 — What and why

Phase 2 adds **products**: what a store sells, in which units, and the names staff use for them.

## Step 1 — Database tables

**What** (`api/app/products/models.py`, migration `0003_products.py`)

| Table | Purpose |
|---|---|
| `products` | One row per item a store sells: name, category, base unit, price, stock, low-stock level, archived. |
| `product_aliases` | Other names for a product, like `sem` for cement. Lowercase. |
| `unit_conversions` | Other units a product is sold in: `1 box = 25 kg`. |

**Ideas**
- **Base unit** — the one unit stock is counted in (nails: `kg`, cement: `bag`). Every sale or delivery is converted to it.
- **`price_centavos` is a whole number.** ₱125.50 is stored as `12550`. Whole numbers never have rounding errors; decimals in floating point do (0.1 + 0.2 = 0.30000000000000004).
- **`stock_qty` is `NUMERIC(12,3)`.** Exact decimals with 3 places, for things like 2.5 kg of nails or 0.125 gallons.
- **Every table has `store_id`.** Aliases and conversions point to `(product_id, store_id)` **together**, so the database itself refuses an alias that links Store B to Store A's product.
- **Unique per store:** two products in one store can't share a name (ignoring upper/lower case) or an alias. Different stores can use the same names.
- **Archive, don't delete.** Archived products are hidden but kept, so old sales still make sense.

## Step 2 — Starter catalog

**What**
- `api/app/products/seed_catalog.json` — 158 common Philippine hardware items in 10 categories, with about 3–6 aliases each (Tagalog, Taglish, short forms) and exact unit conversions. No prices.
- `api/app/products/catalog.py` — loads the file and checks it with Pydantic.
- `api/app/products/README.md` — what each field means and the rules for editing the file.
- `api/tests/test_catalog.py` — fails if a rule is broken (duplicate alias, bad category, …).

**Why**
- A new store can add 100+ products in one minute instead of typing each one.
- Aliases like `bakal 10mm` or `chb 4` match how staff really write orders, so search finds the right item.
- Only **exact** conversions are included. A rounded one (1 m of a 6 m rebar = 0.1666… pc) would make the stock count drift a little on every sale.

## Step 3 — Products API

**What** (`api/app/products/router.py`)

| Endpoint | Who | What it does |
|---|---|---|
| `GET /products` | everyone | List, 20 per page. `q` searches name and aliases, `category`, `low_stock`, `include_archived`, `page`. |
| `GET /products/{id}` | everyone | One product. |
| `POST /products` | manager, secretary | Create. |
| `PATCH /products/{id}` | manager, secretary | Change only the fields you send. Sending `aliases` or `conversions` replaces the whole list. |
| `POST /products/{id}/archive` / `unarchive` | manager, secretary | Hide / show again. |
| `GET /products/catalog` | everyone | Starter items, each marked `already_in_store`. |
| `POST /products/import` | manager, secretary | Copy chosen starter items into the store. |

**Ideas**
- **`stock_qty` can't be edited here.** Sending it is rejected with 422. Stock will change only through stock movements (deliveries, sales, adjustments) in a later phase, so every change has a record.
- **Exact matches first.** Searching `sem` lists Portland Cement (exact alias) before "Semi-Gloss" (contains "sem").
- **`%` and `_` in a search are plain text.** In SQL `LIKE` they are wildcards, so they are escaped.
- **Import is safe to repeat.** Items already in the store are skipped. An alias already used by another product is left off and reported.
- **404 for other stores' products**, same as staff in Phase 1.

## Step 4 — Unit conversion

**What** (`api/app/products/units.py`)

`convert(product, qty, unit)` returns the quantity in the product's base unit. It tries, in order:

1. Same as the base unit → no change.
2. The product's own conversion → `2 box` of nails = `50 kg`.
3. Standard metric → `500 g` = `0.5 kg`; also `ml`/`l` and `mm`/`cm`/`m`.
4. Metric into a product conversion → `500 ml` of paint = `0.5 l` = `0.125 gal`.

Otherwise it raises `UnitConversionError` with a message staff can read: which unit failed and which units are known.

**Ideas**
- **`Decimal`, not float**, so 100 g + 100 g + 100 g is exactly 0.3 kg.
- **Unit spellings are normalized**: `Kilos` → `kg`, `pcs` → `pc`, `sako` → `bag`, `kahon` → `box`. The API saves units in this spelling, so conversions always match.
- Mass, volume and length never mix: `kg` can't become `m`.
- It is a plain function with no database, so the tests are fast (`tests/test_units.py`).

## Step 5 — Tests

**What**
- `tests/test_products_access.py`:
  - **Isolation:** Store A gets 404 on Store B's product (get, edit, archive), doesn't see it in lists or alias search, and can't create into Store B by sending `store_id`.
  - **Roles:** a member can read but every write is 403. A secretary can write.
  - **Search:** by alias, partial, case-insensitive, with a category filter, exact match first.
  - **Pagination:** 45 products → pages of 20, 20, 5, in name order, no repeats.
- `tests/test_products.py` — create, update, archive, import, validation.
- `tests/test_units.py` — the conversion rules.

**Why:** these guard the rules that matter most. I checked them by removing the `store_id` filter on purpose: the isolation tests failed.

## Step 6 — Web screens

**What**
- `/stock` — product list: search box, category chips, red/amber **Low stock** badge, pages. Managers and secretaries see **Import** and **+ Add**, and can tap a product to edit it.
- `/stock/new` and `/stock/[id]` — add/edit form: name, category, base unit, price in pesos, low-stock level, other names, other units. Archive/unarchive button.
- `/stock/import` — starter items grouped by category with checkboxes and **Select all**. Items already in the store show **Added**.
- `web/src/app/api/backend/[...path]/route.ts` — a small **proxy**: the browser can't read the httpOnly token cookie, so it calls `/api/backend/products`, and the Next.js server adds the token and calls FastAPI. Only `products`, `catalog` and `auth/me` are allowed through.

**Ideas**
- **Mobile-first:** one column, 44px-tall buttons (easy to tap), category chips scroll sideways, the Import button stays at the bottom of the screen.
- **Prices are parsed as text, not floats:** `1,250.5` → `125050` centavos.
- **Search waits 300 ms after typing** so it doesn't call the API on every key.
- **Members get a read-only list.** The add/edit/import pages tell them they can't change products. (The API blocks them anyway; this just keeps the screen honest.)
- **Login and logout reload the whole page.** Next.js 16 keeps visited pages' state in memory for fast back/forward. Without a full reload, the next person on the same phone could briefly see the previous user's search results and buttons.

## Step 8 — Fixes from code review

| Problem found | Why it mattered | Fix |
|---|---|---|
| The proxy's allow-list could be skipped with `products/..%2F..%2Fstaff`. | Next.js decodes `%2F` inside a path segment, then `fetch()` resolves `..`, so the request reached `/staff`. | Each path segment must be plain letters, numbers, `-` or `_`. Anything else is 404. |
| Changing a product's base unit from `kg` to `g` turned **50 kg into "50 g"**, and "1 box = 25" now meant grams. | Stock and conversion factors are measured in the base unit, so they silently changed meaning. | Base unit can only change when stock is 0, and the conversions must be sent again in the same request. |
| `GET /products?page=10000000000000000000` crashed with a 500 error. | The offset overflowed the database's number type. | `page` is limited to 1–10,000 (422 above that). |
| A price above ₱20M gave a confusing error. | The form allowed 8 digits and the API message was technical. | Both now stop at ₱9,999,999.99 with a clear message. |
| Re-using the name of an **archived** product said only "already exists". | Archived products are hidden, so the user couldn't find the clash. | The message says it's archived and suggests unarchiving. Import reports "archived in store". |
| The search box had no length limit, but the API allows 80 characters. | Long text gave a technical error. | The input stops at 80 characters. |
