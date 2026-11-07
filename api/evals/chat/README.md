# Chat evals: does the AI pick the right report?

`tests/test_chat*.py` use a scripted model. This folder checks the **real** model: for each question in `cases.json`, does its first tool call use the right tool with the right arguments?

| File | What it is |
|---|---|
| `cases.json` | 20 questions (English, Tagalog, Taglish), each with the expected tool and arguments. |
| `run_chat_eval.py` | Asks the model each question once and prints the score. |
| `scoring.py` | How a call is compared with the expectation (tested in `tests/test_chat_eval_scoring.py`). |

## Run it

```bash
cd api
uv run python -m evals.chat.run_chat_eval
```

Options: `--case tg-` runs only ids containing "tg-"; `--verbose` shows every call.

It needs an API key (`ANTHROPIC_API_KEY` in `api/.env`) and costs a little (one short call per question; the total is printed). No database is needed: tools are not run.

## Reading the results

```
case                        tool  args  expected -> got
en-sales-today                ok    ok  sales_summary
tg-voids-week                 ok    --  stock_movements -> stock_movements({'kind': 'void'})

Right tool:              20/20 (100%)
Right tool + arguments:  19/20 (95%)
```

- **tool**: the first call used the expected tool (or no tool, for off-topic questions).
- **args**: and its arguments match after the tool's defaults are applied (no dates on `sales_summary` / `top_products` means today, so both count). In the example above the model forgot the dates.

Run it after changing the system prompt (`app/insights/prompts/chat.md`), a tool's description or inputs (`app/insights/chat_tools.py`), the model, or `AI_CHAT_EFFORT`. Compare with the last run before keeping the change.

## Add a case

Add an object to `cases` in `cases.json`:

```json
{"id": "tg-sales-monday", "question": "Magkano benta noong Lunes?",
 "expect": {"tool": "sales_summary", "args": {"start": "2026-11-02", "end": "2026-11-02"}}}
```

- Dates are relative to `today` in the file (Friday 2026-11-06).
- `args`: only the arguments you list are checked.
- `query_contains` (for `find_product`): the search text must contain this.
- `"tool": null`: the model should answer without a tool (off-topic questions).
- Optional `"role": "member"` (default `manager`).
