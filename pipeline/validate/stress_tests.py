"""
Reusable stress-test battery: run against ANY P&L or effect series, not
hand-coded per finding.

This is the module that would have made every backtested variant this
session (regime-blend, asymmetric wing, momentum-tilt, the VIX-percentile
gate) get the same rigor for free instead of needing bespoke stress-test
code written from scratch each time. In the original session, this uniform
battery is what caught the calendar-spread finding decaying to nothing in
the second half, and confirmed the VIX-percentile gate strengthening under
the same tests -- the discipline is only worth anything if it's applied
identically to every candidate finding, confirmed or not.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional
import numpy as np
from scipy import stats


@dataclass
class StressTestResult:
    temporal_split: dict
    outlier_sensitivity: dict
    permutation_vs_zero: dict


def temporal_split(values: np.ndarray, labels: Optional[List[str]] = None) -> dict:
    """First-half vs second-half stability. A real finding should point the
    same direction in both halves; a finding that reverses or dies in the
    second half is very likely decayed or a fluke of the discovery window."""
    n = len(values)
    mid = n // 2
    first, second = values[:mid], values[mid:]
    t1, p1 = stats.ttest_1samp(first, 0) if len(first) > 1 else (float("nan"), float("nan"))
    t2, p2 = stats.ttest_1samp(second, 0) if len(second) > 1 else (float("nan"), float("nan"))
    return {
        "first_half": {"n": len(first), "mean": float(first.mean()), "t": float(t1), "p": float(p1)},
        "second_half": {"n": len(second), "mean": float(second.mean()), "t": float(t2), "p": float(p2)},
        "same_direction": bool(np.sign(first.mean()) == np.sign(second.mean())),
    }


def outlier_sensitivity(values: np.ndarray, drop_n: int = 1) -> dict:
    """Drop the `drop_n` largest-magnitude observations and recheck
    significance. A finding that only clears significance because of one or
    two extreme trades is not a finding -- it's an anecdote with a p-value
    attached."""
    order = np.argsort(-np.abs(values))
    trimmed = np.delete(values, order[:drop_n])
    t_full, p_full = stats.ttest_1samp(values, 0)
    t_trim, p_trim = stats.ttest_1samp(trimmed, 0)
    return {
        "full": {"n": len(values), "t": float(t_full), "p": float(p_full)},
        "trimmed": {"n": len(trimmed), "t": float(t_trim), "p": float(p_trim), "dropped": drop_n},
    }


def permutation_test_vs_random_subset(all_values: np.ndarray, subset: np.ndarray,
                                        n_perm: int = 20000, seed: int = 42) -> dict:
    """
    Is `subset`'s mean distinguishable from the mean of a random same-size
    subset of `all_values`? This is the test that separates "this selection
    rule beats picking any N weeks at random" from "this selection rule
    just happens to contain some good weeks." Every regime-gate finding in
    the original session was run through this -- most did NOT clear it.
    """
    rng = np.random.default_rng(seed)
    n = len(subset)
    observed = subset.mean()
    draws = np.array([rng.choice(all_values, size=n, replace=False).mean() for _ in range(n_perm)])
    pctile = float((draws < observed).mean())
    p_value = 2 * min(pctile, 1 - pctile)
    return {"observed_mean": float(observed), "null_mean": float(draws.mean()),
            "null_std": float(draws.std()), "percentile": pctile * 100, "p_value": p_value}


def multiple_comparisons_correction(groups: Dict[str, np.ndarray], n_perm: int = 20000,
                                      seed: int = 42) -> dict:
    """
    Family-wise corrected p-value across several subgroup tests (e.g. one
    t-test per weekday, or per structure). Reports the minimum p-value
    actually observed AND how often that minimum would arise by chance
    alone across this many groups. This is the exact test that retracted
    the "Tuesday/Thursday" weekday concentration in the original session
    (individual p as low as 0.036, family-wise p=0.38 -- noise).
    """
    labels = list(groups.keys())
    all_values = np.concatenate(list(groups.values()))
    group_sizes = [len(v) for v in groups.values()]

    def min_p(values_by_group):
        best = 1.0
        idx = 0
        for size in group_sizes:
            chunk = values_by_group[idx:idx + size]
            idx += size
            if len(chunk) < 2 or len(chunk) == len(values_by_group):
                continue
            _, p = stats.ttest_1samp(chunk, 0)
            best = min(best, p)
        return best

    observed = np.concatenate(list(groups.values()))
    observed_min_p = min_p(observed)

    rng = np.random.default_rng(seed)
    null_min_ps = []
    for _ in range(n_perm):
        shuffled = rng.permutation(all_values)
        null_min_ps.append(min_p(shuffled))
    null_min_ps = np.array(null_min_ps)
    family_wise_p = float((null_min_ps <= observed_min_p).mean())

    return {"labels": labels, "observed_min_p": float(observed_min_p),
            "family_wise_p": family_wise_p, "n_groups": len(labels)}
