# ROOTMEM

A human-brain-inspired, MCP-native agent memory system. This repository is
currently at **Phase 0 — Foundations**: a minimal MCP server exposing
`remember` / `recall` / `update` / `forget` / `search`, backed by
Postgres+pgvector, with a Redis connectivity smoke test alongside it.

See `docs/research/phase0-research-memo.md`, `docs/requirements/`, and
`docs/adr/` for the reasoning behind every non-obvious decision in this
phase, and the project's master execution prompt for the full multi-phase
charter this is Phase 0 of.

## Prerequisites

- Python 3.13
- [uv](https://docs.astral.sh/uv/) (`pip install uv` if not already installed)
- Docker Desktop (for local Postgres+pgvector and Redis)

## Setup

```bash
uv sync --all-extras --dev
cp .env.example .env   # adjust if needed
docker compose up -d
uv run python scripts/migrate.py
```

**If Docker isn't available**: the app talks to Postgres/Redis only through
config (`.env`), so a native install works too — run Postgres 17 and Redis
however you like, point `.env` at their host/port/credentials, then `uv run
python scripts/migrate.py`. `0001_init.sql` skips the pgvector extension
gracefully if it isn't installed (Phase 0 doesn't use it yet). See
`scripts/manual_recall_check.md`'s blocker note for the exact native setup
used during this project's own Phase 0 development.

## Running the MCP server

```bash
uv run python -m rootmem.integration.mcp.server
```

Serves over stdio — point your MCP client (Claude Code, Cursor, etc.) at
this command. See `scripts/manual_recall_check.md` for the exact
cross-session validation procedure used to sign off Phase 0.

## Development

```bash
uv run ruff check .          # lint
uv run mypy --strict src/ tests/   # type-check
uv run pytest tests/unit -v        # unit tests — no Docker required
uv run pytest -m integration -v    # integration tests — requires docker compose up -d + migrate.py
```

## Project layout

- `src/rootmem/storage/` — the `MemoryRepository` port (`protocols.py`) plus
  the in-memory fake and the Postgres implementation (ADR 0003).
- `src/rootmem/integration/mcp/` — the 5 MCP tools and the server that wires
  them onto stdio transport (ADR 0002).
- `src/rootmem/observability/` — per-operation latency/outcome logging.
- `src/rootmem/{capture,extraction,consolidation,trust}/` — empty module
  stubs reserved for later phases (see each directory's README), kept here
  now so those phases add files rather than restructuring the package.
- `docs/` — research memos, requirements, ADRs, and math specs, one set per
  phase, per the project's chained-SDLC charter.
