# Phase 3 — What and why

Phase 3 lets staff **take a photo of a delivery list**. The AI reads it, staff check the lines, and saving adds the stock.

## Step 1 — Database tables

**What** (`api/app/inventory/models.py`, `api/app/ai/models.py`, migration `0004_inventory_scans.py`)

| Table | Purpose |
|---|---|
| `scans` | One photo: its storage key, `type` (sale / stock_in), `status` (pending → read / failed → saved), what the AI read, which model. |
| `transactions` | One saved event that changes stock (stock_in now; sale and adjustment later). Has `client_request_id`. |
| `transaction_items` | The lines: product, qty and unit as written, `qty_base` (in the product's base unit), price, line total. |
| `stock_movements` | Every stock change with `stock_after`: a history you can audit ("why is cement 13?"). Its link to the line is `(transaction_item_id, store_id)`, so it can never point at another store's line (migration `0005a`). |
| `ai_usage` | Every AI call: model, tokens in/out, cost in centavos. |

**Ideas**
- **`UNIQUE(store_id, client_request_id)`** — the phone gives each save an id. The database refuses a second transaction with the same id, so a double tap or a retry after a dropped connection can't add stock twice.
- **Composite foreign keys `(id, store_id)`** on every child row — the database itself refuses a line that mixes two stores.
- **`stock_after` on each movement** — you can rebuild the stock history without trusting `products.stock_qty`.
- **`cost_centavos` has 4 decimals** — one AI read costs a fraction of a peso.

## Step 2 — Photo upload

**What**
- `POST /scans/upload-url` returns a **presigned PUT URL**: a link that allows exactly one upload, for a few minutes.
- `api/app/core/storage.py` — `R2Storage` (Cloudflare R2, via boto3) and `LocalStorage` (a folder, for development). Pick with `STORAGE_BACKEND` in `api/.env`.

**Ideas**
- **The phone uploads straight to storage**, not through our API. The API never handles big files.
- **The server makes the key** (`<store_id>/scans/<random>.jpg`). Every photo sits under its store's prefix, and `POST /scans` only accepts keys under the caller's store.
- **Type and exact size are part of the signature**, so the link can't be used to upload something else or something bigger.
- **Local mode works the same way**: the URL points to `PUT /uploads/local/...` on our API with an HMAC signature, expiry, and size check.
- **For R2:** create a bucket, an API token with Object Read & Write, and a CORS rule that allows `PUT` from your web app's origin.

## Step 3 — AI client

**What** (`api/app/ai/`)
- `base.py` — `VisionReader`: the interface ("read this photo against these products"). Another provider can be added without touching the rest of the app.
- `gemini_reader.py` and `anthropic_reader.py` — the Gemini and Claude implementations. Model, timeout and prices come from `api/.env`. See [ai-hardening.md](ai-hardening.md).
- `prompts/read_list.md` — the instructions for the AI, in a separate file so they're easy to improve.
- `schemas.py` — the shape of the answer, checked with Pydantic.
- `usage.py` / `pricing.py` — save tokens and cost to `ai_usage`.

**Ideas**
- **Structured output** — the API forces the answer to match our JSON schema, and Pydantic checks it again. A bad answer becomes a "Try again" message, never a crash.
- **Short product refs (`P12`) instead of UUIDs** — fewer tokens, and an invented ref simply matches nothing.
- **The product list is cached** (prompt caching), so repeat scans in a store cost less and start faster.
- **Timeout + 1 retry**, and clear errors: "took too long, try again" vs "couldn't read this photo".
- **Refusal fallback** — if a safety filter declines a photo, the API retries on another model automatically.
- **Cost is logged even when reading fails**, because tokens were still used.

## Step 4 — Scan API

**What** (`api/app/inventory/scans.py`, `scan_service.py`)
- `POST /scans` (any staff member) reads the photo and returns lines.
- `GET /scans/{id}` and `POST /scans/{id}/retry`.

Each line gets `qty_base` (converted with Phase 2's `convert()`, e.g. 2 box nails = 50 kg) and is marked **check** when:
- the AI's confidence is below 0.8,
- there's no matching product (or it's a new one),
- the quantity is unclear (`no_qty`),
- **no unit was written** (`no_unit`) — the unit is never guessed from the product, because "2 pako 4" could mean 2 kg or 2 boxes. `qty_base` stays empty until staff enter the unit, and the line can't be saved without one,
- the unit can't be converted for that product (`unknown_unit`), or
- the quantity is too small for the base unit (`qty_too_small`).

**Ideas**
- **Sending the same photo again returns the same scan** — no second AI charge if the phone retries.
- **The file's first bytes are checked** to be a real JPEG/PNG/WebP before it goes to the AI.
- **The AI call runs outside any database transaction**, so a slow read never blocks other staff.
- **Lines are saved already matched to product ids**, and product names and conversions are filled in fresh every time the scan is shown.

## Step 5 — Saving stock in

**What** (`POST /transactions`, `api/app/inventory/stock_service.py`)

In **one** database transaction:
1. If this `client_request_id` was already saved, return that result and stop.
2. Insert the transaction row.
3. Create products marked "new" (managers and secretaries only).
4. **Lock** the product rows (`SELECT ... FOR UPDATE`).
5. Convert each line, insert items and movements, update `stock_qty`.
6. Learn aliases from corrected lines, and mark the scan "saved".

**Ideas**
- **Row locks prevent lost updates.** Without them, two saves at the same moment could both read 10, both add 5, and both write 15 (instead of 20).
- **Locks are taken in id order**, so two saves can't wait on each other forever (deadlock).
- **A repeat sent at the same moment** waits on the unique key and then gets the first save's answer.
- **Alias learning** — if a **manager or secretary** changes a line to another product, the item's written name (like "pakong 4 pulgada") becomes an alias. Next time the AI and the search find it. The text comes from the stored scan, not from the phone, and an alias that belongs to another product is never taken. A **member's** save never creates aliases (aliases change how every later scan matches, like editing a product), but the stock-in still saves.
- **Members can scan and save stock-in** for existing products. Only managers and secretaries can create products (same rule as Phase 2).

## Step 6 — Tests

`api/tests/test_transactions.py`, `test_inventory_access.py`, `test_scans.py`, `test_uploads.py`, `test_ai_client.py`. The AI is replaced by a fake in every test (no API key, no cost).

- **Duplicate `client_request_id`** — sent twice, sent with different content, and sent 4 times at once: stock is added once.
- **Concurrency** — 8 saves at the same moment add exactly 8, with `stock_after` 1, 2, …, 8.
- **Tenant isolation** — Store A can't read or retry Store B's scan, scan B's photo, read B's transaction, add stock to B's product, or save B's scan. The AI only sees the store's own products.
- **Member** can scan and save; can't create products.
- **Alias learning**, including never taking another product's alias, and members' saves teaching none.
- **No unit written** — the line gets `no_unit`, no `qty_base`, and can't be saved until a unit is entered.
- **Store-safe movement key** — the database refuses a stock movement that points to another store's line.

Each key safety check was tested by removing it on purpose: the matching test fails without it.

## Step 7 — Eval set

**What:** `api/evals/` — real photos with the right answers, and `run_eval.py`, which reads them all with the real AI and prints accuracy for product, qty, unit, and all three together. See `api/evals/README.md`.

**Why:** unit tests prove the code works; only real photos show whether the **AI** reads well. Run it before and after changing the prompt or model, and keep a change only if accuracy goes up (or stays the same for less money).

## Step 8 — Web: Scan Stock In

**What** (`web/src/app/scan/`)
1. **Take photo** (camera) or **Choose from gallery**.
2. The phone shrinks the photo to 1600 px on the long side, JPEG 70% (a 4 MB photo becomes about 300 KB), then uploads it.
3. **Reading list…** with **Retry** if the connection drops.
4. **Review**: each line has Qty + Unit and Price + Total. Unsure lines have a **red edge and "Please double check this line"** (with the reason) and an **Approve** button. New products have a **"New" tag**. Everything is editable; the product box searches your products.
5. **Save**, then a summary with the new stock for each item.

**Ideas**
- **Compressing on the phone** saves mobile data and upload time, and is still sharp enough for handwriting.
- **The `client_request_id` is made once when the review opens** and reused if Save is pressed again, so a save that went through before the connection dropped is not added twice.
- `crypto.randomUUID()` only works on HTTPS or localhost, so there is a fallback for testing on a phone over Wi-Fi.

## Running it locally

Add to `api/.env` (see `api/.env.example`):

```
ANTHROPIC_API_KEY=sk-ant-...
STORAGE_BACKEND=local
PUBLIC_API_URL=http://localhost:8000
```

Then run `uv run alembic upgrade head` in `api/`.

To test on your phone over the same Wi-Fi, use your PC's LAN address in **both** `PUBLIC_API_URL` (api) and `NEXT_PUBLIC_API_URL` / `API_URL` (web), and add the phone's web address (`http://<pc-ip>:3000`) to `CORS_ORIGINS`.

## Step 10 — Fixes from code review

| Problem found | Why it mattered | Fix |
|---|---|---|
| A retry could overwrite a scan that was already **saved**. | The saved scan's lines are the record of what arrived. Changing them after saving breaks the history. (A double save was only avoided by luck.) | Read results are written only if the scan is still pending or failed, checked under a row lock. Retry is allowed only after a failure. |
| A read that never finished (e.g. server restarted mid-read) stayed **"pending" forever**. | The phone kept polling with no Retry button. | A pending scan older than the longest possible AI call is shown as failed with Retry. |
| A save could start while a retry was reading. | The scan's lines could change under the save. | A retry sets the scan back to "pending", and saving needs "read". |
| **Quantity "10" showed as "1"** on the review screen (found in browser testing). | A delivery of 10 bags would have been saved as 1. | Trailing zeros are trimmed only after a decimal point. |
| A scan from another store got a confusing "conflict" error. | The database blocked it (good), but the message was wrong. | The scan is checked first and gets a clear "not found". |
| The stock service raised web (FastAPI) errors directly. | Business logic tied to the web layer, and fragile error matching in the endpoint. | Domain errors (`SaveError`, `NotFound`, `Conflict`, `ScanAlreadySaved`) mapped to HTTP in the router. |
| The local upload saved the file inside the async handler. | Blocking file writes stall other requests. | The write runs in the thread pool. |

**Known limits (not bugs):**
- **Reading runs inside the request.** A read can take up to about a minute and occupies one API worker. For many stores, move it to a background job; the phone already polls, so the screen won't need to change.
- **Very large photos use a lot of phone memory.** The phone decodes the full photo before shrinking it, which could be slow on old phones with 48 MP cameras.
