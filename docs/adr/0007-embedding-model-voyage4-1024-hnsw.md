# ADR 0007: Embedding model — `voyage-4` at 1024 dimensions, HNSW index

**Status:** Accepted
**Date:** 2026-09-16

## Context

Phase 0's schema left `content_embedding` dimension-unconstrained specifically so this decision could be made once, correctly, with a real model chosen — rather than guessed in advance and risking exactly the migration NFR6 was written to avoid. Phase 0's research memo assumed the Voyage `voyage-3` family (voyage-3-lite=512 dims, voyage-3=1024, voyage-3-large=configurable), where dimension was coupled to tier.

That family has since been superseded by **voyage-4** (voyage-4-lite / voyage-4 / voyage-4-large, released 2026), which decouples dimension from tier entirely: every tier supports Matryoshka Representation Learning (MRL) truncation to 256, 512, 1024, or 2048 dimensions. Pricing: voyage-4-lite $0.02/M tokens, voyage-4 $0.06/M, voyage-4-large $0.12/M; all with a 32K-token context window and 200M free tokens per account.

## Decision

Use `voyage-4`, truncated to **1024 dimensions**, indexed with pgvector's **HNSW** using `vector_cosine_ops`.

## Rationale

**Tier — `voyage-4`, not `-lite` or `-large`.** `voyage-4-lite` is priced and positioned for high-throughput bulk indexing; ROOTMEM's Phase 1 shape is a personal/small-team agent memory store, not a bulk corpus, so the throughput optimization isn't the right trade to make first. `voyage-4-large`'s marginal quality gain over `voyage-4` has no benchmark behind it for this specific workload — paying 2x for an unproven gain directly contradicts Phase 0's own research memo, which explicitly warned against trusting saturated/self-reported benchmarks (it cited Vectorize.io measuring Mem0 at 49% against its self-reported 94.4%). `voyage-4` is the reasoned middle default until real retrieval-quality data says otherwise.

**Dimension — 1024, not 256/512/2048.** 1024 sits at the point where pgvector's HNSW index performs well while still giving materially better recall than a 256 or 512 truncation. It also matches what Phase 0's research memo already assumed for `voyage-3` (1024), so nothing about the surrounding index/query story needed to be rethought from scratch for an unfamiliar number.

**Index — HNSW, not ivfflat.** ivfflat's `lists` parameter must be tuned against the table's row count, which is meaningless for a table that starts at zero rows and grows from there — an ivfflat index trained on an empty table is close to useless. HNSW has no such training-data dependency and is the modern default recommendation for pgvector as of this decision.

## Alternatives considered

- **`voyage-4-lite` at 512 dims.** Rejected: optimized for a bulk-indexing throughput profile this project doesn't have; a smaller dimension would also give a weaker starting point for the exit criterion's semantic-vs-full-text comparison.
- **`voyage-4-large` at 2048 dims.** Rejected: no internal benchmark justifies the 2x cost for an unproven quality gain, and a larger dimension costs more to index/query with no evidence it's needed yet.
- **ivfflat.** Rejected: needs a populated table to tune against; Phase 1 starts from zero rows.

## Consequences

- `storage/postgres/migrations/0002_pgvector_dimension.sql` fixes `content_embedding` to `VECTOR(1024)` and adds the HNSW index — the migration NFR6 was explicitly written to make possible without a redesign.
- This choice is **explicitly provisional**, not permanent doctrine: `docs/research/phase1-research-memo.md` carries it forward as an open question for Phase 2's research memo to revisit once real usage/retrieval-quality data exists — the same pattern Phase 0's own embedding-model question followed into this phase.
- `config.py` gains `voyage_model="voyage-4"` and `voyage_output_dimension=1024` as named, overridable settings (not hardcoded inline), so revisiting this later is a config change plus a re-embedding pass, not a code change.
