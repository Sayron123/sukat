# Pull requests

How changes go into `main`. Follow this in every session, so each PR is easy to check.

## One PR per end

- **Backend PR:** only files under `api/` (and backend docs). Branch name `api/<short-topic>`.
- **UI PR:** only files under `web/` (and UI docs). Branch name `web/<short-topic>`.
- If one piece of work touches both ends, split it into two PRs. Never mix `api/` and `web/` files in one PR.
- Docs go with the PR they describe. A doc that covers both ends (like this one) goes with the backend PR.
- Both branches start from an up-to-date `main`. Push `main` first if it is ahead of GitHub, so a PR only shows its own commits.

## When the UI needs the backend

- Say it in the UI PR under **Depends on**, with the backend PR's name.
- Merge the backend PR first.
- If the UI still works without the backend change (for example it falls back to an older field), say that too.

## Commits

- One commit per step, each with a short title that says what changed for the user or the code ("Crop the photo on the phone before upload").
- Tests pass at every commit.
- No code comments or docstrings are added (existing ones are updated when they would become untrue).

## Naming

Names should be short and obvious, not a whole sentence. Say what the thing is in two or three words and let the code around it explain the rest.

| Instead of | Use |
|---|---|
| `needs_email_confirmation` | `email_confirmation` |
| `_email_is_theirs` | `_email_proven` |

- Variables, fields, functions and API fields all follow this.
- Booleans don't need `is_`, `has_` or `needs_` when the name already reads as yes/no in context (`email_confirmation`, `archived`, `active`).
- Keep the words the app already uses (`store`, `scan`, `member`, `backup`), so the same thing has the same name everywhere.
- Test function names are the exception: they may read as a sentence, because they describe the behavior being checked.

## Checks before opening the PR

- Backend: `cd api && uv run pytest -q && uv run ruff check app tests && uv run ruff format --check app tests`
- UI: `cd web && npx tsc --noEmit -p . && npx eslint src && npm run build`
- AI changes (prompts, glossary, matching, models): run the eval and add an entry to `docs/ai-changelog.md` (see `api/evals/README.md`).

## Description format

Copy this into the PR description and fill it in. Write it so someone who didn't build it can check it.

```markdown
## What changed
- One line per change, in plain words (what the user or the API now does differently).

## Why
- The problem each change fixes, or who asked for it.

## How to check
1. Steps to see it working (screen to open, request to send, test to run).
2. What you should see.

## Depends on
- The other PR this needs first, or "Nothing".

## Tests
- Commands run and their result (for example "pytest: 736 passed").
- Anything not tested, and why.

## Not in this PR
- Related work left for later, so reviewers don't look for it.
```

## Merging

- The person who owns the repo reviews and merges. A session opens PRs but doesn't merge them unless the owner asks it to in the chat.
