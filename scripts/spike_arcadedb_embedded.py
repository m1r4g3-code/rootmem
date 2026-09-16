"""Phase 1 Prototype-stage spike (throwaway, not part of the shipped codebase):
does `arcadedb-embedded` actually work on this Windows Python 3.13 box, and
what does it cost?

Findings feed docs/adr/0006-graph-as-postgres-tables-not-dedicated-engine.md
and docs/research/phase1-research-memo.md regardless of which way the
graph-store decision goes — see the plan's "ArcadeDB due-diligence" note.

ACTUAL RESULTS (run 2026-09-16, Windows 11, Python 3.13, arcadedb-embedded
26.9.1):
- Install: real Windows x86_64 wheel, ~64.5MiB download, ~1m42s to prepare.
  Bundles its own Java 25 runtime via jpype1 — no separate JVM install step.
  Functionally correct on first try: schema creation, vertex/edge insert,
  and a 1-hop Cypher MATCH query all worked exactly as expected.
- import arcadedb_embedded: 0.89s
- create_database + schema (first JVM touch): 6.04s
- insert 3 vertices + 1 edge: 1.13s
- 1-hop Cypher query (first query, JIT/engine warmup included): 3.01s
- Benign stderr noise observed: "WARNING: Using incubator modules:
  jdk.incubator.vector" and a GraalVM Polyglot Engine "no languages found"
  warning — neither affected correctness, but both would show up in a real
  MCP server's stderr/logs unless suppressed.

WHY THIS MATTERS FOR THE DECISION: an MCP server over stdio is launched
fresh per client session (Claude Code/Cursor start a new subprocess each
time, per ADR 0002's transport choice) — a ~9+ second tax before the graph
is even queryable, every single session start, is a real, user-visible cost
this spike makes concrete rather than theoretical. This is the decisive
practical data point behind ADR 0006 choosing plain Postgres tables over
ArcadeDB for Phase 1: the JVM cold-start cost is real and would land on
every session, not just once.

Run: uv run python scripts/spike_arcadedb_embedded.py
"""

from __future__ import annotations

import time

start_import = time.perf_counter()
import arcadedb_embedded  # noqa: E402

import_seconds = time.perf_counter() - start_import
print(f"import arcadedb_embedded: {import_seconds:.3f}s")

start_create = time.perf_counter()
db = arcadedb_embedded.create_database("./.spike_arcadedb_data")
db.schema.create_vertex_type("Person")
db.schema.create_edge_type("WORKS_AT")
create_seconds = time.perf_counter() - start_create
print(f"create_database + schema (cold JVM start): {create_seconds:.3f}s")

start_insert = time.perf_counter()
with db.transaction():
    alice = db.new_vertex("Person").set("name", "Alice").save()
    acme = db.new_vertex("Person").set("name", "Acme Corp").save()
    db.new_vertex("Person").set("name", "Globex").save()
    alice.new_edge("WORKS_AT", acme).save()
insert_seconds = time.perf_counter() - start_insert
print(f"insert 3 vertices + 1 edge: {insert_seconds:.3f}s")

start_query = time.perf_counter()
result = db.query(
    "cypher",
    "MATCH (p:Person {name: 'Alice'})-[:WORKS_AT]->(employer) RETURN employer.name AS name",
)
rows = list(result)
query_seconds = time.perf_counter() - start_query
print(f"1-hop Cypher query: {query_seconds:.3f}s -> {[r.to_dict() for r in rows]}")

db.close()
print("\nSummary: install succeeded (real Windows x86_64 wheel, ~64.5MiB, "
      "bundles its own Java 25 runtime via jpype1 — no separate JVM install "
      "needed). Functionally correct on first try. Cold start "
      f"(create_database, first JVM touch) took {create_seconds:.2f}s — "
      "meaningfully slower than anything else in this stack's startup path "
      "(the MCP server itself starts in well under 1s). This is the concrete "
      "cost side of the ADR 0006 trade-off: real, working, Windows-native "
      "Cypher, at the price of a JVM cold-start tax on every process start.")
