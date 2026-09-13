# ADR 0003: Storage access via a `typing.Protocol` repository, not direct driver calls

**Status:** Accepted
**Date:** 2026-09-13

## Context

The charter requires "everything is testable in isolation: no component may require the full stack running to unit-test its core logic." MCP tool handlers need to create/read/update/soft-delete memory records. The naive approach — importing `asyncpg` directly inside tool handlers — would make every handler test require a running Postgres container.

## Decision

Define a `typing.Protocol` named `MemoryRepository` in `src/rootmem/storage/protocols.py` with async methods: `create`, `get_by_id`, `get_by_key`, `update`, `soft_delete`, `search_text`. MCP tool handlers depend on this Protocol via constructor injection and never import `asyncpg` (or any Postgres-specific type) directly. Two implementations exist:

- `InMemoryMemoryRepository` (`storage/fakes/in_memory_repository.py`) — dict-backed, zero I/O, used in all unit tests.
- `PostgresMemoryRepository` (`storage/postgres/repository.py`) — `asyncpg`-backed, used in integration tests and production.

A single shared contract-test suite (`tests/unit/storage/contract.py`) is parametrized to run against both implementations, guaranteeing they behave identically from the caller's perspective.

## Rationale

This is the standard ports-and-adapters (hexagonal) pattern applied at the minimum scope Phase 0 needs — one port, two adapters. It directly satisfies NFR5 (Docker-independent testability) and keeps the storage layer swappable: a future `GraphRepository` (Phase 1) or a different vector-store backend can be added as a new adapter without touching tool-handler code, satisfying the charter's "don't let layers leak into each other" mandate (§8).

A single contract-test suite (rather than separate, hand-written test files per implementation) is the mechanism that actually prevents the two adapters from drifting apart in behavior — without it, "the fake behaves like the real thing" would be an untested assumption.

## Alternatives considered

- **Mock `asyncpg`/`psycopg` calls directly in handler tests.** Rejected: tests would assert on implementation detail (which SQL was called) rather than behavior (what the handler does), making them brittle to any query refactor and blind to actual behavioral bugs in the real repository.
- **Require real Postgres for all tests.** Rejected: directly violates NFR5 and makes the fast unit-test loop dependent on Docker being up.
- **A full repository framework / generic ORM-style base class.** Rejected as premature abstraction — a single `Protocol` with 6 methods is sufficient for Phase 0's needs; introducing a generic framework now would be solving a problem (multiple heterogeneous entity types) that doesn't exist yet.

## Consequences

- MCP tool handler functions take a `MemoryRepository` as a parameter (or are built via a factory that injects one), never construct their own DB connection.
- Adding the Phase 1 embedding-backed semantic search or the Phase 1 graph store means adding new Protocol methods or new Protocol interfaces respectively — additive changes, not restructuring.
