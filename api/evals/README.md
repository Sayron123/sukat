# Evals: how well does the AI read real lists?

Unit tests use a fake AI. This folder checks the **real** model on **real photos**, so you can see if a prompt or model change makes reading better or worse.

## What's here

| File | What it is |
|---|---|
| `cases/` | Your test photos and the answer for each one. |
| `run_eval.py` | Reads every photo with the AI and prints accuracy. |
| `scoring.py` | How a read line is compared with the expected line (tested in `tests/test_eval_scoring.py`). |

## Add a case

1. Take a photo of a real list (delivery receipt, handwritten order). Save it as `cases/<name>.jpg` (`.png` and `.webp` also work). Use names like `dr-001-handwritten.jpg`.
   - Remove or cover customer names, phone numbers, and addresses first.
   - Keep it under 5 MB. A phone photo resized to about 1600 px is what the app sends.
2. Write the right answer as `cases/<name>.json` (same name):

```json
{
  "type": "stock_in",
  "lines": [
    { "product": "portland-cement-40kg", "qty": 10, "unit": "bag" },
    { "product": "common-wire-nail-4in", "qty": 2, "unit": "box" },
    { "product": "new:Deformed Bar 32mm x 6m", "qty": 5, "unit": "pc" }
  ]
}
```

- `type`: `"stock_in"` (delivery list) or `"sale"` (sales receipt / order slip). Both types are read with the same prompt (`app/ai/prompts/scan_read.md`); only sales skip suggesting new products.
- `product`: the item's `key` from `app/products/seed_catalog.json` (or its exact name). Use `"new:<name>"` for an item that isn't in the catalog: the right answer is then "no match".
- `qty` and `unit`: **as written on the list** (2 box, not 50 kg).
- List the lines in the order they appear. Leave out totals and other non-item rows.

- `unit_price` (optional, best for sales): the price **per unit as written**, in pesos. Use `null` when no price is written (the AI must then return none, not guess). Leave it out to not score price for that line.

`cases/_example.json` (stock in) and `cases/_example_sale.json` (sale) show the format. They have no photo, so they're skipped.

### Sale receipts

Use real receipts from the store: handwritten resibo, printed delivery receipts, customer order slips. Name them `sale-001.jpg` + `sale-001.json` with `"type": "sale"`. For an item the store doesn't carry, use `"new:<name>"`: on a sale the right answer is "no match" (sales never create products).

## Run it

```bash
cd api
uv run python -m evals.run_eval
```

Options: `--case dr-001` runs only matching cases; `--type sale` runs only sale receipts; `--verbose` prints every wrong line.

It needs an API key (`ANTHROPIC_API_KEY` in `api/.env`), and **each run costs money**. The total cost is printed at the end. The AI sees the whole starter catalog as the store's product list.

## Reading the results

The scan runs in three steps (see `docs/ai-scan-pipeline.md`): **read** the photo, **match** each line to a product, **check** the numbers. The report scores each step, so you can see where errors happen.

```
Provider: gemini, model: gemini-2.5-flash

case                       lines    read   match   final   price  miss extra AI req
dr-001 (in)                    8   87.5%  100.0%   87.5%       -     0     0    1.0
sale-001 (sale)                5  100.0%   80.0%   80.0%   80.0%     0     0    2.0
-------------------------------------------------------------------------------------
TOTAL stock_in                 8   87.5%  100.0%   87.5%       -     0     0    1.0
TOTAL sale                     5  100.0%   80.0%   80.0%   80.0%     0     0    2.0
TOTAL                         13   92.3%   92.3%   84.6%   80.0%     0     0    1.5

AI requests: 3 for 2 scans (1.5 per scan; 1 matched fully by code with 1 request)
Lines matched by code: 11/13, by AI: 1, not matched: 1
```

| Column | Meaning |
|---|---|
| `read` | Step 1: quantity and unit read right (spellings like `bx`/`box` count as the same). |
| `match` | Step 2: the right product (or correctly "not in catalog"). |
| `final` | Product, quantity and unit all right: the line needs no fixing. |
| `price` | The written price read right (only lines whose expected file gives `unit_price`). |
| `miss` | Lines on the photo the read step didn't return. |
| `extra` | Lines it returned that aren't on the photo (for example a total row). |
| `AI req` | AI requests per scan: 1 when every line matched by code, 2 when some went to the AI. |

A low `read` means the photo or `prompts/scan_read.md` is the problem; a good `read` with a low `match` means the glossary, the product's other names, `SCAN_FUZZY_THRESHOLD` or `prompts/scan_match.md`.

Read lines are paired with expected lines by product first, then by order. So one skipped line doesn't make every later line count as wrong.

## Tips

- Aim for 20+ cases with a mix: printed receipts, neat and messy handwriting, Tagalog/Taglish, angled and dim photos.
- Run the eval before and after changing a prompt (`app/ai/prompts/scan_read.md`, `scan_match.md`), the glossary, `SCAN_FUZZY_THRESHOLD`, `AI_PROVIDER` or the model. Keep a change only if `final` goes up, or stays the same at a lower cost.
- Compare providers: run once with `AI_PROVIDER=anthropic` and once with `AI_PROVIDER=gemini`.
- Don't edit the prompt to fix one photo; that usually breaks others.
