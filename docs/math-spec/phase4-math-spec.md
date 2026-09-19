# Phase 4 Math Spec (provisional)

## Retention
`R = exp(-dt / S)`, `dt` = days since `last_accessed_at` (or `created_at` if never accessed).
`S = S0 * (1 + ln(1 + access_count)) * (1 + salience)`, `S0 = decay_base_stability_days` (default 7); NULL salience is treated as 0.
R is in (0,1], monotone decreasing in dt, monotone increasing in access_count and salience.

## Trust (memory)
`trust = reliability(source) * confidence`, both in [0,1]; an unknown source uses `trust_default_reliability` (0.5).

## Skill effectiveness
Beta(alpha, beta) with prior (1,1). A reported success adds reliability-weighted evidence to alpha, a failure to beta (reusing `apply_evidence`). `effectiveness = alpha/(alpha+beta)` is the trust term for skills and lessons.

## Graph proximity
1.0 if the memory is linked to the entity named in the query, 0.5 if linked to a 1-hop neighbour, else 0.

## Rank score
`score = (a*rel + b*R + g*sal + d*trust + e*prox) / (sum of weights of present terms)`.
`rel` is the existing hybrid score clipped to [0,1]. Default weights: a=0.50, b=0.15, g=0.10, d=0.15, e=0.10. Absent terms (NULL salience, no graph entity in query) are dropped and the weights renormalize, so a missing signal is never a penalty.

## Audit chain
`row_hash = SHA256(prev_hash || canonical_json(namespace, seq, actor, action, target_type, target_id, payload, created_at))`; genesis `prev_hash` is 64 zeros. `verify_chain` recomputes sequentially and returns the first index where a stored hash or link disagrees.

## Not resolved
Default weights and S0 are untuned (no usage corpus). Exponential vs power-law is checked by `scripts/spike_decay_curves.py`. The 0.80 clustering thresholds remain unvalidated at scale.
