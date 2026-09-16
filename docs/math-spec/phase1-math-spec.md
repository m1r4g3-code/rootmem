# Phase 1 Math/Algorithm Spec — Deterministic Contradiction Rule & Provisional Hybrid Score

**Status:** Two minimal, explicitly provisional formulas — not the final versions the charter ultimately wants, with justification for why each is deliberately simple for now (per charter SDLC Step 4, same discipline as Phase 0's N/A stub).

## Contradiction resolution: deterministic rule, not the confidence-weighted Bayesian update

The charter's algorithm directives (§5.5) assign confidence-weighted Bayesian contradiction resolution to Phase 1, once the semantic store first has facts that can conflict. Phase 1 does now have conflicting facts — but attempting the real Bayesian update here would mean designing a posterior-update formula with no retrieval-outcome feedback loop to calibrate it against, exactly the kind of unvalidated, throwaway design Phase 0's math-spec already refused to do for salience/decay/ranking. There is no data yet on how often the deterministic rule below actually gets contradictions wrong, which is precisely the signal a real Bayesian model would need to be worth anything.

**The Phase 1 rule** (implemented as a pure function in `extraction/contradiction.py`, isolated so Phase 2 can replace it without touching the pipeline around it):

Given a newly-extracted relation `r_new` and the currently-active relation `r_old` for the same `(namespace, subject_entity_id, predicate)`:

```
if r_new.confidence > contradiction_confidence_floor:
    r_old.valid_to = r_new.valid_from
    r_old.superseded_by = r_new.id
    r_new.supersedes = r_old.id
else:
    r_old.metadata["contested"] = true
    r_new.metadata["contested"] = true
    # both remain active; neither is superseded
```

This is most-recent-wins gated by a confidence floor, not a probabilistic combination of the two relations' evidence — it makes no claim about which fact is more likely *true*, only about which one the graph should treat as current going forward, with an explicit escape hatch (`contested`) for the case where the new evidence isn't confident enough to simply overwrite. `contradiction_confidence_floor` is a `Settings`-configured constant (NFR7 in `docs/requirements/phase1-requirements.md`), not derived from any theoretical model.

**Where the real math belongs:** Phase 2, once consolidation exists and can supply retrieval-outcome feedback (did trusting the "winning" relation actually lead to correct answers later?) to calibrate a genuine confidence-weighted Bayesian posterior against. This mirrors exactly how Phase 0's math-spec deferred salience scoring to Phase 2 for the same reason — no signal yet to fit.

## Hybrid search score: provisional linear blend, not the Phase 4 multi-factor formula

`retrieval/ranking.py`'s docstring already reserves this module for the charter's eventual multi-factor formula (`α·cosine_sim + β·R(t) + γ·salience + δ·trust + ε·graph_proximity`, per §5.3), explicitly noting that formula needs decay (Phase 4), salience (Phase 2), trust (Phase 4), and graph proximity (Phase 1+) — none of which exist yet except the cosine-similarity term this phase adds.

**The Phase 1 function**, its first real tenant:

```
hybrid_score(text_rank, cosine_sim, weight_text, weight_vector) =
    weight_text * text_rank + weight_vector * cosine_sim
```

A plain weighted linear blend of Postgres's native `ts_rank()` output and cosine similarity between the query embedding and `content_embedding`, with `weight_text`/`weight_vector` as `Settings`-configured constants (defaulting to equal weight). This is two of the eventual formula's five terms, combined the simplest possible way (no learned weighting, no normalization beyond what `ts_rank()`/cosine similarity already provide natively), specifically so the exit criterion's semantic-vs-full-text comparison (§(c) in `docs/requirements/phase1-requirements.md`) has a concrete score to test against.

**Why not more sophisticated now:** normalizing `ts_rank()` (unbounded) against cosine similarity (bounded `[-1, 1]`) properly, or learning the blend weights from actual query outcomes, both require exactly the kind of real usage data this phase doesn't have yet building against zero real queries. The research memo carries forward "whether `voyage-4`/1024/HNSW remains right" as an open question for the same reason — this formula's weights are in the same boat.

**Where the real formula belongs:** Phase 4, per the charter's own assignment, once decay, salience, and trust all exist to supply their terms, and Phase 1's graph gives `graph_proximity` something real to measure.

## What is NOT covered by this spec

Everything else the charter's algorithm-innovation directives name — salience scoring (§5.1, Phase 2), decay curves (§5.2, Phase 4), the full multi-factor retrieval-ranking formula (§5.3, Phase 4), the consolidation trigger (§5.4, Phase 2) — remains out of scope for the same reasons Phase 0's math-spec already gave: no real signal yet to design against.
