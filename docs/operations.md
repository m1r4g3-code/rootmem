# Operating ROOTMEM

Audience: someone deploying ROOTMEM as a shared HTTP service for one or more
agents. For local single-user use, the stdio setup in the README is simpler.

> **Verification status.** Docker Desktop does not work on the development
> machine, so nothing here was run locally. The CI job `container` builds the
> `Dockerfile`, runs the migrations from inside the image, starts the server
> and checks `/healthz` and the 401s; it passed on the Phase 6 commit. That
> covers the **image only**. `deploy/docker-compose.prod.yml` and
> `deploy/Caddyfile` (the compose wiring, the migrate-then-start ordering and
> automatic TLS) have **never been run**. Do a staging run before trusting
> production.

## What runs

```
agents / clients ──HTTPS──▶ Caddy (TLS) ──HTTP──▶ rootmem (port 8765, private)
                                                     │
                                                     ▼
                                                 Postgres + pgvector (private)
```

ROOTMEM also calls two paid external APIs: **Voyage** (embeddings) and
**Anthropic** (extraction, consolidation). A Voyage account without a payment
method is limited to 3 requests/minute; ROOTMEM degrades (stores memories
without embeddings) rather than failing, but search quality drops until
embeddings are back-filled (`scripts/backfill_embeddings.py`).

## Deploy

1. Point a DNS name at the host; open ports 80 and 443.
2. `cp deploy/.env.prod.example deploy/.env.prod` and set every value
   (`ROOTMEM_DOMAIN`, `POSTGRES_PASSWORD`, `VOYAGE_API_KEY`, `ANTHROPIC_API_KEY`).
3. `docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod up -d --build`.
   Migrations run automatically in the one-shot `migrate` service before the
   server starts.
4. Check `https://<domain>/healthz` returns `{"status":"ok"}`.

Neither Postgres nor the server publishes a port; Caddy is the only way in.

## Identities and tokens

Every client needs a bearer token. Run these inside the server container:

```
docker compose ... run --rm rootmem python -m rootmem.identity.cli create \
    --name build-bot --namespace team --scope readwrite --expires-in-days 90
docker compose ... run --rm rootmem python -m rootmem.identity.cli list
docker compose ... run --rm rootmem python -m rootmem.identity.cli rotate --name build-bot
docker compose ... run --rm rootmem python -m rootmem.identity.cli revoke --name build-bot
```

- The token is printed **once**. Only its SHA-256 is stored; a lost token
  cannot be recovered, only rotated.
- `--scope read` allows `recall`, `search`, `related`, `find_skill`,
  `get_skill`, `verify_audit` and nothing that writes.
- `rotate` kills the old token immediately; there is no grace window. Update
  clients first if you cannot tolerate a gap.
- Revocation, rotation and expiry are checked on every request, so they take
  effect on the next call.
- An identity may only touch the namespaces it was created with. A request for
  any other namespace is refused and changes nothing.

## Using the API

MCP clients connect to `https://<domain>/mcp` with an
`Authorization: Bearer <token>` header. Plain HTTP callers can use the REST
facade, which shares the same authorization, rate limits and audit:

```
curl -H "Authorization: Bearer $TOKEN" https://<domain>/v1/tools
curl -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
     -d '{"query":"deploy window","namespace":"team"}' \
     https://<domain>/v1/tools/search
```

Status codes: 401 no/invalid/expired/revoked token, 403 namespace or scope
denied, 404 unknown tool or memory, 422 bad arguments, 429 rate limited.

Python: `from rootmem.client import RootmemClient` (standard library only).

### Claude Code session hook

Capture finished sessions through the API (works against a remote server):

```json
{ "hooks": { "SessionEnd": [ { "hooks": [ {
  "type": "command",
  "command": "python -m rootmem.integrations.claude_code_hook"
} ] } ] } }
```

with `ROOTMEM_URL`, `ROOTMEM_TOKEN` and optionally `ROOTMEM_NAMESPACE` /
`ROOTMEM_SOURCE` in the environment. The hook never blocks the session ending;
on failure it prints to stderr and exits non-zero.

### Auto-memory middleware (Phase 7)

Two more hooks make retrieval and capture automatic *within* a session, not
only at its end — see `docs/capture-hook-example.md` for the full
`settings.json` wiring and env var table. Operationally:

- Both add one HTTP round trip per prompt (`auto_recall`, read-scope) and
  per turn (`auto_capture`, write-scope) — on an active session this is
  meaningfully more request volume than the previous end-of-session-only
  capture.
- **Rate limits matter more with this on.** `RATE_LIMIT_PER_MINUTE` (default
  600) should comfortably cover a single interactive user; size it up before
  enabling this for several concurrent identities on one deployment.
- **Voyage's free tier (3 requests/minute) does not gate `auto_recall`**
  (it uses `mode="text"`, no embedding call) but **does gate `auto_capture`**
  (`remember` embeds synchronously) — an active back-and-forth session will
  exceed that ceiling on the free tier; writes still succeed with a null
  embedding (existing graceful degradation), just without a vector until a
  later `scripts/backfill_embeddings.py` sweep. A paid tier removes this.
- Per-turn capture and the end-of-session capture will write overlapping
  content for the same conversation, by design (ADR 0043) — this is left
  for consolidation to merge, not deduplicated at write time.

## Rate limiting

Each identity has a token bucket (`RATE_LIMIT_PER_MINUTE`, default 600;
`RATE_LIMIT_BURST`, default 60; 0 disables). It is **per server process** and
resets on restart, which is correct for one node and wrong for several: do not
scale out horizontally without adding a shared limiter.

## Backup, restore and moving data

- **Full backup:** `pg_dump` the `rootmem` database (it holds memories, graph,
  skills, identities and the audit log). Test a restore before you need one.
- **One namespace, between deployments:**
  `python -m rootmem.portability.cli export --namespace team --out team.jsonl`
  then `... import --namespace team --in team.jsonl` on the target (which must
  be empty for that namespace). The bundle carries a digest and is refused if
  altered. Embeddings, soft-deleted memories and the audit log are **not**
  included; re-embed with `scripts/backfill_embeddings.py`. Import appends one
  `import` entry to the target namespace's audit chain.
- **Audit check:** call `verify_audit` for a namespace; a broken chain reports
  the first altered row.

## Upgrading

Pull the new code, rebuild, `up -d --build`. Migrations run in the `migrate`
service first. Migrations are forward-only; take a `pg_dump` beforehand.

## Configuration reference

| Variable | Default | Purpose |
|---|---|---|
| `ROOTMEM_TRANSPORT` | `stdio` (`http` in the image) | `stdio` or `http` |
| `ROOTMEM_HTTP_HOST` / `_PORT` | `127.0.0.1` / `8765` | listen address |
| `ROOTMEM_HTTP_ALLOW_NON_LOOPBACK` | `false` (`true` in the image) | required to listen beyond loopback |
| `ROOTMEM_HTTP_ALLOWED_HOSTS` | empty | hostnames served; enables Host/Origin checking |
| `RATE_LIMIT_PER_MINUTE` / `_BURST` | `600` / `60` | per-identity limit |
| `TRUST_SOURCE_RELIABILITY` | `{}` | JSON map of source to reliability (0-1) |
| `POSTGRES_*` | see `.env.example` | database connection |
| `VOYAGE_API_KEY`, `ANTHROPIC_API_KEY` | none | external APIs |

## Limits and threat model, stated plainly

- **TLS is not in the application.** Terminate it in the reverse proxy (Caddy
  here). Never expose port 8765 directly.
- **Bearer tokens are bearer tokens:** anyone holding one has that identity's
  access until it expires, is rotated or is revoked. Prefer expiry.
- **A revoked or expired token looks like an OAuth failure in some clients.** ROOTMEM answers 401, and MCP clients that support OAuth respond by trying to log in; the server offers no OAuth endpoints, so they end at "Dynamic Client Registration rejected (HTTP 404)" with an Authenticate button instead of saying the token is dead. Do not press Authenticate: rotate or re-issue the token and update the client's `Authorization` header.
- **The audit chain detects tampering; it does not prevent it.** A database
  superuser can rewrite the whole chain, and a mutation that succeeds but whose
  audit append fails is reported as an error even though the change applied.
- **No OAuth, no user accounts, no per-tool scopes** beyond read/readwrite.
- **Single node.** Rate limits are in-process; there is no clustering.
- **Ranking weights and decay are provisional defaults**; see
  `docs/benchmarks/phase6-retrieval-eval.md` for what the small evaluation set
  does and does not show.
