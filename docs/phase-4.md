# Phase 4 — What and why

Phase 4 adds **sales**: take a photo of a receipt, check it, save it, and stock goes down. It reuses everything from Phase 3 (photo upload, AI reader, scan screens, the one-transaction save). Nothing is copied.

## Step 1 — Sale scans

**What**
- `POST /v1/scans` with `"type": "sale"`. Same endpoint and flow as stock in.
- `api/app/ai/prompts/read_sale.md` — the AI's instructions for receipts (Phase 3's prompt is now `read_stock_in.md`). The reader picks the file by scan type.
- `api/app/products/pricing.py` — the product's price for any unit.

**Rules for a sale line**
- **Existing products only.** If the AI suggests a new product anyway, the suggestion is dropped before saving the scan. A line with no match is marked **Check** ("No matching product").
- **No price written?** It uses the product's price **for that unit**. Nails at ₱85/kg with 1 box = 25 kg → 1 box = ₱2,125.
- **No unit written?** Nothing is guessed: the line is marked **Check** ("No unit written") with no price and no total until staff enter the unit. "2 pako 4" could be 2 kg (₱170) or 2 boxes (₱4,250).
- **Alias learning** works as in stock in, but only for managers and secretaries. A member's sale still saves.
- **A written price that differs** from the product's price gets the **"price differs"** warning, with the usual price shown. It's a warning, not a "Check": stores often give discounts.
- Stock-in prices are supplier costs, so they are never filled in or compared.

**Why one prompt per type?** A sale has different rules from a delivery (no new products, no guessing prices). Separate files can be improved and tested (with evals) without affecting each other.

## Step 2 — Saving a sale

**What:** `POST /v1/transactions` with `"type": "sale"`. It's the **same code** as stock in (`save_transaction` in `api/app/inventory/stock_service.py`), in one database transaction:
- Same `client_request_id` = same result. A double tap never sells twice.
- Products are locked (`SELECT ... FOR UPDATE`), so two cashiers selling at once both count.
- Each line adds a **negative** stock movement (−3 bags).
- Alias learning works the same as stock in.

**Negative stock**

If a sale would take any product below 0, the API answers **409** with `"code": "negative_stock"` and the list of products (stock now, stock after). Nothing is saved.

The phone shows the list. **Save anyway** sends the same request again with `"confirm": true` and the same `client_request_id`, which is safe because nothing was saved the first time.

**Why allow it at all?** Stores sometimes sell before the delivery is recorded. Refusing would stop the sale; silently allowing it would hide a mistake. Asking is the middle ground, and the stock history shows the negative number until the delivery is entered.

**Rounding:** a line priced from the product uses **exact quantity × base price**, rounded once. 500 g of ₱85/kg nails is ₱42.50; rounding the per-gram price first (₱0.09) would make it ₱45.00.

## Step 3 — Voiding

**What:** `POST /v1/transactions/{id}/void` (manager and secretary only). Also new: `GET /v1/transactions` (newest first) to find things later. Migration `0005` adds `voided_at`, `voided_by` and `stock_movements.is_reversal`.

In one database transaction:
1. Lock the transaction row. A second void at the same moment waits, then gets **409 "already voided"**.
2. Lock the products (same order as saving, so a void and a sale can't deadlock).
3. Add one **reversing** movement for every movement the transaction made. A sale's stock comes back; a stock-in's goes out again.
4. Set status `voided`, `voided_at`, `voided_by`.

**Why never delete?** The history must stay complete: "why is cement 10?" should always have an answer. A void is a new event that undoes an old one, like a correction entry in a notebook.

**Safety net:** the database allows only **one** reversal per line (unique `transaction_item_id + is_reversal`), so even a bug can't restore stock twice.

## Step 4 — Tests

`api/tests/test_sales.py`, `test_void.py`, `test_sale_scans.py`. The AI is a fake in all of them.

- A sale reduces stock (negative movements, correct totals).
- The same `client_request_id` never reduces stock twice.
- Negative stock needs `confirm` (and nothing is saved before it).
- A void restores stock exactly once, including 4 voids at the same moment.
- A member can't void; a secretary can.
- Tenant isolation: another store's product, sale, scan and void all give "not found".
- 6 sales of one product at the same moment all count.

Removing the negative-stock check or the void's row lock on purpose makes tests fail, so the tests really guard them.

## Step 5 — Evals

**What:** sale receipts can be added to `api/evals/cases/` with `"type": "sale"` and an optional `unit_price` per line (as written; `null` = no price written). `run_eval.py` reads each case with its own prompt, adds a **price** column, and prints totals for stock in and sales separately. `--type sale` runs only receipts.

**Why:** reading prices is new for the AI, and wrong prices cost money. The eval shows how often the written price is read right, before and after a prompt change. Add 20+ real receipts (cover names and phone numbers first).

## Step 6 — Web screens

**What**
- **Home: "Scan Receipt"** opens the camera straight away. Browsers only allow that from a direct tap, so the button is the file input. The photo is then handed to `/scan/sale`.
- **Review** is the same screen as stock in, with:
  - no "New" products;
  - a **"Price differs"** tag plus the usual price;
  - prices filled in from the product.
- **Not enough stock** opens a confirm dialog listing the products. "Save anyway" saves.
- **Success** shows the sale total, with "View details".
- **History** (`/transactions`) lists sales and stock-ins, with Sales / Stock in filters.
- **Detail** (`/transactions/[id]`) shows the lines and totals, with a **Void** button for managers and secretaries behind a confirm step. A voided sale shows who voided it and when.

**Ideas**
- One `ScanFlow` with a `mode` ("stock_in" or "sale") instead of two copies.
- A price the phone filled in from the product is sent as "no price", so the server uses its exact rule. This was found in testing: the screen showed ₱3,162.50 but ₱3,165.00 was saved, because the rounded ₱0.09/g was sent back as if written.
- The confirm dialog uses the browser's built-in `<dialog>` element (keyboard, focus and screen reader support for free).

## Step 8 — Fixes from code review

| Problem found | Why it mattered | Fix |
|---|---|---|
| A refused save (e.g. "not enough stock") kept its database locks until the request finished cleaning up. | "Save anyway" is sent right after, and would wait on those locks. | The service rolls back the moment it refuses (same for "already voided"). A test checks the product row is free while the refused request's session is still open. |
| "Scan Receipt" relied on the scan page mounting fresh to pick up the photo. | Next.js can keep a visited page alive; then the photo would be ignored. | The scan page listens for new photos, so it works either way. |
| The date formatter lived inside a page and another page imported it from there. | Pages shouldn't depend on each other. | Moved to `web/src/lib/format.ts`. |

Found and fixed earlier in this phase (by tests):
- A default-priced line **saved** for more than the review showed (₱45.00 vs ₱42.50).
- Small-unit totals were rounded twice.

**Known limit:** voiding a scanned sale leaves its scan marked "saved", so the same photo can't be saved again. To redo a voided sale, take a new photo.

## Update — brought up to date with main

Phase 4 was updated with the audit fixes already in `main` (H1, H2, M1, M3):
- Both prompts (`read_stock_in.md`, `read_sale.md`) return an empty unit when none is written; `pricing.py` no longer falls back to the base unit.
- Members' saves (stock in and sales) never create aliases.
- Phase 4's `0005` (void) and main's `0005a` (store-safe line key) both came right after `0004`. They change different things, so neither was renamed: an empty merge migration `0006` joins them. A database at `0004`, `0005` or `0005a` upgrades with `uv run alembic upgrade head`.
