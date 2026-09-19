# consolidation

The "sleep cycle". One consolidation pass (trigger in `trigger.py`,
orchestration in `distill.py`) runs salience scoring, episodic->semantic
distillation (Phase 2), and episodic->procedural (skill) and failure->lesson
distillation (Phase 3, `procedural_clustering.py`, `skill_format.py`). See
`docs/adr/0012-*` through `0021-*`.
