"""
Regression tests for the shared BSM solver. Every downstream backtest depends
on this being right -- a silent bug here propagates everywhere, the way the
streak-counter off-by-one did for the momentum signal.
"""
import sys, os, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.structure.black_scholes import price, delta, implied_vol


def test_atm_call_put_parity():
    # C - P = S - K*exp(-rT), must hold regardless of sigma
    S, K, T, r, sigma = 100.0, 100.0, 0.25, 0.05, 0.20
    c = price(S, K, T, r, sigma, "C")
    p = price(S, K, T, r, sigma, "P")
    expected = S - K * math.exp(-r * T)
    assert abs((c - p) - expected) < 1e-8


def test_deep_itm_call_converges_to_intrinsic_as_vol_shrinks():
    S, K, T, r = 150.0, 100.0, 0.1, 0.05
    c = price(S, K, T, r, 1e-4, "C")
    assert abs(c - (S - K * math.exp(-r * T))) < 0.5


def test_zero_time_price_is_intrinsic():
    assert price(110, 100, 0, 0.05, 0.2, "C") == 10
    assert price(90, 100, 0, 0.05, 0.2, "P") == 10
    assert price(90, 100, 0, 0.05, 0.2, "C") == 0


def test_call_delta_bounds():
    d = delta(100, 100, 0.25, 0.05, 0.20, "C")
    assert 0.0 < d < 1.0
    # deep ITM call delta approaches 1
    d_itm = delta(200, 100, 0.25, 0.05, 0.20, "C")
    assert d_itm > 0.95


def test_put_delta_bounds():
    d = delta(100, 100, 0.25, 0.05, 0.20, "P")
    assert -1.0 < d < 0.0
    d_itm = delta(50, 100, 0.25, 0.05, 0.20, "P")
    assert d_itm < -0.95


def test_implied_vol_round_trips_through_price():
    S, K, T, r, true_sigma = 24000, 24200, 0.02, 0.065, 0.14
    mkt_price = price(S, K, T, r, true_sigma, "C")
    recovered = implied_vol(mkt_price, S, K, T, r, "C")
    assert recovered is not None
    assert abs(recovered - true_sigma) < 1e-4


def test_implied_vol_returns_none_below_intrinsic():
    # a price at/below intrinsic has no solvable IV -- must return None,
    # not raise, so callers can skip the observation
    S, K, T, r = 100, 90, 0.25, 0.05
    intrinsic = S - K
    assert implied_vol(intrinsic - 1, S, K, T, r, "C") is None


def test_implied_vol_returns_none_at_zero_time():
    assert implied_vol(5.0, 100, 100, 0, 0.05, "C") is None


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
