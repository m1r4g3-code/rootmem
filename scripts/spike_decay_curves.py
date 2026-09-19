"""Spike (ADR 0023): exponential vs power-law retention on synthetic access
patterns. Pure, no I/O.

Question: does the ranking layer behave sensibly under `exp(-t/S)` with
stability growing on access, or would a power-law `(1 + t/S)^-1` be a better
fit? Two properties matter for ranking:
  1. Reinforcement ordering: a reinforced memory must outrank an unreinforced
     one of the same age at every age.
  2. Tail: at old ages, does the curve still separate memories, or does it
     flatten to ~0 and stop informing the ranking?
"""

from __future__ import annotations

import math

from rootmem.retrieval.decay import RetentionParams, stability_days

PARAMS = RetentionParams(base_stability_days=7.0)
AGES_DAYS = (1, 7, 30, 90, 365)


def exponential(age_days: float, stability: float) -> float:
    return math.exp(-age_days / stability)


def power_law(age_days: float, stability: float) -> float:
    return 1.0 / (1.0 + age_days / stability)


def main() -> None:
    s_cold = stability_days(0, None, PARAMS)
    s_warm = stability_days(5, None, PARAMS)
    print(f"stability: never-accessed={s_cold:.1f}d, 5 accesses={s_warm:.1f}d")
    print(f"{'age(d)':>7} | {'exp cold':>9} {'exp warm':>9} {'gap':>8} | "
          f"{'pow cold':>9} {'pow warm':>9} {'gap':>8}")
    ordering_ok = True
    for age in AGES_DAYS:
        e_cold, e_warm = exponential(age, s_cold), exponential(age, s_warm)
        p_cold, p_warm = power_law(age, s_cold), power_law(age, s_warm)
        ordering_ok &= e_warm > e_cold and p_warm > p_cold
        print(f"{age:>7} | {e_cold:9.4f} {e_warm:9.4f} {e_warm - e_cold:8.4f} | "
              f"{p_cold:9.4f} {p_warm:9.4f} {p_warm - p_cold:8.4f}")
    print(f"reinforcement ordering holds for both families: {ordering_ok}")


if __name__ == "__main__":
    main()
