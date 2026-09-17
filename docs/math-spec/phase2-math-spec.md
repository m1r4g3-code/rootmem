# Phase 2 Math/Algorithm Spec — Bayesian Belief Update, Salience Score & Consolidation Trigger

**Status:** Three formulas, each filling in exactly one placeholder Phase 1 left explicitly open (`docs/math-spec/phase1-math-spec.md`'s `γ·salience` term, its "consolidation trigger (§5.4, Phase 2)" note, and ADR 0008's deferred Bayesian math) — all still provisional, with justification for what real signal each still needs before it stops being provisional (same discipline as Phase 0/1's specs).

## Bayesian belief update: replacing the deterministic contradiction rule

ADR 0008 shipped a flat rule in Phase 1 — most-recent-wins above a confidence floor — explicitly because no retrieval-outcome feedback loop existed to calibrate anything more sophisticated against, and explicitly named two real gaps this design closes (see `docs/research/phase2-research-memo.md`): the deterministic rule never distinguished a corroborating restatement from a genuine contradiction, and `extraction/contradiction.py` was promised but never created.

**Belief representation.** Every relation's belief is a Beta distribution over "this relation is currently true," parameterized by two stored pseudo-counts, `belief_alpha`/`belief_beta` (both `DOUBLE PRECISION`, `> 0`). The relation's `confidence` column is a cached, recomputed function of the two, never independently assigned:

```
confidence = belief_alpha / (belief_alpha + belief_beta)
```

Beta-Bernoulli conjugacy means `(alpha, beta)` is a sufficient statistic for the entire evidence history — mathematically equivalent to replaying every corroborating/conflicting/feedback event from scratch, at the cost of two floats instead of an event log scan on every read. This is the deliberate alternative to the "recompute confidence dynamically from a raw event log at read time" pattern found in fresh research (`docs/research/phase2-research-memo.md`): `search`, `related`, and contradiction-detection all read `confidence` far more often than evidence changes it, so a cheap, correct, incrementally-updated cache is the right trade here, not a per-read replay. The raw events are still recorded (`relation_feedback`, one row per `feedback` call) for auditability and future recalibration — they are just not what gets read on the hot path.

**Applying one evidence event.** A single pure function handles every evidence source (initial extraction, initial distillation, corroboration, and explicit feedback) — the only per-source variation is which two numbers get passed in:

```
def apply_evidence(alpha, beta, *, confidence, reliability, prior_strength, supporting) -> (alpha', beta'):
    weight = reliability * prior_strength
    if supporting:
        return alpha + weight * confidence, beta + weight * (1 - confidence)
    else:
        return alpha + weight * (1 - confidence), beta + weight * confidence
```

`confidence` is the evidence's own strength in `[0, 1]` (an extraction/distillation call's stated confidence, or a `feedback` call's `reported_confidence`). `reliability` is a per-source-type weight in `[0, 1]` — `bayesian_source_reliability_extracted` (default `0.7`), `bayesian_source_reliability_distilled` (default `0.85`, an abstracted fact from multiple corroborating episodes is inherently better-supported than one raw extraction), `bayesian_source_reliability_feedback` (default `1.0`, an explicit agent judgment is trusted fully). `prior_strength` (`bayesian_prior_strength`, default `2.0`) scales how much pseudo-count weight one evidence event contributes relative to the `Beta(1, 1)` uniform prior every new relation starts from — a `Beta(1,1)` prior plus one supporting event at `confidence=0.9`, `reliability=0.7`, `prior_strength=2.0` yields `alpha=1+1.26=2.26`, `beta=1+0.14=1.14`, `confidence≈0.665` — deliberately more conservative than trusting the raw `0.9` outright, reflecting that a single piece of evidence shouldn't immediately produce near-certainty.

**Four call sites, one function:**

1. **Initial relation creation** (extraction or distillation, no existing active relation for `(namespace, subject_entity_id, predicate)`): `apply_evidence(1.0, 1.0, confidence=r.confidence, reliability=reliability_for(r.derivation), prior_strength=bayesian_prior_strength, supporting=True)` — a fresh `Beta(1,1)` prior plus this one event.
2. **Corroboration**: a new relation's `(subject_entity_id, predicate, object_entity_id, object_literal)` exactly matches the currently-active relation's. No new row is created superseding it; instead the *existing* relation's `(belief_alpha, belief_beta)` are updated via `apply_evidence(old.belief_alpha, old.belief_beta, confidence=new.confidence, reliability=reliability_for(new.derivation), prior_strength=bayesian_prior_strength, supporting=True)`. `ContradictionResolution.corroborated = True` signals this to callers.
3. **Candidate contradiction**: same `(subject_entity_id, predicate)` but a *different* object. The new relation's own belief is computed exactly like case 1 (a fresh prior plus this one event) — it does not touch the old relation's belief, since this evidence isn't about the old relation's claim. Then: if `new_confidence > old_confidence + bayesian_supersede_margin` (default margin `0.05`), the old relation is superseded exactly as Phase 1's mechanics already do (`valid_to` set, `supersedes`/`superseded_by` linked) — only the *decision function* changed, not the soft-supersede plumbing. Otherwise, both relations are marked `metadata.contested = true` and remain active, unchanged from Phase 1's escape hatch. This is the concrete mechanism behind the exit criterion's requirement (d): once corroboration has raised an old relation's confidence well above its initial value, a contradiction that would have cleared Phase 1's flat, fixed floor may no longer clear the now-higher bar it must beat.
4. **Explicit feedback** (`feedback` MCP tool): `outcome="confirmed"` is a supporting event; `outcome="contradicted"` is a refuting event (`supporting=False`) — both via `apply_evidence(relation.belief_alpha, relation.belief_beta, confidence=reported_confidence, reliability=bayesian_source_reliability_feedback, prior_strength=bayesian_prior_strength, supporting=(outcome == "confirmed"))`. This is the literal, concrete answer to ADR 0008's own question of what "retrieval-outcome feedback" means: an explicit, agent-reported outcome, not an inferred one (see ADR 0014).

**Formal grounding, not full implementation.** AGM belief revision's three core postulates are satisfied by construction, not proven from first principles here: *Success* (new evidence always moves the posterior toward it, per `apply_evidence`'s definition), *Consistency* (a relation's belief state is always a valid `Beta(alpha>0, beta>0)`, never contradictory), and *minimal change* (`Relevance` — only the specific relation the evidence concerns is updated; unrelated relations are untouched). Full AGM-compliant revision (handling belief *sets* with entailment closure) is more machinery than one relation's scalar confidence needs; this spec borrows the postulates as a sanity check on the design, not as a specification to implement in full generality.

**What this does not yet resolve.** The reliability weights and `bayesian_prior_strength` are documented, reasonable defaults — not calibrated against real retrieval-outcome data, because no such data exists until `feedback` has been used in practice. This is exactly the position ADR 0008 itself took toward Phase 1 attempting Bayesian math with zero data: designing precise weights now, with nothing to validate them against, would be the same premature-design risk. Carried forward as an open question to Phase 3/4's research memo, once real `feedback` usage exists.

## Salience score

Fills in `retrieval/ranking.py`'s previously-unfilled `γ·salience` term (wiring it into the actual ranking formula remains Phase 4 — this phase only computes and persists the raw score):

```
salience(m) = w1 * novelty(m) + w2 * importance_flag(m) + w3 * repetition(m) + w4 * task_relevance(m)
```

with default weights `w1 = w2 = w3 = 1/3`, `w4 = 0`. `task_relevance(m)` is defined as always `0` — no task-modeling primitive exists anywhere in this codebase to compute it from, so its weight is honestly zeroed rather than the term silently omitted from the formula (the formula's shape is preserved for when Phase 3+ gives it a real input). `importance_flag(m)` is the raw agent-supplied value from `remember`/`ingest_session` (FR1), already in `[0, 1]`, used directly.

`novelty(m)` and `repetition(m)` both derive from the same pairwise-similarity data `MemoryRepository.find_similar_pairs` computes for clustering (see below) — one pgvector self-join over a consolidation batch feeds both salience and clustering, not two separate passes:

```
novelty(m)    = 1 - max({cosine_sim(m, m') : m' in sample})          (1.0 if sample is empty)
repetition(m) = min(1, count({m' in sample : cosine_sim(m, m') >= repetition_similarity_threshold}) / salience_repetition_saturation_count)
```

where `sample` is up to `novelty_neighbor_sample_size` (default `10`) other episodes in the batch, `repetition_similarity_threshold` defaults to `0.85`, and `salience_repetition_saturation_count` (default `3`) caps repetition's contribution so a fact repeated 20 times doesn't score proportionally higher than one repeated 3 times — three corroborating mentions is already a strong signal; more repetitions add diminishing information; this is a raw cap, not a curve, so it is honestly labeled a heuristic, not a fitted diminishing-returns function.

**Why not more sophisticated now.** `w1..w4` are unweighted-by-data defaults, exactly as the Build Reference itself prescribes ("start equal-weighted, then A/B against retrieval-quality outcomes") — the A/B step requires an eval harness and real usage volume this project doesn't have yet, the same position Phase 1's `hybrid_search_weight_text`/`hybrid_search_weight_vector` are already in.

## Consolidation trigger

```
should_consolidate(unconsolidated_count, hours_since_last_run) =
    unconsolidated_count >= consolidation_episode_threshold
    OR hours_since_last_run >= consolidation_time_window_hours
    OR force == True   (trigger_reason = "manual", bypasses both checks above)
```

with `consolidation_episode_threshold` defaulting to `500` and `consolidation_time_window_hours` to `24.0` — the Build Reference's own proposed numbers, carried forward unchanged since no real usage volume exists yet to argue for a different pair. `hours_since_last_run` is computed against `ConsolidationRepository.get_last_run(namespace)`'s `started_at` (treated as unbounded / always-eligible if no run has ever occurred for the namespace). `trigger_reason` (`"count" | "time" | "manual"`) is recorded on the resulting `consolidation_runs` row for observability — which condition actually fired is real diagnostic signal for later tuning, not just an internal implementation detail.

## Distillation clustering

Union-find over a similarity graph, not k-means/HDBSCAN (ADR 0015 has the full infra-minimalism rationale): within one consolidation batch (bounded by `consolidation_batch_size`, default `500`), any pair of episodes with `cosine_sim(m, m') >= distillation_similarity_threshold` (default `0.80`) is joined into the same cluster. Clusters smaller than `distillation_min_cluster_size` (default `2`) are left un-distilled this pass — they are still marked consolidated (processed, not re-queued indefinitely), but produce no new semantic relation, since a single episode has nothing to abstract across; its facts were already captured by Phase 1's per-episode extraction at ingest time. Each qualifying cluster's raw texts are passed to `DistillationProvider.distill`, whose output flows through the same `extraction.pipeline.apply_extraction` path as Phase 1's per-episode extraction (with `derivation="distilled"` and `source_memory_ids` set to every cluster member).

**Why `0.80`, not a tighter or looser threshold.** `0.80` sits below Phase 1's fixture-replay tests' typical near-duplicate similarity range (empirically closer to `0.9+` for genuinely restated facts) but above the similarity two merely-related-but-distinct facts tend to share — the actual number is validated against a small synthetic set in `scripts/spike_similarity_clustering.py` before being locked into ADR 0015, mirroring Phase 1's "spike before ADR" discipline rather than being asserted from first principles here.

## What is NOT covered by this spec

Decay/forgetting curves (Phase 4), the full multi-factor retrieval-ranking formula (Phase 4 — this phase supplies only the raw `salience` score, not its place in `α·cosine_sim + β·R(t) + γ·salience + δ·trust + ε·graph_proximity`), trust/provenance scoring (Phase 4), episodic→procedural and failure→lesson distillation math (Phase 3, once SKILL.md's format gives distillation output somewhere concrete to go) — all remain out of scope for the same reason Phase 0/1's specs already gave: no real signal yet to design against.
