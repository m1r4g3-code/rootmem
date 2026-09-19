# ADR 0020: Procedural/lesson distillation reuses `run_consolidation`'s single pass; `ProceduralDistillationProvider` is a new Protocol

**Status:** Accepted
**Date:** 2026-09-18

## Context

Phase 2's `consolidation/distill.py` already fetches one batch of unconsolidated episodes per pass (`memory_repository.list_unconsolidated`), computes salience, clusters near-duplicates, and distills qualifying clusters into semantic relations — all triggered by one mechanism (ADR 0012: an inline `ingest_session` auto-trigger plus an explicit `consolidate` tool/CLI, both sharing `maybe_run_consolidation`). Procedural distillation (ADR 0017) needs to run against episodes carrying `source_session_id`/`session_outcome` — a subset of the same batch already fetched for episodic→semantic distillation, not a different data source. Separately, procedural distillation's LLM call takes a fundamentally different input/output shape than Phase 2's existing `DistillationProvider.distill` (near-duplicate texts in, `ExtractionResult` entities/relations out): it takes multiple *ordered session traces* plus a `kind` discriminator, and produces a `SkillDraft` (name/description/body) with no entities or relations in it at all.

## Decision

**One trigger, one pass, one `consolidation_runs` row.** `run_consolidation`/`maybe_run_consolidation` gain a new stage, executed after the existing episodic→semantic stage, using the same already-fetched batch: group by session (ADR 0017), cluster success traces, gate by recurrence (see below), distill qualifying clusters/sessions, persist via `ProceduralMemoryRepository`. No second trigger, no second CLI command, no second `asyncio.create_task` — `consolidation/trigger.py`'s `should_consolidate` and every existing call site (the inline auto-trigger, the `consolidate` tool, `consolidation/cli.py`) are threaded with two new dependencies (`ProceduralMemoryRepository`, `ProceduralDistillationProvider`) and otherwise unchanged. `ConsolidationRun`/`consolidation_runs` gain `procedures_distilled`/`lessons_distilled` counts alongside Phase 2's existing `facts_distilled`, so one run record narrates everything one "sleep cycle" did.

**Asymmetric recurrence gating**, per the math spec: a success-trace cluster is distilled as a skill only if it meets `procedural_min_recurrence` (default `2`) members; a failure-outcome session is distilled as a lesson if it alone meets `lesson_min_recurrence` (default `1` — always satisfied by a single qualifying session).

**A new, separate `ProceduralDistillationProvider` Protocol** (`consolidation/procedural_protocols.py`), not an extension of `DistillationProvider`:

```python
class SkillDraft(BaseModel):
    name: str
    description: str
    body_markdown: str

class ProceduralDistillationProvider(Protocol):
    async def distill_procedure(
        self, traces: list[list[str]], context: ProceduralDistillationContext
    ) -> SkillDraft: ...
```

## Rationale

**Reusing one pass, not adding a second:** ADR 0012's own discipline against new infrastructure applies directly here, not just by analogy — a second trigger/CLI/tool for procedural distillation would duplicate machinery that already exists and already works, for data this phase doesn't need to fetch separately (it's the exact same batch). One `consolidation_runs` row also gives an operator a single place to see everything one pass accomplished, rather than needing to correlate two separate run logs to understand what happened to one batch of episodes.

**A new Protocol, not an extension, for the LLM provider:** applying ADR 0006's "different aggregate → different Protocol" test to *provider* Protocols, not just storage ones (ADR 0009 already established this pattern is not storage-specific — `EmbeddingProvider`/`ExtractionProvider` are themselves separate Protocols despite both being "an LLM/API call"). `DistillationProvider.distill`'s output type, `ExtractionResult`, is entities-and-relations-shaped — forcing a skill's name/description/step-list through it would mean inventing fake entities or relations purely to carry data that isn't actually an entity or a relation, a worse violation of honest typing than a second, small Protocol with its own genuinely-shaped output (`SkillDraft`).

**The asymmetric recurrence gate** is justified in full in `docs/math-spec/phase3-math-spec.md`: a single success is one data point, not yet a pattern; a single clear failure is already a usable caution.

## Alternatives considered

- **A second, parallel trigger/CLI/tool dedicated to procedural distillation.** Rejected: duplicates ADR 0012's already-solved trigger/execution problem for no new requirement — the batch, the trigger condition, and the execution model are all identical to what episodic→semantic distillation already needs.
- **Extend `DistillationProvider.distill`'s signature/return type to optionally produce a `SkillDraft` instead of an `ExtractionResult`.** Rejected: a `Protocol` method with two structurally unrelated possible return shapes selected by a runtime flag is worse typing than two small, honestly-named Protocols, and every call site would need to branch on which shape it got back regardless.
- **Symmetric recurrence gating (require repetition for lessons too).** Rejected per the math spec's rationale: a real failure mode is worth surfacing once, not withheld until it recurs — withholding it would silently discard a caution a later session could have used, for the sake of formula symmetry with no practical benefit.

## Consequences

- `consolidation/distill.py`'s `run_consolidation` grows one more stage and two more threaded dependencies, but its existing episodic→semantic stage is untouched — a regression in procedural distillation cannot silently break Phase 2's already-shipped, already-tagged behavior, and vice versa.
- `tests/unit/consolidation/test_distill_procedural_fake_backend.py` tests the new stage against all-fake dependencies (`ScriptedProceduralDistillationProvider`, `InMemoryProceduralMemoryRepository`), exactly matching Phase 2's own `test_distill_fake_backend.py` pattern.
- A malformed `SkillDraft` (failing `skill_format` validation) is logged and skipped for that cluster/session this pass, exactly mirroring the existing `DistillationError`-triggered degradation `consolidation/distill.py` already uses — procedural distillation failures never abort the rest of the consolidation pass.
