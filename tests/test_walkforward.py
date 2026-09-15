"""
Regression tests for the walk-forward classifier -- the module that exists
specifically because a full-sample-quantile look-ahead bug was found and
fixed in the original research session (a VWKS quintile test). These tests
are written adversarially: the whole point is to fail loudly if a future
edit reintroduces a peek at future data.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.signals.walkforward import walkforward_tercile, walkforward_zscore


def _dates(n):
    return [f"2025-01-{i+1:02d}" if i < 31 else f"2025-02-{i-30:02d}" for i in range(n)]


def test_first_min_history_points_are_dropped_not_classified():
    dates = _dates(70)
    values = [float(i) for i in range(70)]
    out = walkforward_tercile(dates, values, min_history=60)
    assert len(out) == 10  # only points after the 60-day warmup are classified
    assert out[0].date == dates[60]


def test_classification_is_blind_to_future_values():
    """
    Adversarial check: classify a rising series two ways -- once with the
    real tail, once with the tail replaced by extreme outliers. Every
    classification for dates BEFORE the tail must be identical in both runs.
    If it isn't, the classifier is peeking forward.
    """
    dates = _dates(100)
    base_values = [float(i % 20) for i in range(80)]  # oscillating baseline

    tail_normal = base_values + [float(i % 20) for i in range(20)]
    tail_extreme = base_values + [10_000.0 + i for i in range(20)]  # wildly different future

    out_normal = walkforward_tercile(dates, tail_normal, min_history=30)
    out_extreme = walkforward_tercile(dates, tail_extreme, min_history=30)

    # compare classifications for every date that exists before the tail begins
    normal_by_date = {c.date: (c.tercile, c.rank) for c in out_normal if c.date in dates[:80]}
    extreme_by_date = {c.date: (c.tercile, c.rank) for c in out_extreme if c.date in dates[:80]}
    assert normal_by_date == extreme_by_date, (
        "classification of past dates changed when future values changed -- look-ahead bug"
    )


def test_tercile_boundaries_are_roughly_balanced_on_uniform_data():
    dates = _dates(300)
    values = [float(i % 97) for i in range(300)]  # pseudo-uniform spread
    out = walkforward_tercile(dates, values, min_history=60)
    counts = {"Low": 0, "Mid": 0, "High": 0}
    for c in out:
        counts[c.tercile] += 1
    total = sum(counts.values())
    # no bucket should be wildly imbalanced on roughly-uniform data
    for k in counts:
        assert 0.15 < counts[k] / total < 0.55


def test_zscore_uses_only_trailing_window():
    """
    A spike at index 45 in an otherwise-flat series: the trailing window
    *before* the spike is zero-variance (z is correctly None -- the spike
    cannot see itself). Once the spike enters the trailing window for later
    dates, those dates get a well-defined, negative z (current flat value is
    now below a window mean the spike pulled up). This directly exercises
    "trailing means strictly before the date," not "centered on the date."
    """
    dates = _dates(50)
    values = [1.0] * 40 + [1.0, 1.0, 1.0, 1.0, 1.0, 100.0, 1.0, 1.0, 1.0, 1.0]
    out_by_date = dict(walkforward_zscore(dates, values, window=10))

    spike_date = dates[45]
    after_spike_date = dates[46]  # spike is now inside this date's trailing window
    before_spike_date = dates[43]  # trailing window here is still all 1.0

    assert out_by_date[before_spike_date] is None  # zero-variance window -> undefined
    assert out_by_date[spike_date] is None          # spike can't be in its own trailing window
    assert out_by_date[after_spike_date] is not None
    assert out_by_date[after_spike_date] < 0        # flat value now reads as below-window-mean


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
