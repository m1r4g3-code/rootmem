# ADR 0023: Decay is exponential with access- and salience-grown stability, computed at read time

**Status:** Accepted (curve family confirmed by `scripts/spike_decay_curves.py`, see below)
**Date:** 2026-09-19

## Context

R(t) needs an input, and no access tracking exists.

## Decision

Add `last_accessed_at` and `access_count` to `memories`. Retention is `exp(-dt/S)` with stability S growing with access count and salience. It is computed at read time and never rewrites or deletes anything (ADR 0004).

## Spike findings (`scripts/spike_decay_curves.py`)

Compared `exp(-t/S)` with the power-law `1/(1 + t/S)` at base stability 7 days (never accessed: S=7.0d; five accesses: S=19.5d):

| age (days) | exp cold | exp warm | power cold | power warm |
|---|---|---|---|---|
| 7 | 0.368 | 0.699 | 0.500 | 0.736 |
| 30 | 0.014 | 0.215 | 0.189 | 0.395 |
| 90 | 0.000 | 0.010 | 0.072 | 0.178 |
| 365 | 0.000 | 0.000 | 0.019 | 0.051 |

Both families keep a reinforced memory above an unreinforced one at every age. They differ in the tail: exponential goes to about zero past ~90 days for unreinforced memories, so retention stops separating old memories from each other; power-law keeps a small separating signal.

## Decision on the curve

Keep exponential. It has one interpretable parameter and matches the spaced-repetition model the stability growth is borrowed from. The tail flatness costs little because retention is one bounded term (default weight 0.15) beside relevance (0.50), so a very old memory that is highly relevant still ranks. Revisit trigger: real usage showing that very old, unreinforced memories need to be told apart by age.

## Alternatives considered

- Power-law curve: the spike comparator; better tail, less interpretable, not chosen.
- A background job that rewrites scores or deletes: rejected, destructive and needs a worker.

## Consequences

Reads now write (access tracking). This is a batched update, and failures must not fail the read. `search` with `as_of` is a what-if query and does not write.
