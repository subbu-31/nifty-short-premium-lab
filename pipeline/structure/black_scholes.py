"""
Black-Scholes pricing, delta, and implied-vol solver for European index options.

Used throughout the pipeline for delta-targeted strike selection. Deliberately
simple (flat risk-free rate, no dividend yield) -- both assumptions are
disclosed in docs/methodology.md rather than hidden in the math.
"""
import math
from scipy.optimize import brentq
from scipy.stats import norm


def price(S: float, K: float, T: float, r: float, sigma: float, option: str) -> float:
    """European option price. option is 'C' or 'P'. T in years."""
    if T <= 0 or sigma <= 0:
        return max(0.0, (S - K) if option == "C" else (K - S))
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if option == "C":
        return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def delta(S: float, K: float, T: float, r: float, sigma: float, option: str) -> float:
    if T <= 0 or sigma <= 0:
        if option == "C":
            return 1.0 if S > K else 0.0
        return -1.0 if S < K else 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    return norm.cdf(d1) if option == "C" else norm.cdf(d1) - 1


def implied_vol(mkt_price: float, S: float, K: float, T: float, r: float, option: str):
    """Returns None if the price is at/below intrinsic or T<=0 -- these are not
    solvable/meaningful IVs, not errors, so callers should treat None as
    'skip this observation', not retry with different bounds."""
    intrinsic = max(0.0, (S - K) if option == "C" else (K - S))
    if mkt_price <= intrinsic + 1e-6 or T <= 0:
        return None
    try:
        return brentq(lambda s: price(S, K, T, r, s, option) - mkt_price, 1e-4, 5.0, xtol=1e-6)
    except ValueError:
        return None
