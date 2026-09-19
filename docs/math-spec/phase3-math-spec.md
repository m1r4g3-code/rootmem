# Phase 3 Math/Algorithm Spec — Session-Trace Clustering, Recurrence Thresholds & SKILL.md Rendering

**Status:** Two formulas plus one formatting spec, each filling in exactly one placeholder Phase 2 left explicitly open (`docs/research/phase2-research-memo.md`'s carried-forward open question on clustering-signal generalization, and the SKILL.md format work named as this project's next scope since Phase 0) — all still provisional, with justification for what real signal each still needs before it stops being provisional (same discipline as Phase 0/1/2's specs).

## Session-trace grouping and similarity

**Why episode-level similarity (Phase 2's signal) doesn't transfer.** Phase 2's `distillation_similarity_threshold` clusters individual episodes because a fact is one flat claim — two restatements of "Alice works at Acme Corp" are directly comparable at the sentence level. A procedure is not one claim; it's an ordered sequence of steps whose *combination* constitutes the pattern. Comparing individual steps across sessions would merge unrelated attempts that merely share vocabulary (e.g. two different bugs whose first step is "the test fails"). The unit of comparison must be the session, not the episode.

**Grouping.** Within one consolidation batch (the same `list_unconsolidated` batch Phase 2's episodic→semantic stage already fetches, bounded by `consolidation_batch_size`), episodes are grouped by `(namespace, source_session_id, session_outcome)`. A group qualifies as a candidate session trace only if:

```
source_session_id is not None
AND session_outcome is not None
AND count(episodes in group) >= procedural_min_session_length   (default 2)
```

Episodes lacking a `session_id` (e.g. `remember`-sourced memories) or an explicit `session_outcome` are never considered — this is a deliberate floor, not a limitation to work around: a "procedure" requires the ordered-sequence and outcome structure `ingest_session` alone provides (see `docs/research/phase3-research-memo.md`).

**Trace summary and embedding.** Each qualifying group's episodes are ordered by `created_at` and joined into one synthetic trace-summary text (their `content` values, in order, newline-joined) — one `EmbeddingProvider.embed` call per qualifying session, reusing the exact provider already injected for `remember`/`ingest_session` (no new embedding infrastructure).

**Clustering.** Success-outcome traces are pairwise cosine-compared and passed through `consolidation/clustering.py`'s existing `cluster_by_similarity(ids, pairs, threshold)` — **reused completely unmodified**, since it is already a generic function over `(id, id, similarity)` triples regardless of what the ids/embeddings represent:

```
cosine_similarity(a, b) = (a . b) / (||a|| * ||b||)
pairs = {(trace_i, trace_j, cosine_similarity(embed(trace_i), embed(trace_j))) : i < j, both outcome="success"}
clusters = cluster_by_similarity(trace_ids, pairs, threshold=procedural_session_similarity_threshold)
```

Failure-outcome traces are never clustered with each other or with success traces — each qualifying failure session is treated as its own single-trace "cluster" of size 1, since `lesson_min_recurrence` (below) does not require repetition to distill a caution from it.

**Distillation gating (asymmetric recurrence).**

```
distill_as_skill(cluster)  = cluster.kind == "success" AND len(cluster) >= procedural_min_recurrence   (default 2)
distill_as_lesson(session) = session.outcome == "failure" AND 1 >= lesson_min_recurrence                (default 1, always true)
```

**Why the asymmetry.** A single successful run-through is one data point — indistinguishable from luck, a one-off, or an approach that happens to work in that exact context. Calling it "the way to do this" after seeing it once would overfit to a sample size of one. A single clear failure carries different information: it is already worth recording as a concrete caution ("this approach hit this specific problem"), independent of whether it recurs — the cost of surfacing one real failure mode once is low, and waiting for it to repeat before recording it would silently discard a lesson a later session could have used. This mirrors ordinary human experience: people trust a technique more after seeing it work several times, but usually only need to be burned once by a specific failure to remember to avoid it. Both thresholds are named, provisional defaults — see "What this does not yet resolve" below.

**Why `procedural_session_similarity_threshold=0.80`, carried over from Phase 2's `distillation_similarity_threshold`.** The number is inherited as a starting hypothesis, not re-derived from first principles — but it operates on a materially different embedding target (a multi-step trace summary, not a single sentence), so it is **not** assumed valid without re-validation. `scripts/spike_session_trace_clustering.py` (Prototype stage, run before finalizing ADR 0017) checks it empirically against real `voyage-4` embeddings of two differently-worded successful traces plus one distractor, exactly mirroring the spike-before-ADR discipline `scripts/spike_similarity_clustering.py` established for Phase 2's own threshold.

## SKILL.md rendering and validation

Fills in the "SKILL.md format work" every prior phase's docs named as forward-looking scope since Phase 0, now made concrete against the published agentskills.io spec (December 2025):

```
validate_skill_name(name):
    require name matches ^[a-z0-9]+(-[a-z0-9]+)*$
    require len(name) <= skill_name_max_length   (default 64)

validate_skill_description(description):
    require len(description) <= skill_description_max_length   (default 1024)
    # "states what+when to use it" is a content-quality property the LLM
    # distillation prompt is responsible for; this validator only enforces
    # the spec's one hard, mechanically-checkable constraint (length).

render_skill_markdown(draft: SkillDraft) -> str:
    return f"""---
name: {draft.name}
description: {draft.description}
---

{draft.body_markdown}
"""
```

A `SkillDraft` failing either validator is never persisted — the consolidation pass logs a degraded outcome and skips that cluster for the current pass (the exact `DistillationError`-triggered graceful-degradation pattern `consolidation/distill.py` already uses for Phase 2's own distillation calls), rather than storing a non-conformant `procedural_memories` row. This keeps every stored row a guarantee, not a best-effort: anything `get_skill` returns is, by construction, valid SKILL.md content.

**Why no `scripts`/`references`/`assets` subdirectory support yet.** The published spec's progressive-disclosure subdirectories are optional, and nothing in this phase's exit criterion or its underlying distillation signal (short, LLM-abstracted procedures from a handful of session traces) produces content that needs them — a skill distilled from 2-3 short sessions is a few paragraphs and a short step list, not a multi-file bundle. Supporting them now would be speculative infrastructure for a shape of output this phase never actually produces; revisit only if a real distilled skill's content outgrows a single markdown body.

## What this does not yet resolve

- **`procedural_min_recurrence=2`/`lesson_min_recurrence=1`'s exact values.** The *asymmetry* is a considered design choice (see above); the specific numbers are not empirically derived — there is no real usage data yet to argue for different constants, the same "no signal yet" position Phase 2's `bayesian_prior_strength`/salience weights were shipped in.
- **Whether `procedural_session_similarity_threshold=0.80` holds at real usage scale**, beyond what the spike's small synthetic set can show — carried forward to Phase 4's research memo alongside Phase 2's own analogous open item for `distillation_similarity_threshold`.
- **Trace-summary construction itself (naive newline-join of ordered episode contents) is a simple starting point, not a validated abstraction.** A more sophisticated summarization step (e.g. an LLM pre-pass condensing a long session before embedding) is deliberately not added here — this phase's exit criterion uses short, 3-step sessions where naive joining is adequate; revisit if real session traces prove long enough that raw joining degrades embedding quality.

## What is NOT covered by this spec

Decay/forgetting curves, trust/provenance scoring, the multi-factor retrieval-ranking formula, and the tamper-evident audit log (all Phase 4, unchanged since Phase 2's spec); a skill "usage/effectiveness" scoring formula (Phase 4's trust/provenance territory, not this phase's — see `docs/requirements/phase3-requirements.md`'s non-goals); any Bayesian belief/confidence math for `procedural_memories` (deliberately not given a confidence field this phase — a distilled skill/lesson is not a contestable factual claim the way a `relations` row is); a real benchmark-lift measurement methodology (SWE-bench Verified/Terminal-Bench scoring — explicitly out of scope per ADR 0021, revisit only if a real benchmark harness is built in Phase 4+).
