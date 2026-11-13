# AI changelog

One entry per change to the scan or chat AI: prompts, glossary, units, matching code, thresholds, models. Each entry gives the eval numbers before and after (`uv run python -m evals.run_eval`, see `api/evals/README.md`) and the cost per scan.

Keep a change only if `final` goes up, or stays the same at a lower cost, and nothing else drops.

## 2026-11-13: first real case, units and matching fixes

Eval set: 1 real case (`dr-001`, a handwritten supplier invoice, 10 lines). One case is not enough to tune prompts or thresholds; these are bug fixes found on it. Model: `gemini-3.1-flash-lite`, no backup.

| Step | read | match | final | price | matched by code | AI req/scan | Cost/scan |
|---|---|---|---|---|---|---|---|
| Baseline | 90% | 100% | 90% | 100% | 0/10 | 2.0 | ₱0.22 |
| + `yrd` / `yd` / `yard` as a unit | 100% | 100% | 100% | 100% | 0/10 | 2.0 | ~₱0.22 (no change to AI input) |
| + keep sizes when cutting qty and unit out of a row | 100% | 100% | 100% | 100% | 2/10 | 2.0 | ₱0.15 |

- **Units**: `1yrd` was read correctly but not known as a unit. Added to `app/products/units.py`.
- **Match (code)**: on column-style rows (`Marine Plywood 3/4  3pcs.  1470  4.410`) `item_text` cut the qty "3" out of "3/4" and left a glued "3pcs." in, so the size guard refused every product and all lines went to the AI match call. Now the qty and unit are removed as a pair, and a lone qty never cuts a size (`3/4`, `2"`, `#240`).
- **Alias learning**: learned aliases now come from the clean item name, and a product the AI match step found is learned when staff keep it, so the same text matches by code next time. Not covered by the eval; covered by tests in `tests/test_transactions.py`.
- AI req/scan stays 2.0 on this case because 7 of its 10 items are not in the starter catalog, and those always go to the AI match call.
- Costs are from single runs and move a little between runs.

## 2026-11-13: first baseline, 21 real sales receipts

Eval set: 21 Sunrays / New Sunrays sales invoices (`sale-001` to `sale-021`, 156 lines, names covered), starter catalog, `gemini-3.1-flash-lite`, free tier. Two runs, same code:

| Run | read | match | final | price | miss | extra | AI req/scan | Cost/scan if paid |
|---|---|---|---|---|---|---|---|---|
| 1 | 94.5% | 71.9% | 68.5% | 100% | 0 | 4 | 2.0 | ₱0.20 (one failed read) |
| 2 | 94.2% | 76.9% | 73.1% | 100% | 0 | 3 | 2.0 | ₱0.13 |
| 3 (store header, address, TIN and footer also covered) | 94.9% | 79.5% | 75.0% | 100% | 0 | 3 | 2.0 | ₱0.13 |

- The two runs differ by about 5 points on match, so a change needs to beat that to count.
- Run 1: `sale-017` failed with MAX_TOKENS on a 10-line receipt (the model repeated itself); it read fine in run 2.
- Most wrong matches are Sunrays' own products (Omni Plug, Panasonic Outlet, Kopez Receptacle) against generic starter products (Male Plug, Convenience Outlet). Those labels can't be right or wrong without the store's real product list.
