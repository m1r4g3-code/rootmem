# Phase 8 Math Spec — Decay-Adjusted Contest Reconciliation

No new decay model and no new belief-update model — this phase composes two formulas that already exist (Phase 2's Bayesian belief, Phase 4's retention curve) over a pair of relations, rather than deriving anything new.

## Decayed confidence

For a relation `r` with belief `(alpha, beta)` and transaction time `recorded_at`, at reconciliation time `now`:

```
belief_confidence(r) = r.belief_alpha / (r.belief_alpha + r.belief_beta)          [existing, Phase 2]

retention(r, now) = exp(-elapsed_days / stability_days)                            [existing, Phase 4]
  elapsed_days   = max(0, (now - r.recorded_at).days)
  stability_days = decay_base_stability_days * (1 + ln(1 + access_count)) * (1 + salience)
                 = decay_base_stability_days                                       [relations: access_count=0, salience=None]

decayed(r, now) = belief_confidence(r) * retention(r, now)
```

Relations carry no access-tracking, so `stability_days` reduces to the flat `decay_base_stability_days` constant for every relation — the *only* thing driving `retention` apart between two contested relations is how much earlier one was `recorded_at` than the other.

## Reconciliation decision

For a contested pair `(old, new)` with `old.recorded_at <= new.recorded_at`, reusing the existing `bayesian_supersede_margin` (call it `m`):

```
d_old = decayed(old, now)
d_new = decayed(new, now)

if d_new > d_old + m:  supersede old, new wins
elif d_old > d_new + m: supersede new, old wins (retroactively)
else:                   leave both contested
```

This is exactly `resolve_contradiction`'s own supersede-margin test, applied to decayed confidence instead of raw confidence — the same decision shape, a different pair of inputs.

## Why this eventually favors the newer side, and why that's named as a choice, not a derivation

Since `old.recorded_at <= new.recorded_at`, `old`'s `elapsed_days` is always `>= new`'s, so `retention(old, now) <= retention(new, now)` for any `now`. Both `belief_confidence` values are fixed (nothing here changes alpha/beta) — decay only ever discounts, never inflates, either side. As `now` grows without bound, `d_old -> 0` and `d_new -> 0`, but `d_old` reaches any given threshold strictly before `d_new` does (having started decaying earlier), so **for a sufficiently large elapsed time with no new evidence on either side, the pair always eventually resolves "new wins."** How long "sufficiently large" is depends entirely on the original confidence gap (a much stronger old belief takes proportionally longer for decay to erode past). This asymmetry is a deliberate, stated simplification (see the research memo) — a genuine two-sided comparison in the short-to-medium term, but a foregone conclusion in the very long term, for lack of any mechanism (not built here) letting the older side "refresh" itself the way an accessed memory can.

## Grace period

A contested pair is only eligible when `now - max(old.recorded_at, new.recorded_at) >= min_contest_age_hours` (default 1 hour) — an explicit `ruminate(..., force=True)` call bypasses this, exactly mirroring `consolidate(force=True)`'s own bypass of its count/time trigger.
