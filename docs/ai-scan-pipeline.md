# AI scan pipeline — What and why

Reading a photo of a delivery list or receipt now takes **three steps** instead of one AI call that did everything:

```
photo ──► 1. read (AI) ──► 2. match (code, then AI for leftovers) ──► 3. check (code) ──► review screen
```

Each step's output is saved on the scan (`scans.ai_result_json` → `steps`), so when a line comes out wrong you can see which step made the mistake.

## Step 1 — Gemini adapter (and provider choice)

**What**
- `app/ai/base.py`: a `ScanAI` interface with one method per AI step (`read_photo`, `match_items`). The rest of the pipeline is plain code and doesn't know which AI it talks to.
- `app/ai/gemini_reader.py`: the Gemini version, on Google's official `google-genai` SDK. `app/ai/anthropic_reader.py`: the Claude version.
- `AI_PROVIDER=gemini` or `AI_PROVIDER=anthropic` in `api/.env` picks one, and `AI_MODEL` names its model. If `AI_FALLBACK_PROVIDER` is set and the main provider cannot read the photo, the whole scan runs again on the backup (see `docs/ai-hardening.md`).
- Every AI request is logged to `ai_usage` (`scan_read`, `scan_match`), priced with **that provider's** prices (`AI_PRICE_*` for the main provider, `AI_FALLBACK_PRICE_*` for the backup).

**Why**
- **Structured output (a JSON schema)** means the AI must answer in the exact shape we expect; Pydantic checks it again.
- **Thinking is off** (Gemini 2.x) **or at its lowest level** (3.x: `MINIMAL`; Pro models: `LOW`). Copying text and picking from a list don't need reasoning, so this keeps scans fast and cheap.
- **Switching provider is one setting**, so you can compare quality and cost with the evals.

## Step 2 — Read

**What:** `prompts/scan_read.md`. The AI gets **only the photo** and returns each row as written: `raw_text`, `qty_text`, `unit_text`, `price_text`, `total_text`, and a `confidence` from 0 to 1.

**Rules:** copy exactly (keep "sem", "bx", "1/2"), never invent an item or a price, and use null with low confidence for anything unreadable. Three short Taglish examples show this.

**Why**
- **No product list here.** The AI can't "fix" a row into a product that isn't there, and the prompt stays small.
- **Copying, not interpreting,** is what AI vision does best. Everything that needs rules (units, math, matching) moves to code, where it is predictable and tested.
- **`total_text`** is the line's written amount, kept apart from the unit price so step 3 can check the math.

## Step 3 — Match

**What** (`app/ai/scan_match.py`, `prompts/glossary.json`, `prompts/scan_match.md`)
1. **Take the item part of the row:** "10 bags sem @250 2,500" → "sem".
2. **Normalize it:** lowercase; sizes cleaned (`4"` and "4 pulgada" → "4"); short forms from the glossary ("sem" → "semento", "bkl" → "bakal", "chb" → "hollow block"). Product names and aliases get the same treatment, so both sides compare fairly.
3. **Exact match** on a product name or alias.
4. **Fuzzy match** (rapidfuzz) if no exact match. It must score at least `SCAN_FUZZY_THRESHOLD` (90), clearly beat every other product, and must not add a size the product doesn't have ("bakal 14mm" never becomes the 10mm bar).
5. **Only the lines still unmatched go to one AI call**, with the store's product list. It must answer an id from the list, or null. Ids not in the list are ignored.

**Why**
- **Most lines match by code:** free, instant, and the same every time. A scan where every line matches by code makes **only 1 AI request**.
- **The AI is used only for the hard cases** (spelling, Tagalog, unusual names), and it can't invent a product.
- **The glossary is a plain file:** add a short form your store sees, and every scan benefits.
- **If the match call fails,** the scan still works: those lines are simply unmatched for staff to pick.

## Step 4 — Check

**What** (`app/ai/scan_check.py`, code only)
- **Turn text into numbers:** "1/2" → 0.5, "1 1/2" → 1.5, "@250" → ₱250.00, "= 2,500" → ₱2,500.00.
- **Units:** cleaned with the glossary ("pcs" → pc, "kls" → kg), then converted with the products' own units (`convert()`).
- **Math:** quantity × price is compared with a written line total (within `SCAN_TOTAL_TOLERANCE_CENTAVOS`, ₱1, since totals are often rounded). If only a total is written, the unit price is worked out from it.
- **A line is marked "check" when:**
  - confidence is below 0.8
  - no product matched
  - there's no quantity or no unit
  - the unit can't be converted
  - the quantity is too small
  - **the math doesn't match** (new: "Total doesn't match qty × price")

**Why**
- **Code can't make up numbers,** and its rules are tested.
- **The math check catches misread digits:** if 10 × ₱250 doesn't equal the ₱2,600 written, one of those numbers was read wrong. Staff see "Check" on that line.
- **The review screen runs the same check** (with the products as they are now), so what staff see and what was stored never disagree.

**On the review screen**
- A photo where the AI finds no items is not kept: the scan is deleted and staff are asked for a clearer photo. Its AI cost is still logged.
- The trash button beside the title removes every item that isn't in the store's products (after a confirm). **Scan again** beside Save reads the photo once more (`POST /scans/{id}/rescan`, once per photo) and replaces the lines.
- A new item's name is a normal input box. While typing, existing products with a similar name are offered to use instead.
- **Needs review** has a **Delivery | Sale** filter at the top. It only chooses which photos are listed: a photo keeps the type picked before the camera opened.

## Step 5 — Evals

**What:** `uv run python -m evals.run_eval` now reports each step:

| Column | Step |
|---|---|
| `read` | quantity and unit right (step 1) |
| `match` | product right (step 2) |
| `final` | all three right |
| `AI req` | AI requests per scan (1 = everything matched by code) |

It also counts how many lines were matched by code, by the AI, or not at all.

**Why:**
- **Find where errors come from.** A low `read` points at the photo or the read prompt; a good `read` with a low `match` points at the glossary, the products' other names, the threshold, or the match prompt.
- **Compare providers.** Run once with `AI_PROVIDER=anthropic` and once with `gemini`.

## Step 6 — Tests

All with a mocked AI (no key, no cost):
- `tests/test_scan_pipeline.py`:
  - glossary, exact and fuzzy matching
  - only unmatched lines going to the AI
  - 1 request when code matches everything
  - the math check and every check reason
  - steps stored on the scan, and one `ai_usage` row per request
- `tests/test_scan_ai_providers.py`:
  - both providers' requests, thinking setting, usage and errors
  - choosing the provider, and cost per provider

## Settings (`api/.env`)

| Setting | Default | What |
|---|---|---|
| `AI_PROVIDER` | `gemini` | `gemini` or `anthropic`, for scans and chat |
| `GEMINI_API_KEY` | (empty) | Google AI Studio key (hidden in logs, like the other keys) |
| `SCAN_FUZZY_THRESHOLD` | `90` | lowest fuzzy score that counts as a match (0-100) |
| `SCAN_TOTAL_TOLERANCE_CENTAVOS` | `100` | how far qty × price may be from a written total |
