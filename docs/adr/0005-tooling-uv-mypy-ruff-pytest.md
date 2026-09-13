# ADR 0005: Tooling — uv, mypy --strict, ruff, pytest, yoyo-migrations

**Status:** Accepted
**Date:** 2026-09-13

## Context

The charter mandates "type safety everywhere" (Python: full type hints + mypy/pyright strict mode) and "config over code," and requires migrations to be "written and tested before the schema that needs them ships." Several tools can satisfy each of these; this ADR fixes one choice per concern so the project doesn't carry dual-config drift (e.g. both mypy and pyright configured as CI gates, silently disagreeing).

## Decision

- **Dependency manager:** `uv` (with `pyproject.toml` + `uv.lock`). Not currently installed on the dev machine — installing it is setup step 0.
- **Type checker (CI-enforced gate):** `mypy --strict`. Pyright/Pylance remains available for editor-side live feedback (VS Code's default), but only `mypy --strict` is the enforced CI gate.
- **Test framework:** `pytest` + `pytest-asyncio` (all repository and tool-handler methods are async) + `pytest-cov`.
- **Lint/format:** `ruff` (single tool covering what black + isort + flake8 previously required separately).
- **Migrations:** `yoyo-migrations`, running raw `.sql` files, tracked via its own applied-migrations table.

## Rationale

**uv over Poetry/pip-tools:** faster dependency resolution, a single lockfile format, and has become the de facto standard for new Python projects as of 2026 — no ecosystem-compatibility reason to prefer Poetry here since this project has no existing Poetry-based dependency.

**mypy over pyright as the CI gate:** both are capable strict type checkers; the decision is about avoiding *two* enforced configs that could silently diverge (mypy passing while pyright fails, or vice versa) rather than a claim that mypy is categorically superior. mypy's per-module strictness overrides (`[[tool.mypy.overrides]]`) give finer-grained control if a future third-party dependency lacks type stubs. Pyright still runs in the editor for fast feedback — it's just not the gate that blocks a merge.

**yoyo-migrations over Alembic:** Alembic is built around SQLAlchemy models and its autogenerate machinery diffs ORM model state against the DB — this project has no ORM (the repository pattern talks to `asyncpg` directly, per ADR 0003), so Alembic's main value proposition doesn't apply, and using it without an ORM means writing everything by hand anyway while still carrying Alembic's SQLAlchemy dependency and config surface. yoyo-migrations does the one thing actually needed — track and apply raw SQL migration files transactionally — with a much smaller footprint.

## Alternatives considered

- **Poetry.** Rejected: slower resolver, no clear benefit over uv for a greenfield project.
- **Pyright as the sole CI gate instead of mypy.** Viable alternative; mypy chosen for per-module override granularity, not a strong technical requirement either way — revisit if the team's day-to-day editor tooling makes pyright parity more valuable in practice.
- **Alembic.** Rejected per rationale above — fights the no-ORM design.
- **Hand-rolled migration runner.** Rejected: yoyo already solves "track applied migrations transactionally" correctly; reinventing it adds risk for no benefit.

## Consequences

- `pyproject.toml` declares `mypy`, `ruff`, `pytest`, `pytest-asyncio`, `pytest-cov`, `yoyo-migrations`, and `mcp` as dependencies/dev-dependencies, managed via `uv`.
- CI (`ci.yml`) runs `ruff check .`, `mypy --strict src/`, and `pytest` as separate, clearly-attributed steps.
