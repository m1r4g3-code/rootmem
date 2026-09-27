# ADR 0046: Auto-recall gates on a lexical match, not a blended relevance score

**Status:** Accepted
**Date:** 2026-09-27

## Context

Found while running the Phase 7 exit-criterion test against real Postgres and a real Voyage embedding: a prompt with no topical relation whatsoever to the one memory in a test namespace ("what is the weather in reykjavik" against "the deploy key rotates every friday") still scored above `ROOTMEM_AUTO_RECALL_MIN_SCORE=0.0` and got injected as context. Cosine similarity between two arbitrary embedded sentences is essentially never exactly zero, and the multi-factor `rank_score` (ADR 0022) blends that similarity with decay/trust/salience terms that reflect the memory's own attributes, not its relevance to the current prompt — so a fixed floor on the blended score cannot discriminate "truly related" from "happened to be a candidate." A manual, agent-invoked `search` tolerates this because a human or agent reading the results applies its own judgment; an unattended, automatic hook injecting context with nobody reviewing it cannot.

## Decision

`claude_code_auto_recall.py` calls `search` with `mode="text"`, not the default hybrid/semantic mode. `search_text`'s SQL requires an actual `to_tsvector(...) @@ plainto_tsquery(...)` match — a real keyword-overlap gate, enforced before ranking, not a threshold on a continuous score. `ROOTMEM_AUTO_RECALL_MIN_SCORE` stays as a secondary, optional refinement among genuine matches, not the sole gate.

## Alternatives considered

- Raising the score floor empirically instead: rejected — the blended score's baseline (from decay/trust/salience alone, with the relevance term near zero) is not a fixed, well-calibrated quantity across namespaces or memory ages, so any single fixed floor would eventually be wrong again, just less obviously.
- Gating on the ranked result's `breakdown` relevance sub-term instead of the total score: a more precise fix, deferred — it would need the REST client to expose `breakdown`, which isn't wired through today, and `mode="text"` already fully closes the specific failure found, with a named, honest cost (paraphrases with no shared words are missed).

## Consequences

Auto-recall will not surface a memory that shares no words with the prompt, even if it is semantically the right one — a real, deliberate scope reduction versus manual `search`'s own default. Named as a revisit item (relevance-only gating via `breakdown`) rather than solved fully here.
