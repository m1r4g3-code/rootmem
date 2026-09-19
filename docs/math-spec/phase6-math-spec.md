# Phase 6 Math Spec

## Token bucket (per identity)
Capacity `B` (burst) tokens, refilling at `r = rate_limit_per_minute / 60` tokens per second. On each call at time `t`: `tokens = min(B, tokens + r * (t - t_last))`; if `tokens >= 1` the call is allowed and `tokens -= 1`, otherwise it is throttled. Time is injected, and a clock that runs backwards is treated as zero elapsed time. Buckets are per identity id, held in process memory: correct for one node, not shared across nodes.

## Retrieval metrics
For a query with graded relevance `rel(d)` in {0,1,2,3} and a ranked list `d_1..d_k`:
- `recall@k` = (relevant items in top k) / (all relevant items), where relevant means `rel > 0`.
- `MRR` = `1 / rank` of the first relevant item, or 0 if none.
- `DCG@k = sum_i (2^rel(d_i) - 1) / log2(i + 1)`, `nDCG@k = DCG@k / IDCG@k` where IDCG is the DCG of the ideal ordering.
Reported as means over queries. With a small labeled set the differences are directional; no significance claim is made.

## Bundle digest
`content_sha256` = SHA-256 over the concatenated, canonical JSON lines of all bundle records in a fixed order. The manifest carries record counts and this digest; import recomputes and refuses a mismatch.

## Not resolved
Rate and burst defaults are provisional. Ranking-weight changes, if any, are decided from the evaluation and recorded in an ADR.
