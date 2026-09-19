# Phase 6 Research Memo — Hardening, Ecosystem Adapters, Quality Evidence & Packaging

**Date:** 2026-09-19. Inputs: Phase 5 retro ("Limits worth stating", "Decisions to revisit in Phase 6"), ADR 0002/0028, installed `mcp` 2.2.0.

## What Phase 5 left open

- Security: no token expiry or rotation, no read-only scope, no rate limiting, no TLS, no health endpoint.
- Ecosystem: no REST facade, no export/import between deployments, and the capture hook example shells out to a DB-direct CLI that cannot serve a remote deployment.
- Quality: ranking weights, decay stability and trust reliabilities are provisional; ADR 0026's revisit trigger is a benchmark or real usage.
- Packaging: no container image or deployment recipe; ADR 0002 only labelled this phase "Ecosystem Integration".

The user chose all four themes and an HTTP-native exit proof with no measured number in the gate.

## Findings that shape the design

- The SDK's `custom_route` handlers are not covered by bearer auth, so a REST facade has to authenticate itself. Routing it through the same verifier and the same tool-call path means scopes, namespace authorization, rate limits and audit come for free instead of being reimplemented.
- `guarded` in `server.py` is already the one authorization point; scope and rate-limit checks belong there.
- Tokens are SHA-256 digests; rotation is replacing a digest, expiry is a timestamp checked in the verifier.
- The capture CLI opens the database directly. A hook that must work against a remote server has to go through the API with a token.
- Docker Desktop is broken on this machine (Phase 0), so container builds can only be verified in CI. That is stated, not hidden.

## Prior art and how it shapes decisions

- **Rate limiting:** a token bucket is the standard, small, testable choice; in-process is correct for a single node and is documented as such.
- **Portability:** a versioned, line-oriented bundle with a manifest and content digest is easy to diff and verify; embeddings are derived data and are excluded by default.
- **Retrieval evaluation:** recall@k, MRR and nDCG over a small labeled set. A small synthetic set can show direction, not absolute quality; that limit is written into the report.

## Open questions carried out

- Whether real usage supports changing any ranking default.
- OAuth/OIDC, distributed rate limiting and federation remain out of scope.
