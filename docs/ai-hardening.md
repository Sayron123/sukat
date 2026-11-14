# AI hardening

This page explains how Sukat keeps its AI features working, and how it keeps their cost under control.

The AI does two jobs:

- **Photo reading:** it reads a photo of a receipt or delivery list.
- **The AI assistant (chat):** it answers questions about sales and stock.

## 1. Choosing the AI provider

The setting `AI_PROVIDER` picks who answers first. It can be `gemini` or `anthropic` (Claude).

The default is Gemini, with the model `gemini-3.1-flash-lite`.

Both providers do both jobs, and the rest of the app does not care which one is used. Photo reading runs in three steps: read, match, check (see `docs/ai-scan-pipeline.md`). If the read step fails, all the steps run again on the backup. If only the match step fails, just that one request goes to the backup. Chat uses the same tools, the same role limits and the same tests on both.

| Job | Gemini file | Claude file |
| --- | --- | --- |
| Photo reading | `api/app/ai/gemini_reader.py` | `api/app/ai/anthropic_reader.py` |
| Chat | `api/app/ai/gemini_chat.py` | `api/app/ai/anthropic_chat.py` |

Role limits are not left to the AI. The server checks the role when a tool runs, so a member who asks for a manager's report gets "not allowed", whichever provider is answering.

### Thinking

Thinking costs money, because Google charges it as output. Sukat sets `AI_GEMINI_THINKING_LEVEL=minimal`, the lowest level. Gemini 3 models cannot switch thinking fully off.

## 2. The backup provider

The setting `AI_FALLBACK_PROVIDER` picks the backup and `AI_FALLBACK_MODEL` its model. The provider can be `none`, `gemini` or `anthropic`. The backup may be the **same provider with a different model**, for example `gemini-3.1-flash-lite` as the main model and `gemini-3.5-flash-lite` as the backup. Each Gemini model has its own free-tier limit, so a second model also helps when the first one hits its limit (429). Only the exact same provider and model is refused.

The backup gets **one try** when the main provider:

- takes too long (timeout) or cannot be reached,
- is busy (error 429),
- has a server problem (error 5xx),
- returns an answer that does not pass validation.

The backup is **not** used when the problem would not change on a retry:

- the provider refuses the photo or question for safety reasons,
- the list is too long for one photo,
- the API key or settings are wrong (errors 400, 401, 403, 404).

### How a photo falls back

The photo is sent to the backup. If the backup also fails, staff see the normal "failed" screen with a Retry button.

The **match** step (the AI call for rows code couldn't match) has its own one-time backup: if it fails in a way a retry may fix, the same rows and product list go to the backup model. If that fails too, the scan still works and those rows are left for staff to pick. Each call that spent tokens gets its own `scan_match` row in `ai_usage`, and `steps.match.by_backup` on the scan says when the backup answered.

### How a chat question falls back

The **whole question starts again** on the backup. Sukat does not switch providers in the middle of a question, because each provider's replies only make sense to itself. This is safe because chat tools only read data.

Each provider gets its own 45-second limit, so in the worst case a question can take about 90 seconds.

### Retries on the same provider

When a backup is set, the main provider is not retried first. It goes straight to the backup, so people do not wait too long. With no backup, photo reading retries on the same provider `AI_MAX_RETRIES` times.

## 3. What gets logged

Every AI cost is saved in the `ai_usage` table. The new `provider` column says who did the work.

| Situation | What is saved |
| --- | --- |
| Main provider answers | One row with the main provider |
| Backup answers, main spent nothing | One row with the backup provider |
| Backup answers a photo, main spent tokens first | Two rows with feature `scan_read`, one per provider |
| Backup answers a chat, main spent tokens first | The `chat` row has the backup. The main provider's cost is in a `chat_failed_attempt` row |

The `chat_failed_attempt` row exists so a fallback still counts as one question in the 30-per-hour limit, while its cost still counts in the budget.

The main and backup models have separate price settings: `AI_PRICE_*` and `AI_FALLBACK_PRICE_*`. Each row is priced with the prices of the model that made it (the backup reader and chat mark their usage as backup, so this also works when both are Gemini).

## 4. The monthly budget

Each store has a monthly AI budget, in centavos.

- The default is `AI_MONTHLY_BUDGET_CENTAVOS=50000`, which is ₱500.
- To give one store a different limit, set `stores.ai_monthly_budget_centavos`. Empty means "use the default", and `0` means "no AI for this store". There is no screen for editing this yet.
- A month follows Manila time. It starts at midnight on the 1st.

Before each photo reading, retry and chat question, Sukat adds up this month's `ai_usage` cost for the store. If the total has reached the budget, the AI is **not called**. The person gets error 429 with the code `ai_budget_reached` and a message saying when the AI will work again.

Sending the same photo again still works, because it returns the saved result and costs nothing.

### Why a store can go slightly over

The cost of a call is only known after the call ends. Calls already running when the limit is reached will still finish. So a store can go over by the cost of those few calls, which is usually a few centavos.

### The usage screen

Managers can open **More → AI usage**. It shows this month's spending, the limit, what is left, and the split between photo reading and the assistant. Other roles do not see the menu item, and the server refuses them with error 403.

The API behind it is `GET /v1/insights/ai-usage`. The amounts are estimates based on the price settings and `USD_TO_PHP`.

## 5. Settings

| Setting | Default | What it does |
| --- | --- | --- |
| `AI_PROVIDER` | `gemini` | Who answers first |
| `AI_FALLBACK_PROVIDER` | `none` | Who answers if the first one fails (may be the same provider as `AI_PROVIDER` with another model) |
| `GEMINI_API_KEY` | empty | The Gemini key |
| `ANTHROPIC_API_KEY` | empty | The Claude key |
| `AI_MODEL` | `gemini-3.1-flash-lite` | The main model |
| `AI_FALLBACK_MODEL` | `gemini-3.5-flash-lite` | The backup model (same accuracy as the main model on the 2026-11-14 eval, its own free-tier limit) |
| `AI_GEMINI_THINKING_LEVEL` | `minimal` | How much Gemini thinks |
| `AI_PRICE_INPUT_PER_MTOK_USD` | `0.25` | Main model, input |
| `AI_PRICE_OUTPUT_PER_MTOK_USD` | `1.50` | Main model, output and thinking |
| `AI_PRICE_CACHE_WRITE_PER_MTOK_USD` | `0.25` | Main model, cache write. Gemini does not use it |
| `AI_PRICE_CACHE_READ_PER_MTOK_USD` | `0.025` | Main model, cached input |
| `AI_FALLBACK_PRICE_*_PER_MTOK_USD` | `0.30` / `2.50` / `0.30` / `0.03` | Backup model, same order |
| `AI_MONTHLY_BUDGET_CENTAVOS` | `50000` | Default budget per store per month |

Prices are in US dollars per one million tokens. The Gemini prices come from Google's pricing page and were checked on November 9, 2026. Update them when the model or the prices change.

## 6. How it is tested

The tests never call a real AI and need no API key. They are in `api/tests/test_ai_hardening.py`.

- **Fallback:** timeouts, 429, 5xx and invalid answers go to the backup. Refusals and bad settings do not. The backup is tried only once.
- **Budget:** the AI is not called when the limit is reached. Stores do not affect each other, and last month does not count.
- **Provider logging:** `ai_usage` shows who answered and prices each provider correctly.
- **Gemini:** Google's real SDK talks to a fake web server, so the real request format and error handling are tested.
- **Same chat tests:** every test in `test_chat.py` and `test_chat_safety.py` runs twice, once without a provider and once through the Gemini code.

## 7. After changing these settings

1. Run `uv run alembic upgrade head` in `api/`.
2. Add `GEMINI_API_KEY`, and set the provider, model and price lines in `api/.env` as shown in `api/.env.example`.
3. Try one photo and one chat question with the real keys.
