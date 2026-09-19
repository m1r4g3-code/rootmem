# Phase 6 Retrospective — Hardening, Ecosystem Adapters, Quality Evidence & Packaging

**Status:** Filled in after `v0.6.0-phase6`'s automated exit-criterion test (passed, 224-249s), 340 unit tests, the full integration directory (103 free tests plus every external file run one at a time, including the Phase 1-6 exit tests), and a live manual pass with a real client over HTTP (10/10) on 2026-09-19. **The container image and compose file have never been built here; only CI can verify them (see below).**

## What shipped

- **Hardening (ADR 0033-0035):** optional token expiry, `rotate` (old token dead immediately), `read`/`readwrite` scopes enforced before any tool body runs, a per-identity token-bucket rate limit, and an unauthenticated `/healthz` that reveals only a status. Migration 0010.
- **REST facade and client (ADR 0036):** `GET /v1/tools`, `POST /v1/tools/{name}`, authenticated with the same verifier and calling the same tool path as MCP, so scopes, namespace authorization, rate limits and audit are shared by construction. A standard-library Python client.
- **Namespace export/import (ADR 0037):** a versioned JSONL bundle with a manifest and content digest; a `PortabilityRepository` (Postgres + fake, one contract suite) exporting memories, graph with belief state and history, links, provenance and skills; import into an empty namespace with fresh ids, one `import` audit entry, digest verified before anything is written.
- **Claude Code hook (ADR 0038):** goes through the API with a token, so it works against a remote server.
- **Retrieval evaluation (ADR 0039):** metrics, a 30-memory / 15-query labeled set, recorded embeddings, an offline deterministic runner and a generated report.
- **Packaging (ADR 0040):** `Dockerfile`, production compose file with a TLS reverse proxy, `docs/operations.md`, an allowed-hosts setting so Host/Origin checking can be turned on, and a CI job that builds the image and smoke-tests it.
- 13 tools (unchanged count); ADRs 0033-0041.

## What the evaluation actually showed (read with its limits)

On the small synthetic set, nDCG@5 was 0.635 lexical, 0.882 semantic, 0.975 with Phase 4 multi-factor ranking. Multi-factor lifted freshness, trust and entity queries to 1.0 — **by construction, because the set was built so those signals matter**, so that is not evidence they matter in real use. The genuinely informative finding is a cost: on pure-semantic queries multi-factor scored 0.938 versus 1.000, because one correct answer (an ordinary-source, never-accessed memory, q06) was outranked by better-trusted, more-accessed near-misses. The weight grid saturated (many cells at 1.000), so the set cannot discriminate between weightings; **no default was changed**. Nothing here says the defaults are right or wrong for real usage.

## What worked

- **One shared tool path paid for itself.** Putting scope, rate-limit and namespace checks in the single `guarded` wrapper meant the REST facade needed no authorization code of its own, and REST/MCP parity was one assertion.
- **Typed errors instead of message parsing.** `ApiToolError` carries an HTTP status; the facade reads it from the SDK's re-wrapped exception's `__cause__`. Found by a failing unit test (403/429 came back as 422), not by reading docs.
- **The full-directory regression.** After Phase 5's stale-test lesson I ran every integration file, external ones one at a time with pauses; everything passed.
- **Live check found real friction** (below), and the real client behaved well: the read-scope refusal was clear, and a wrong-project mistake was diagnosable from the server log.

## What didn't work / surprises

- **A revoked token looks like an OAuth failure in the client.** ROOTMEM answers 401; the client then tries an OAuth login the server does not offer and ends at "Dynamic Client Registration rejected (HTTP 404)" with an Authenticate button. Documented, not fixed; a real fix would mean not advertising OAuth metadata or offering a clearer 401 body.
- **The first exit-test failures were mine, not the product's, but two were instructive:** a rate-limit that never triggered because a slow remote database made each call take longer than the refill interval (fix: a slower refill), and the hook exiting 1. The hook's stderr was hidden by my test, so the real cause took two extra 3-minute runs to see: the HTTP test harness gave the server a stripped environment with no home directory, and the Anthropic SDK needs one to build its client. Lesson: make test harnesses surface subprocess errors from the first run.
- **The hook's 30s client timeout was a genuine latent bug** — `ingest_session` can take longer (Voyage retries plus extraction) — so the hook now waits 120s. It was hidden in the exit test by the error above until the stderr was visible.
- **`claude mcp add` is per-project by default.** The entries were invisible from another project until added with `--scope user`.
- **Path confusion between Git Bash and Windows Python** (`/tmp`) briefly broke the hook check; it failed cleanly and reported why.
- **I twice typed a mistaken `C:\AppData\...` path** while writing files; one created a stray file and folder (removed), the other resolved harmlessly. No other file was written outside the project.

## Limits worth stating

- **Container packaging is unverified.** No Docker on this machine works; the CI `container` job is the only check, and it runs when this is pushed. If it fails, that is a Phase 6 defect.
- Rate limiting is per process and resets on restart; there is no shared limiter.
- Export/import excludes embeddings, soft-deleted memories, the audit log and superseded skill versions, and needs an empty target namespace.
- The evaluation set is small and synthetic; its "semantic" baseline is cosine over the in-memory repository, not production hybrid.
- Still no TLS in the application, no OAuth, no token refresh.

## Decisions to revisit in Phase 7

- Whether real usage supports any ranking-default change; the q06 regression (a correct but low-trust, never-accessed answer losing) is the case to watch.
- A clearer response for revoked/expired tokens, or advertising no OAuth metadata.
- A shared rate limiter if the server is ever scaled out.
- Carried unchanged: session-trace batch scoping, 0.80 clustering thresholds, first-episode auto-trigger.

## Metrics captured

- Unit tests: 340 passed. Free integration suite: 103 passed (1010s). External files each passed: Anthropic providers, stdio e2e (7), Voyage, and the Phase 1-6 exit tests (Phase 6: 224-249s).
- `mypy --strict`: 197 files clean.
- Live: 14 rapid REST calls gave 200 x9, 429 x4, then 200 after refill; rotation flipped the old token 200 -> 401 immediately.
