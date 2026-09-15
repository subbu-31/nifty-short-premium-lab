"""
Core structure backtest: delta-targeted strike selection -> hold to expiry ->
cost-adjusted P&L, for straddle / strangle / iron condor.

This is a *translation* of the exact logic used in the original research
session into a reusable, testable form -- it needs an `OptionChainSource`
(see data/README.md) to actually run, since the raw NSE option-chain data
is not distributed with this repo (unclear vendor licensing; see
docs/methodology.md). The pre-computed outputs of running this engine
against that data are in data/derived/.
"""
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple

from pipeline.structure.black_scholes import price, delta, implied_vol
from pipeline.cost.cost_scenarios import CostScenario, net_pnl

RISK_FREE_RATE = 0.065  # flat assumption, no dividend yield -- see docs/methodology.md
TARGET_SHORT_DELTA = 0.20
TARGET_WING_DELTA = 0.08
ENTRY_DAYS_BEFORE_EXPIRY = 4


@dataclass
class ChainQuote:
    strike: int
    option_type: str  # "CE" or "PE"
    price: float


# A data source just needs to answer: "closing prices for every strike on
# this date, for this expiry" and "spot close on this date." Swap in a real
# Kite/NSE-backed implementation without touching anything below.
OptionChainSource = Callable[[str, str], Dict[Tuple[int, str], float]]
SpotCloseSource = Callable[[str], float]


def _nearest_by_delta(candidates, target_delta):
    return min(candidates, key=lambda kd: abs(kd[1] - target_delta))[0]


def price_structure_at_entry(entry_date: str, expiry_date: str, T_years: float,
                               chain: OptionChainSource, spot: SpotCloseSource):
    """
    Solves IV/delta for every strike on entry_date, selects delta-targeted
    short strikes (+wings for the condor), returns a trade ticket. Returns
    None if the chain doesn't have enough liquid strikes to solve -- this is
    a real, expected outcome for thin early-history data, not an error to
    propagate.
    """
    S = spot(entry_date)
    raw = chain(entry_date, expiry_date)

    solved = {}
    for (k, side), px in raw.items():
        if px is None or px <= 0:
            continue
        opt = "C" if side == "CE" else "P"
        iv = implied_vol(px, S, k, T_years, RISK_FREE_RATE, opt)
        if iv is None or not (0.02 < iv < 3.0):
            continue
        d = delta(S, k, T_years, RISK_FREE_RATE, iv, opt)
        solved[(k, side)] = {"price": px, "iv": iv, "delta": d}

    if len(solved) < 6:
        return None

    calls = [(k, v["delta"]) for (k, s), v in solved.items() if s == "CE"]
    puts = [(k, v["delta"]) for (k, s), v in solved.items() if s == "PE"]
    if not calls or not puts:
        return None

    atm_strike = min(solved.keys(), key=lambda ks: abs(ks[0] - S))[0]
    short_call_k = _nearest_by_delta(calls, TARGET_SHORT_DELTA)
    short_put_k = _nearest_by_delta(puts, -TARGET_SHORT_DELTA)

    far_calls = [(k, d) for k, d in calls if k > short_call_k]
    far_puts = [(k, d) for k, d in puts if k < short_put_k]
    long_call_k = _nearest_by_delta(far_calls, TARGET_WING_DELTA) if far_calls else None
    long_put_k = _nearest_by_delta(far_puts, -TARGET_WING_DELTA) if far_puts else None

    return {
        "S_entry": S, "atm_strike": atm_strike,
        "short_call_k": short_call_k, "short_put_k": short_put_k,
        "long_call_k": long_call_k, "long_put_k": long_put_k,
        "chain": solved,
    }


def _intrinsic(k, side, S):
    return max(0.0, S - k) if side == "CE" else max(0.0, k - S)


def settle(ticket, S_exit: float, scenario: CostScenario):
    """Given an entry ticket and the expiry-day settlement spot, returns
    net P&L for straddle, strangle, and (if wings were found) condor."""
    chain = ticket["chain"]
    atm, sc, sp = ticket["atm_strike"], ticket["short_call_k"], ticket["short_put_k"]

    straddle_credit = chain[(atm, "CE")]["price"] + chain[(atm, "PE")]["price"]
    straddle_gross = straddle_credit - (_intrinsic(atm, "CE", S_exit) + _intrinsic(atm, "PE", S_exit))
    straddle_net = net_pnl(straddle_gross, straddle_credit, n_short_legs=2, n_wing_legs=0, scenario=scenario)

    strangle_credit = chain[(sc, "CE")]["price"] + chain[(sp, "PE")]["price"]
    strangle_gross = strangle_credit - (_intrinsic(sc, "CE", S_exit) + _intrinsic(sp, "PE", S_exit))
    strangle_net = net_pnl(strangle_gross, strangle_credit, n_short_legs=2, n_wing_legs=0, scenario=scenario)

    result = {"straddle_gross": straddle_gross, "straddle_net": straddle_net,
              "strangle_gross": strangle_gross, "strangle_net": strangle_net}

    lc, lp = ticket["long_call_k"], ticket["long_put_k"]
    if lc is not None and lp is not None and (lc, "CE") in chain and (lp, "PE") in chain:
        wing_cost = chain[(lc, "CE")]["price"] + chain[(lp, "PE")]["price"]
        wing_exit = _intrinsic(lc, "CE", S_exit) + _intrinsic(lp, "PE", S_exit)
        condor_gross = strangle_gross - wing_cost + wing_exit
        condor_net = net_pnl(condor_gross, strangle_credit, n_short_legs=2, n_wing_legs=2, scenario=scenario)
        result["condor_gross"] = condor_gross
        result["condor_net"] = condor_net

    return result
