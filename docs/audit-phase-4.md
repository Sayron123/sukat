# Audit — Phase 4 (sales scan, negative stock, void)

Branch audited: `phase-4-sales-scan` (PR #7), compared with `main`.
Method: read every backend and web change, then confirmed each finding with a small test against the Phase 4 code. Existing suite: 214 passed.

## Summary

| ID | Severity | Finding | Status |
|---|---|---|---|
| P4-H1 | High | A sale line with no unit is counted and priced in the base unit, with no "Check" | Fixed |
| P4-M1 | Medium | Members' sales (and stock-ins) create product aliases | Fixed |
| P4-M2 | Medium | Any staff member can save a sale at any price (even ₱0), and nothing records it | Open |
| P4-M3 | Medium | Phase 4 conflicts with the audit fixes (#9): two migration heads, 2 file conflicts | Fixed |
| P4-L1 | Low | A sale line with no price saves as ₱0, without a warning | Open |
| P4-L2 | Low | After voiding, the same scan can't be saved again; the photo must be read again (AI cost) | Open |
| P4-L3 | Low | Reusing a `client_request_id` for another type returns the first transaction | Open |
| P4-L4 | Low | Any member can confirm a sale that takes stock below 0 | Decide |
| P4-L5 | Low | Voiding a stock-in after sales makes stock negative without a warning on screen | Open |
| P4-L6 | Low | Logged-out "Scan Receipt" loses the photo after the login redirect | Fixed by design PR #8 |

## High

### P4-H1 — Sale line with no unit is guessed as the base unit
**Where:** `api/app/ai/prompts/read_sale.md` and `read_stock_in.md` ("If no unit is written, use the matched product's unit"), `api/app/ai/convert.py` (fallback to `entry.base_unit`), `api/app/inventory/scan_service.py` (`line.unit or product.base_unit`), `api/app/products/pricing.py` (`unit or product.base_unit` in `price_per_unit` and `priced_line`).

**Proof:** a sale line "2 pako 4" with no unit, nails priced ₱85/kg:
`unit: "", qty_base: 2, unit_price: ₱85.00, total: ₱170.00, check_reasons: []`.
If the customer bought 2 boxes, the real sale is ₱4,250 and 50 kg. The review shows no "Check", so staff likely save it.

**Fix:** same as audit H1 on main, plus remove the fallback in `pricing.py`. With no unit: add `no_unit`, no `qty_base`, no default price, no total.

**Fixed:** both prompts, `convert.py`, `scan_service.py` and `pricing.py`. Tests: `test_sale_line_without_unit_gets_no_default_price`, `test_price_per_unit_never_guesses_an_empty_unit` (both fail without the fix).

## Medium

### P4-M1 — Members create aliases
**Where:** `stock_service.save_transaction` calls `_learn_alias` for every role and both types.
**Proof:** a member's sale, with the line changed from cement to nails, created the alias "pakong bakal".
**Fix:** same as audit M1: learn aliases only for managers and secretaries.

**Fixed:** applies to stock in and sales. Test: `test_member_sale_from_scan_learns_no_alias` (fails without the fix).

### P4-M2 — Sale price can be anything, with no record
**Where:** `TransactionIn.lines[].unit_price_centavos` is used as sent for sales; `transaction_items` stores only the final price.
**Proof:** a member saved 2 boxes of nails (usual ₱4,250) at ₱0. Saved with total ₱0. History shows a normal sale.
**Why it matters:** the "Price differs" warning exists only on the review screen. After saving, nobody can see that a sale was discounted, by how much, or by whom. This is how under-charging or theft would hide.
**Fix (pick one or both):**
- Store the product's price at the time (`expected_unit_price_centavos`) on each sale line, and show "Discounted" in history and on the detail page.
- Require a manager or secretary for prices below the product's price (or below a set percentage).

### P4-M3 — Merge conflicts with the audit fixes
**Where:** `api/app/inventory/models.py`, `api/tests/test_ai_client.py`; migrations `0005` (Phase 4) and `0005a` (#9) both revise `0004`.
**Fix:** after #9 merges, update the Phase 4 branch from main: rename `0005a` to `0006` with `down_revision = "0005"`, keep both the `(transaction_item_id, is_reversal)` unique key and the composite `(transaction_item_id, store_id)` FK, and apply P4-H1 and P4-M1.

**Fixed:** conflicts resolved, keeping both the `(transaction_item_id, is_reversal)` unique key and the composite FK. Instead of renaming `0005a` (a database already at `0005a` would then break), an empty merge migration `0006` joins `0005` and `0005a`. Tested upgrading from `0004`, `0005` and `0005a`.

## Low

### P4-L1 — Unpriced sale lines save as ₱0
A product with no price, and no price on the receipt: the sale saves with no price and adds ₱0 to the total (confirmed). The review doesn't ask for a price.
**Fix:** for sales, make a missing price a check reason (`no_price`), or block saving until a price is entered.

### P4-L2 — A voided scan can't be saved again
Void a wrong sale, then try to save the same scan corrected: 409 "This scan is already saved" (confirmed). Staff must upload the photo again, which costs another AI read.
**Fix:** when voiding, set the scan back to `read` so it can be corrected and saved again.

### P4-L3 — `client_request_id` reused for another type
A stock-in saved with id X, then a sale sent with the same id X: answer 200 with the stock-in (confirmed). The phone would think the sale was saved. Very unlikely (ids are random per review), but cheap to close.
**Fix:** if the existing transaction's type differs, return 409.

### P4-L4 — Members can confirm negative stock
Any member can tap "Save anyway". This may be what stores want (sell before the delivery is recorded). Decide; if not, require a manager or secretary for `confirm: true`.

### P4-L5 — Voiding a stock-in can make stock negative silently
Stock-in 5, sell 15, void the stock-in: stock becomes −5 (confirmed). This is the true count and is documented, but the void dialog doesn't say it.
**Fix:** show the stock after voiding in the confirm dialog when it goes below 0.

### P4-L6 — Logged-out "Scan Receipt"
On Phase 4's public home page, a logged-out user takes a photo, gets sent to login, and the photo is lost. The design PR (#8) makes Home a signed-in page, which removes this case.

## Checked and fine
- Tenant isolation: every query uses `current.store_id`; sale and void endpoints refuse other stores' ids.
- Idempotency: the same id saves once; a refused `negative_stock` save rolls back and the same id works with `confirm: true`.
- Locks: sales and voids lock products in id order (no deadlock); a second void waits and gets "already voided".
- Void keeps everything: reversal movements, `voided_at` / `voided_by`, check constraint between status and `voided_at`.
- Default sale price: total is exact base quantity × base price, rounded once.
- Web: the same request id is kept across reloads and the negative-stock confirm.
