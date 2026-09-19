"""
Synthetic option-chain fixture -- a data source the engine can run against
with no vendor data and no network.

The real chain archive is not redistributable (see data/README.md), which
means the backtest engine ships untested against anything resembling a
multi-session run. This fixture closes that gap. It fabricates a market
whose properties are *known by construction*, so tests can assert what the
engine should do rather than what some particular week of NIFTY happened to
do.

What is controlled here, and why each one matters:

  realized_vol   the vol actually driving the spot path
  implied_vol    the vol every chain quote is priced at

Setting implied_vol > realized_vol manufactures a volatility risk premium of
a known sign. Setting them equal removes it. A short-premium engine that
cannot tell those two worlds apart is broken, and that is a test worth
having.

This fixture is NOT a market simulator. Prices are Black-Scholes exact at a
flat vol -- no smile, no skew, no bid/ask, no volume, no gaps, no jumps.
Nothing it produces is evidence about NIFTY. It exercises machinery.
"""
from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from pipeline.structure.black_scholes import price as bs_price  # noqa: E402

TRADING_DAYS = 252
STRIKE_STEP = 50
ENTRY_DTE = 4
RISK_FREE_RATE = 0.065  # matches engine.RISK_FREE_RATE


@dataclass
class SyntheticMarket:
    """A sequence of weekly expiries with a GBM spot path underneath.

    Session keys are plain ``"S0000"``-style strings: the engine treats dates
    as opaque keys and never parses them, so fabricating a calendar would add
    surface area without adding coverage.
    """

    n_expiries: int = 71          # matches the real study's 71-week window
    spot_0: float = 24_000.0
    realized_vol: float = 0.12    # annualised, drives the path
    implied_vol: float = 0.15     # annualised, prices every quote
    strikes_each_side: int = 20
    seed: int = 7

    _spot: Dict[str, float] = field(default_factory=dict, init=False)
    _pairs: List[Tuple[str, str]] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        import random

        rng = random.Random(self.seed)
        s = self.spot_0
        dt = 1.0 / TRADING_DAYS
        drift = -0.5 * self.realized_vol ** 2 * dt
        diffusion = self.realized_vol * math.sqrt(dt)

        # Each expiry: an entry session ENTRY_DTE days earlier, then settlement.
        for i in range(self.n_expiries):
            entry = f"S{i:04d}E"
            self._spot[entry] = s
            for _ in range(ENTRY_DTE):
                s *= math.exp(drift + diffusion * rng.gauss(0.0, 1.0))
            expiry = f"S{i:04d}X"
            self._spot[expiry] = s

    # ---- the two callables the engine asks for -------------------------

    def spot(self, date: str) -> float:
        return self._spot[date]

    def chain(self, entry_date: str, expiry_date: str) -> Dict[Tuple[int, str], float]:
        """Closing price for every strike, priced at ``implied_vol``.

        Quotes below half a point are dropped rather than returned as dust --
        the real chain has no liquid sub-0.5 quotes either, and keeping them
        would let the IV solver chew on prices no one could trade.
        """
        S = self._spot[entry_date]
        T = self.T_years
        atm = round(S / STRIKE_STEP) * STRIKE_STEP
        out: Dict[Tuple[int, str], float] = {}
        for n in range(-self.strikes_each_side, self.strikes_each_side + 1):
            k = int(atm + n * STRIKE_STEP)
            for side, opt in (("CE", "C"), ("PE", "P")):
                px = bs_price(S, k, T, RISK_FREE_RATE, self.implied_vol, opt)
                if px > 0.5:
                    out[(k, side)] = px
        return out

    # ---- helpers -------------------------------------------------------

    @property
    def T_years(self) -> float:
        return ENTRY_DTE / 365.0

    def sessions(self) -> List[Tuple[str, str]]:
        """(entry_date, expiry_date) for every expiry, in order."""
        return [(f"S{i:04d}E", f"S{i:04d}X") for i in range(self.n_expiries)]

    def settlement_spot(self, expiry_date: str) -> float:
        return self._spot[expiry_date]
