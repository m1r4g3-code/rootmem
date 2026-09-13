# Phase 0 Math/Algorithm Spec — N/A

**Status:** Not applicable to this phase, with justification (per charter SDLC Step 4, which requires this determination to be explicit and written, not silently skipped).

## Why there is no math spec for Phase 0

Phase 0 has exactly one ranking operation — `search`'s ordering by Postgres's native `ts_rank()` over a GIN full-text index. This is a built-in database function, not a custom-designed scoring formula; there is nothing to derive, no weights to justify, and no edge cases specific to a novel algorithm (Postgres's own documentation covers `ts_rank()`'s behavior).

The charter's algorithm-innovation directives (§5.1–§5.5 of the master execution prompt: salience scoring, decay curves, retrieval-ranking weights, consolidation triggers, contradiction resolution) all presuppose data and mechanisms that do not exist yet in Phase 0:

- **Salience scoring** requires retrieval-outcome feedback (did retrieving this memory help the agent succeed?) — Phase 0 has no notion of task outcomes at all.
- **Decay curves** require a reinforcement signal (retrieval count, memory strength over time) — Phase 0 has no consolidation engine and no notion of memory "strength" separate from raw existence.
- **Retrieval ranking weights** (`α·cosine_sim + β·R(t) + γ·salience + δ·trust + ε·graph_proximity`) require cosine similarity (needs populated embeddings — deferred to Phase 1), recency-based retention `R(t)` (needs decay — Phase 2/4), salience (Phase 2), trust (Phase 4), and graph proximity (needs the graph store — Phase 1+). None of these five terms have real data behind them in Phase 0.
- **Consolidation triggers** and **contradiction resolution** require an episodic buffer and a semantic store respectively — both are Phase 1/2 constructs.

Writing a math spec now would mean designing formulas against a system that has no real signal to validate them against — exactly the kind of premature, unvalidated design the charter's "you do not guess" principle (§0) warns against. A formula invented here would not be backed by an experiment, a benchmark, or even real data shape, and would likely be thrown away or substantially rewritten once Phase 1/2/4 exist.

## Where the real math specs belong

- Retrieval-ranking formula (baseline + any learned/contextual-bandit improvement per charter §5.3): **Phase 4**, once trust and decay signals exist, and Phase 1's embeddings give a real cosine-similarity term.
- Decay/forgetting curve (Ebbinghaus exponential vs. power-law comparison per §5.2): **Phase 4**.
- Salience scoring (linear vs. learned model per §5.1): **Phase 2**, when consolidation first needs to prioritize what gets distilled.
- Consolidation trigger (adaptive/information-theoretic per §5.4): **Phase 2**.
- Contradiction resolution (confidence-weighted Bayesian update per §5.5): **Phase 1**, when the semantic store first has facts that can conflict.

This stub exists so the charter's per-phase artifact checklist has a real, reviewable answer for Phase 0 rather than a silently missing file.
