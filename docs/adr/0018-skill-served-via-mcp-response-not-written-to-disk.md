# ADR 0018: A distilled skill is served via MCP tool response, never written to a filesystem skills directory

**Status:** Accepted
**Date:** 2026-09-18

## Context

The SKILL.md format (agentskills.io, published December 2025) is fundamentally a filesystem artifact: a folder containing a `SKILL.md` file plus optional `scripts/`/`references/`/`assets/` subdirectories, read by a coding agent's own tooling from a known local `skills/` directory. ROOTMEM is an MCP stdio server, launched as a subprocess per client session — it has no general filesystem-write channel into wherever a *client's own* skills directory happens to live, and that location varies by client, host machine, and configuration, with no principled way for ROOTMEM to discover or guess it.

## Decision

`procedural_memories` (a Postgres table, ADR 0017) is the durable source of truth for every distilled skill and lesson. A new pure module, `consolidation/skill_format.py`, renders a stored row into literal SKILL.md-conformant markdown text (YAML frontmatter + body) on demand. A new `get_skill(name, namespace)` MCP tool returns that rendered text directly in its response. ROOTMEM never writes to any filesystem location outside its own Postgres-backed storage layer — **producing well-formed, spec-conformant SKILL.md content is the entirety of ROOTMEM's contract; "installing" that content into a real skills directory (writing the folder, placing the file) is explicitly the calling agent's or human's responsibility**, exercised however that agent already manages its own skills directory.

## Rationale

This is a clean division of labor, not a scope gap: ROOTMEM's whole architecture (per ADR 0002/0010) already treats itself as a memory *service* a client talks to over MCP, never a service that reaches out and mutates a client's local filesystem on its own initiative — capture is client-initiated (`ingest_session`/CLI), never a webhook ROOTMEM itself pushes into. Extending that same boundary to skill delivery is consistent, not a new precedent. It also sidesteps a real, unresolvable ambiguity: even if ROOTMEM *could* write files, "which directory" has no single correct answer across Claude Code, Cursor, or any other MCP-capable client, each of which may structure or even support a skills directory differently — hardcoding a guess would be exactly the kind of unverifiable, environment-specific behavior the charter's engineering standards exist to prevent.

Rendering on demand from a stored row (rather than storing pre-rendered markdown as the source of truth) keeps `name`/`description` validation (`skill_format.validate_skill_name`/`validate_skill_description`) enforceable against the structured fields at write time, and keeps future rendering changes (e.g. adding a version marker) a pure-function change with no data migration.

## Alternatives considered

- **ROOTMEM writes literal SKILL.md folders to a configured local directory.** Rejected: requires a new, unprincipled configuration surface (`skills_output_directory` or similar) with no way to verify it points anywhere a real client will actually read from, and turns ROOTMEM into a filesystem-mutating service for the first time in this project's history — a materially different trust boundary than everything shipped so far.
- **Return a skill as a downloadable/exportable artifact via a new transport (e.g. writing to a well-known path relative to the MCP server's own working directory).** Rejected: still guesses at a location, and MCP stdio servers have no standard convention for "files the client should go pick up" — the tool-response channel is the one channel this architecture already guarantees is read.
- **Store pre-rendered markdown as the persisted source of truth, not structured fields.** Rejected: would make `name`/`description` re-validation and any future rendering change (e.g. surfacing `scripts/`/`references/` subdirectories per NFR/math-spec's "not yet" note) require re-parsing markdown rather than reading structured columns directly.

## Consequences

- `get_skill`'s response is the sole way any client ever sees a distilled skill's content — `find_skill` returns discovery/ranking metadata only (name, description, kind, score), not full body content, keeping the two tools' responsibilities distinct (search vs. retrieve, the same split `search`/`recall` already use for episodic memories).
- The Phase 3 exit criterion's requirement (e) — "correctly follows its documented steps via ordinary subsequent MCP tool calls" — is scoped precisely to what this boundary makes observable: a session receiving `get_skill`'s text and then acting on it correctly through further MCP calls, not an assertion that any file was ever written anywhere.
- If a future phase needs literal on-disk installation (e.g. a dedicated "apply this skill to my current client" flow), that is a new, separate capability layered on top of this one — `get_skill`'s content contract does not need to change to support it.
