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

- `product`: the item's `key` from `app/products/seed_catalog.json` (or its exact name). Use `"new:<name>"` for an item that isn't in the catalog: the right answer is then "no match".
- `qty` and `unit`: **as written on the list** (2 box, not 50 kg).
- List the lines in the order they appear. Leave out totals and other non-item rows.

`cases/_example.json` shows the format (it has no photo, so it's skipped).

## Run it

```bash
cd api
uv run python -m evals.run_eval
```

Options: `--case dr-001` runs only matching cases; `--verbose` prints every wrong line.

It needs an API key (`ANTHROPIC_API_KEY` in `api/.env`), and **each run costs money**. The total cost is printed at the end. The AI sees the whole starter catalog as the store's product list.

## Reading the results

```
case                      lines  product     qty    unit   all 3  miss extra
dr-001-handwritten            8   87.5%  100.0%  100.0%   87.5%     0     0
```

| Column | Meaning |
|---|---|
| `product` | Matched the right catalog product (or correctly said "not in catalog"). |
| `qty` | Read the exact quantity. |
| `unit` | Read the right unit (spellings like `bx`/`box` count as the same). |
| `all 3` | Product, qty and unit all right: the line needs no fixing. |
| `miss` | Lines on the photo the AI didn't return. |
| `extra` | Lines the AI returned that aren't on the photo (for example a total row). |

Read lines are paired with expected lines by product first, then by order. So one skipped line doesn't make every later line count as wrong.

## Tips

- Aim for 20+ cases with a mix: printed receipts, neat and messy handwriting, Tagalog/Taglish, angled and dim photos.
- Run the eval before and after changing `app/ai/prompts/read_list.md`, `AI_MODEL`, or `AI_EFFORT`. Keep a change only if `all 3` goes up, or stays the same at a lower cost.
- Don't edit the prompt to fix one photo; that usually breaks others.
