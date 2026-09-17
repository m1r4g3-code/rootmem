# ADR 0015: Distillation clustering — similarity-threshold union-find, not k-means/HDBSCAN

**Status:** Accepted
**Date:** 2026-09-18

## Context

The Build Reference proposes k-means or HDBSCAN for episodic→semantic distillation's clustering step. No `numpy`/`scikit-learn`-class ML dependency exists anywhere in this project's `pyproject.toml` today — every clustering-adjacent capability so far (semantic search, hybrid ranking) is built entirely on pgvector's native cosine-distance operator (`<=>`), already a production dependency since Phase 1. Every prior infrastructure decision in this project has favored reusing what's already running over adding something new for a single use case (ADR 0006, ADR 0010, ADR 0012).

## Decision

Cluster episodes for distillation via similarity-threshold union-find over pgvector cosine similarity, computed by `MemoryRepository.find_similar_pairs` (a bounded self-join over one consolidation batch) and joined in pure Python (`consolidation/clustering.py`'s `cluster_by_similarity`, ~30 lines, no library dependency). Any pair with `cosine_sim >= distillation_similarity_threshold` is unioned into the same cluster; clusters smaller than `distillation_min_cluster_size` (default `2`) are left un-distilled for that pass.

`distillation_similarity_threshold` is set to **`0.80`**, validated empirically by `scripts/spike_similarity_clustering.py` against real `voyage-4` embeddings (not synthetic/hash-based vectors) for a small, hand-labeled mixed set: three genuine near-duplicate restatements of "Alice works at Acme Corp" (pairwise similarities `0.9407`-`0.9610`), six otherwise-distinct sentences including one deliberately confusable pair (a different subject, same predicate/object — "Bob works at Acme Corp," similarity `0.7950` to the Alice cluster). At `threshold=0.80`, the spike's clustering output exactly matches the expected hand-labeled grouping; at `0.70` and `0.75` it does not (the Bob/Alice pair and, at `0.70`, even a question sentence incorrectly join the cluster).

## Rationale

Union-find over an already-available similarity signal requires no new dependency, no model training/fitting step (unlike k-means, which needs a chosen `k`; HDBSCAN, which needs density-parameter tuning), and is easy to reason about and unit-test as a pure function with hand-built similarity data — no real embeddings needed for its own unit tests (`tests/unit/consolidation/test_clustering.py`), only for the one-time threshold-selection spike. It composes naturally with `find_similar_pairs`, the same query that also feeds salience's `novelty`/`repetition` terms (ADR 0016) — one pgvector self-join per batch serves both purposes.

## A real, documented risk this threshold carries

The margin between the chosen threshold (`0.80`) and the nearest confusable non-match found in the spike (`0.7950`, same-predicate-different-subject) is thin — `0.005`. This is not treated as a false victory: it means a threshold tuned tighter around this specific fixture's numbers could misfire on a different confusable pair with slightly higher incidental similarity (e.g. two different people at the same company, phrased even more similarly than this spike's example). This is named explicitly as the concrete revisit trigger for this ADR — if real usage produces false-positive clusters (two genuinely different subjects merged), the fix is either raising the threshold (accepting some missed true corroborations) or, if that proves insufficient, adding a cheap structural check (e.g. requiring extracted subject-entity match, not just embedding similarity) before ADR 0015's pure-similarity approach is abandoned for something more expensive.

## Alternatives considered

- **k-means or HDBSCAN**, per the Build Reference. Rejected: first `scikit-learn`/`numpy`-class dependency this project would ever take on, for a clustering problem pgvector cosine similarity plus union-find already solves at the scale this phase's exit criterion and near-term realistic usage need.
- **A higher threshold (e.g. `0.90`) for a larger safety margin.** Considered — rejected as the *default* because it would also fail to cluster some of this spike's own genuine near-duplicates less strongly worded than the three tested here (real restatements can plausibly sit closer to `0.85`-`0.90` than the `0.94`+ this particular fixture happened to produce); `0.80` is the spike's empirically-validated boundary, not a conservative guess in either direction.
- **A structural check (exact subject-entity match) instead of, rather than alongside, pure embedding similarity.** Rejected as this phase's default: it would require running entity extraction *before* clustering rather than after (distillation currently clusters raw episode text, then extracts/distills from the cluster) — a larger pipeline restructuring than this phase's scope justifies without first seeing whether the thin-margin risk above actually manifests in practice.

## Consequences

- `scripts/spike_similarity_clustering.py` and its console output are the recorded evidence for this threshold — not asserted from first principles.
- `tests/unit/consolidation/test_clustering.py` unit-tests `cluster_by_similarity` against hand-built similarity data (no real embeddings needed there); a real-embeddings regression check re-running the spike's exact scenario belongs in the sparse `integration-external` CI job, so a future embedding-model change (e.g. revisiting `voyage-4` per Phase 1's own open question) is caught if it shifts these numbers.
- If usage data later shows this threshold needs per-namespace or per-predicate tuning, that is a natural, additive extension of `distillation_similarity_threshold` from a single `Settings` constant to a lookup — not a redesign of the union-find approach itself.
