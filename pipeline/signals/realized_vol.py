"""
Close-to-close realized volatility, rolling window, annualized.

Deliberately just close-to-close here (not the full Parkinson/Garman-Klass/
Rogers-Satchell/Yang-Zhang suite from the original research pass) -- this is
the one estimator actually feeding the vol-regime gate used in the core
backtest. The others are documented results in data/derived/ but not yet
ported into this staged pipeline (see README scope note).
"""
import math
from typing import List, Sequence, Tuple

TRADING_DAYS_PER_YEAR = 252


def rolling_realized_vol(dates: Sequence[str], closes: Sequence[float],
                          window: int = 20) -> List[Tuple[str, float]]:
    """Annualized close-to-close vol over a trailing `window`-day span,
    ending at (and including) each date. First `window` dates are dropped --
    there is no valid trailing window for them yet."""
    assert len(dates) == len(closes)
    log_returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    ret_dates = dates[1:]

    out = []
    for i in range(window, len(log_returns) + 1):
        win = log_returns[i - window:i]
        mean = sum(win) / window
        var = sum((r - mean) ** 2 for r in win) / window
        vol = math.sqrt(var) * math.sqrt(TRADING_DAYS_PER_YEAR)
        out.append((ret_dates[i - 1], vol))
    return out
