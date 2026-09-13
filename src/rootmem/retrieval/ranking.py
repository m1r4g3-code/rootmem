"""Retrieval ranking — reserved layer, currently empty by design.

Phase 0's only ranking is `ts_rank()`, issued directly inline in
`PostgresMemoryRepository.search_text` — there is no custom scoring formula
to house here yet (see docs/math-spec/phase0-math-spec.md). This module
exists now so the multi-factor ranking formula planned for Phase 4
(cosine similarity + decay + salience + trust + graph proximity) has a
stable home to land in without the retrieval layer leaking into storage
code at that point, per the charter's layer-isolation mandate (§8).
"""
