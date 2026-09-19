# ADR 0040: Container packaging, verified in CI rather than locally

**Status:** Accepted
**Date:** 2026-09-19

## Context

There is no deployment recipe. Docker Desktop is broken on the development machine (Phase 0), so an image cannot be built or run here.

## Decision

Ship a `Dockerfile` (python 3.13-slim, non-root, healthcheck on `/healthz`), `deploy/docker-compose.prod.yml` (server, pgvector Postgres, and a TLS reverse proxy), and `docs/operations.md`. A CI job builds the image and smoke-tests `/healthz` against a service Postgres. The retro states that the image was never built locally.

## Alternatives considered

- Skipping packaging: declined by the user's theme choice.
- Claiming it works untested: rejected.

## Consequences

The first real build happens in CI on the pushed commit; a failure there is a Phase 6 defect to fix before the tag is trusted.
