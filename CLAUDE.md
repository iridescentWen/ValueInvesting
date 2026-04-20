# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

AI agent for value investing. Dashboard-driven stock screener (PB/PE/ROE + value-investing indicators) with agent-generated subjective analysis, covering A-shares / US / HK markets.

Full design spec: `~/.claude/plans/ai-agent-wiggly-moon.md` — read this before substantive changes to understand the architectural intent and implementation phases.

## Repo layout

Monorepo with two independent sub-apps, each managing its own dependencies:

- `backend/` — FastAPI + Pydantic AI, managed by `uv`
- `frontend/` — Next.js 15 (App Router) + React 19 + TypeScript + Tailwind 4, managed by `npm`

There is **no root build system**. Always `cd` into the relevant sub-app to run commands.

## Ports (non-default — chosen to avoid conflicts)

- Backend: **8421** (FastAPI)
- Frontend: **8420** (Next.js)

`npm run dev` hard-codes `--port 8420`. The uvicorn command explicitly passes `--port 8421`. CORS on the backend whitelists `http://localhost:8420`.

## Common commands

### Backend (from `backend/`)

```bash
uv sync                                                  # install core deps
uv sync --extra cn                                       # add AkShare (A-shares / HK)
uv sync --extra us                                       # add yfinance (US)
uv run uvicorn app.main:app --reload --port 8421         # dev server
uv run pytest                                            # all tests
uv run pytest tests/test_health.py::test_health -v       # single test
uv run ruff check .                                      # lint
uv run ruff format .                                     # format
```

### Frontend (from `frontend/`)

```bash
npm install
npm run dev            # port 8420
npm run build
npm run typecheck      # tsc --noEmit
npm run lint
```

### Both at once

Use the VS Code / Cursor compound launch **"All: Backend + Frontend"** (see `.vscode/launch.json`), or run two terminals.

## Architecture — non-obvious pieces

### Agent framework: Pydantic AI, model-agnostic by design

- `backend/app/agents/base.py` exposes `build_agent(system_prompt, **kwargs)` — **all agent code must go through this factory**, not construct `Agent(...)` directly.
- The LLM is selected at runtime via the `LLM_MODEL` env var (e.g. `anthropic:claude-sonnet-4-6`, `openai:gpt-5`). Never hard-code provider/model strings.
- `settings.require_llm_key()` is called inside `build_agent` and fails fast if the key for the selected provider is missing.

### Data source abstraction

`backend/app/data/providers/base.py` defines `MarketDataProvider` (ABC) + Pydantic models for `Stock`, `DailyBar`, `Fundamentals`, `RealtimeQuote`. `market: ClassVar[Market]` (where `Market = Literal["cn", "us", "hk"]`) is how subclasses advertise their market.

**Business code must depend only on this ABC**, never on AkShare / yfinance / EDGAR directly — that lets us swap free data sources for paid ones without touching callers.

### Two data stores (planned)

- **Postgres** for OLTP: stock metadata, watchlists, user-defined screens
- **DuckDB** for analytical filtering: daily fundamentals snapshot as parquet, queried by the screener endpoint (~10x faster than Postgres for this workload)

Connection strings come from `.env` (`DATABASE_URL`, `DUCKDB_PATH`). Local Postgres is assumed — there is no Docker.

### Config

`backend/app/config.py` uses `pydantic-settings` with `.env` autoload. Notable:

- Every field has a default, including `database_url: str = ""`. Startup does **not** fail when `.env` is missing — callsites that need the DB must validate at use time.
- `cors_origins: list[str]` — in `.env`, this must be **JSON array format**: `CORS_ORIGINS=["http://localhost:8420"]`. Not comma-separated.

### Frontend / backend wiring

`frontend/lib/api.ts` is the single source of truth for `API_URL` and response types. Every page/component that calls the backend imports from here — do not sprinkle `fetch("http://...")` elsewhere.

Next.js fetches use `{ next: { revalidate: N } }` ISR by default. Avoid `cache: "no-store"` unless the endpoint truly requires per-request freshness.

## Secrets policy

`.gitignore` aggressively blocks all `.env*` variants except `.env.*.example` / `.env.sample` / `.env.template`, plus `*.pem`/`*.key`/`credentials*.json`/`*api_key*`/etc. Before committing, `git status` should never show any env or credential file. If it does, the `.gitignore` has a hole — fix the ignore, don't just skip-add.

## VS Code / Cursor

`.vscode/` is partially committed (launch, tasks, settings, extensions) and partially ignored (personal preferences). When adding shared config, add an explicit `!` exception to `.gitignore`.

Python interpreter is expected at `backend/.venv/bin/python` (set in `.vscode/settings.json`); run `uv sync` before opening the repo in VS Code so Pylance can resolve imports.
