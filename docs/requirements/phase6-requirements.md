# Phase 6 Requirements & Constraints — Hardening, Ecosystem Adapters, Quality Evidence & Packaging

## Exit criterion

> Against a real uvicorn server process in HTTP mode and real Postgres:
> **(a)** an expired token, and a pre-rotation token after `rotate`, get 401, while the rotated token sees the same data;
> **(b)** a `read` identity can `search` and `recall`; every write tool is denied, with no side effects and no audit entry;
> **(c)** a burst beyond the limit is throttled for identity X while identity Y is unaffected;
> **(d)** `/healthz` returns 200 without a token and reveals nothing beyond status;
> **(e)** the REST facade returns the same result as MCP for the same call, and 401 (no token) or 403 (foreign namespace);
> **(f)** export from identity A's namespace and import into identity B's namespace reproduces memories, graph and skills, appends an `import` audit entry, and the chain verifies;
> **(g)** the Claude Code hook script, given a sample SessionEnd payload and transcript, creates the memory through REST;
> **(h)** the retrieval evaluation runs end to end and writes its report (numbers recorded, not gated);
> **(i)** stdio and all Phase 0-5 suites still pass. CI also builds the container image.

Gate for tagging `v0.6.0-phase6`: one automated exit test plus a live manual pass (`scripts/manual_phase6_check.md`).

## Functional requirements

- FR1: `identities` gains `expires_at` and `scope` (`read`|`readwrite`, default `readwrite`); the verifier rejects expired or revoked tokens.
- FR2: CLI `create --expires-in-days --scope`, and `rotate --name` (the old token is invalid immediately).
- FR3: pure `identity/scopes.py`; `guarded` denies non-read tools for a `read` identity before the tool body runs.
- FR4: pure token-bucket `identity/ratelimit.py` with an injectable clock; per-identity limits from `Settings`; throttled calls fail with a clear error (HTTP 429 on REST).
- FR5: unauthenticated `/healthz` running `SELECT 1`, returning only a status.
- FR6: REST facade `GET /v1/tools`, `POST /v1/tools/{name}` authenticating with the same verifier and calling the same tool path.
- FR7: stdlib-only Python client `RootmemClient(base_url, token)`.
- FR8: `PortabilityRepository` (Postgres + fake, contract-tested round trip); versioned bundle with manifest and content digest; CLI `export`/`import`; embeddings excluded by default; audit log not exported; import appends one `import` audit entry.
- FR9: `integrations/claude_code_hook.py` (SessionEnd stdin JSON, transcript JSONL to text, ingest through the client).
- FR10: `evaluation/` metrics (recall@k, MRR, nDCG@k), a labeled set with recorded embeddings, a runner comparing text-only, hybrid and multi-factor ranking, and a report.
- FR11: `Dockerfile`, production compose file with a TLS reverse proxy, `docs/operations.md`, and a CI job that builds the image and smoke-tests `/healthz`.

## Non-functional requirements

- NFR1: `mypy --strict`, zero suppressions; scopes, rate limiter, bundle format, hook parser and metrics are pure and unit-tested.
- NFR2: the REST facade must not reimplement authorization; it shares the MCP tool path.
- NFR3: a denied or throttled call has no side effects.
- NFR4: the evaluation runs offline and deterministically (recorded embeddings, injected clock).
- NFR5: no new runtime dependency beyond what the SDK already brings; the client uses only the standard library.
- NFR6: honest limits: single-node rate limiting, container build verified in CI only, small synthetic evaluation set.

## Non-goals

OAuth/OIDC; multi-node or distributed rate limiting; a management UI; MCP tools for export/import; streaming or websocket APIs; live replication; changing ranking defaults without evidence; a public benchmark suite; cross-deployment identity federation.
