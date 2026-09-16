# extraction

LLM-based entity/relation extraction (Haiku-tier, ADR 0009) plus
deterministic contradiction resolution (ADR 0008 — the real
confidence-weighted Bayesian version is Phase 2's, once there's
retrieval-outcome feedback to calibrate it against).

- `models.py` — `ExtractedEntity`/`ExtractedRelation` (by *name*, not graph
  id — resolving names to ids is `pipeline.py`'s job, not the provider's).
- `protocols.py` — the `ExtractionProvider` port.
- `anthropic_provider.py` — the real implementation, structured output via
  forced tool-calling.
- `fakes/scripted_provider.py` — a registered-lookup fake for unit tests.
- `pipeline.py` — `apply_extraction`: resolves names to entity ids via
  `GraphRepository.upsert_entity`, then calls `create_relation` (which
  already owns the contradiction rule internally — this module doesn't
  re-decide it) and `link_memory_entity`.
