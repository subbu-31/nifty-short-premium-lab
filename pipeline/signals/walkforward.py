"""
Walk-forward (expanding-window) classifiers.

This is the single most important piece of shared infrastructure in the
pipeline: a first-pass version of the VWKS test in the original research
session used a *full-sample* quantile cut to classify each day, which is a
look-ahead bug -- day 10's tercile depended on data from day 500. Every
tercile/percentile gate in this pipeline (volatility regime, VIX percentile,
Hurst z-score baseline) must go through this module instead of hand-rolling
`np.percentile` on the whole series.

Contract: classify(d) uses only observations strictly before d's position in
the series (see min_history), never the value at d itself's future neighbors.
"""
from dataclasses import dataclass
from typing import Sequence


@dataclass
class Classification:
    date: str
    value: float
    tercile: str  # "Low" | "Mid" | "High"
    rank: float   # percentile rank within history at time of classification


def walkforward_tercile(dates: Sequence[str], values: Sequence[float], min_history: int = 60):
    """
    Classify each (date, value) pair into Low/Mid/High using only the
    expanding history of values *before* that date. The first `min_history`
    points are unclassifiable (insufficient history) and are omitted from
    the result -- this is expected, not a bug: there is no valid classification
    for them, so silently dropping is correct, not a gap to fill.
    """
    assert len(dates) == len(values), "dates and values must be aligned 1:1"
    out = []
    history: list[float] = []
    for d, v in zip(dates, values):
        if len(history) >= min_history:
            hist_sorted = sorted(history)
            rank = sum(1 for h in hist_sorted if h <= v) / len(hist_sorted)
            tercile = "Low" if rank < 1 / 3 else ("Mid" if rank < 2 / 3 else "High")
            out.append(Classification(date=d, value=v, tercile=tercile, rank=rank))
        history.append(v)
    return out


def walkforward_zscore(dates: Sequence[str], values: Sequence[float], window: int):
    """
    Trailing (not expanding) z-score: value at d vs. the mean/std of the
    `window` observations strictly before d. Used for the backwardation
    z-score signal, where a trailing window is the more natural baseline
    than an ever-expanding one (recent regime matters more than the whole
    history for "is this week's term structure unusual").
    """
    out = []
    for i in range(window, len(values)):
        win = values[i - window:i]
        mean = sum(win) / window
        var = sum((x - mean) ** 2 for x in win) / window
        std = var ** 0.5
        z = (values[i] - mean) / std if std > 0 else None
        out.append((dates[i], z))
    return out
