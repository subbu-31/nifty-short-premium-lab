"""
Engine behaviour over a multi-session synthetic run.

These tests do NOT reproduce any finding in the README ledger. They cannot:
the ledger's numbers come from real NIFTY chains that this repository does
not distribute. What they establish is narrower and still worth having --
that the engine which produced those numbers selects strikes by the delta it
claims to, responds to a volatility risk premium in the right direction,
prices the condor's extra legs consistently, and cannot see past the entry
session.

Read a failure here as "the machinery is wrong", never as "the finding is
wrong" -- and read a pass as nothing at all about NIFTY.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.backtest.engine import (  # noqa: E402
    TARGET_SHORT_DELTA,
    TARGET_WING_DELTA,
    price_structure_at_entry,
    settle,
)
from pipeline.cost.cost_scenarios import CostScenario  # noqa: E402
from tests.fixtures.synthetic_chain import SyntheticMarket  # noqa: E402

CALIBRATED = CostScenario(
    name="calibrated", short_leg_cost=0.971, wing_leg_cost=0.583, statutory_pct=0.0006
)


_RUN_CACHE: dict = {}


def _run(market: SyntheticMarket, scenario: CostScenario = CALIBRATED):
    """Walk every expiry, returning (ticket, settlement) pairs that priced.

    Memoised: solving IV across ~80 strikes x 71 expiries is the whole cost of
    this suite, and several tests want the same run. Keyed on everything that
    changes the result.
    """
    key = (
        market.seed,
        market.realized_vol,
        market.implied_vol,
        market.n_expiries,
        scenario.name,
    )
    if key in _RUN_CACHE:
        return _RUN_CACHE[key]

    out = []
    for entry, expiry in market.sessions():
        ticket = price_structure_at_entry(
            entry, expiry, market.T_years, market.chain, market.spot
        )
        if ticket is None:
            continue
        result = settle(ticket, market.settlement_spot(expiry), scenario)
        out.append((ticket, result))
    _RUN_CACHE[key] = out
    return out


# ---- wiring ------------------------------------------------------------


def test_every_session_prices():
    """A clean synthetic chain should never fail strike selection.

    The engine returns None on chains too thin to solve -- legitimate against
    real early-history data, but here it would mean a wiring break.
    """
    market = SyntheticMarket()
    runs = _run(market)
    assert len(runs) == market.n_expiries


def test_condor_wings_are_found():
    for ticket, result in _run(SyntheticMarket()):
        assert ticket["long_call_k"] is not None
        assert ticket["long_put_k"] is not None
        assert "condor_net" in result


# ---- strike selection --------------------------------------------------


def test_short_strikes_sit_near_the_target_delta():
    """Selected short strikes must actually carry ~0.20 delta.

    One strike step out of place is invisible in the P&L series but changes
    what the whole study is measuring, so it gets asserted rather than
    eyeballed.
    """
    for ticket, _ in _run(SyntheticMarket()):
        chain = ticket["chain"]
        call_delta = chain[(ticket["short_call_k"], "CE")]["delta"]
        put_delta = chain[(ticket["short_put_k"], "PE")]["delta"]
        assert abs(call_delta - TARGET_SHORT_DELTA) < 0.05
        assert abs(abs(put_delta) - TARGET_SHORT_DELTA) < 0.05


def test_wings_are_further_out_than_the_shorts():
    for ticket, _ in _run(SyntheticMarket()):
        assert ticket["long_call_k"] > ticket["short_call_k"]
        assert ticket["long_put_k"] < ticket["short_put_k"]
        chain = ticket["chain"]
        assert abs(chain[(ticket["long_call_k"], "CE")]["delta"]) < TARGET_SHORT_DELTA
        assert abs(chain[(ticket["long_put_k"], "PE")]["delta"]) < TARGET_SHORT_DELTA


def test_recovered_iv_matches_the_vol_the_chain_was_priced_at():
    """Round-trip: price at a known vol, solve it back out of the price."""
    market = SyntheticMarket(implied_vol=0.18)
    ticket, _ = _run(market)[0]
    for (_k, _side), v in ticket["chain"].items():
        assert abs(v["iv"] - 0.18) < 0.01


# ---- the premium the engine exists to measure --------------------------


def test_selling_into_a_premium_pays_and_selling_without_one_does_not():
    """The sign test that matters for a short-premium engine.

    Same seed, same path, same strikes -- only the vol the chain is priced at
    changes. With implied above realized the seller collects more than the
    path takes back; with implied equal to realized the edge is gone. An
    engine that scores both alike is not measuring what it claims to.
    """
    premium = _run(SyntheticMarket(realized_vol=0.12, implied_vol=0.20, seed=11))
    fair = _run(SyntheticMarket(realized_vol=0.12, implied_vol=0.12, seed=11))

    premium_mean = sum(r["strangle_gross"] for _t, r in premium) / len(premium)
    fair_mean = sum(r["strangle_gross"] for _t, r in fair) / len(fair)

    assert premium_mean > 0
    assert premium_mean > fair_mean


# ---- cost treatment ----------------------------------------------------


def test_condor_gives_up_more_of_its_gross_to_cost_than_the_strangle():
    """Structural, not empirical.

    The condor pays for two extra legs and collects the same short credit, so
    it enters with less gross and more cost. That ordering is arithmetic and
    must hold on any data -- it is the mechanism behind the ledger's cost
    finding, not the finding itself, which is an empirical magnitude this
    fixture cannot speak to.
    """
    runs = _run(SyntheticMarket(realized_vol=0.10, implied_vol=0.20, seed=3))

    strangle_gross = sum(r["strangle_gross"] for _t, r in runs)
    strangle_net = sum(r["strangle_net"] for _t, r in runs)
    condor_gross = sum(r["condor_gross"] for _t, r in runs)
    condor_net = sum(r["condor_net"] for _t, r in runs)

    assert strangle_gross > 0 and condor_gross > 0, "need a profitable base to measure drag"

    strangle_drag = (strangle_gross - strangle_net) / strangle_gross
    condor_drag = (condor_gross - condor_net) / condor_gross
    assert condor_drag > strangle_drag


def test_a_heavier_cost_scenario_never_improves_pnl():
    cheap = CostScenario(name="cheap", short_leg_cost=0.5, wing_leg_cost=0.3, statutory_pct=0.0006)
    for (_t, a), (_t2, b) in zip(_run(SyntheticMarket(), CALIBRATED), _run(SyntheticMarket(), cheap)):
        assert a["strangle_net"] <= b["strangle_net"]
        assert a["condor_net"] <= b["condor_net"]


# ---- leak probe --------------------------------------------------------


def test_strike_selection_cannot_see_past_the_entry_session():
    """Two markets identical up to entry, diverging afterwards.

    If the ticket differs, something downstream of entry is reaching back into
    strike selection. Same construction as the clean-vs-leaked placebo in the
    donchian study, applied to this engine.
    """
    a = SyntheticMarket(seed=21)
    b = SyntheticMarket(seed=21)

    entry, expiry = a.sessions()[5]
    # Move settlement only -- entry-session state is untouched.
    b._spot[expiry] = a._spot[expiry] * 1.05

    ta = price_structure_at_entry(entry, expiry, a.T_years, a.chain, a.spot)
    tb = price_structure_at_entry(entry, expiry, b.T_years, b.chain, b.spot)

    assert ta["short_call_k"] == tb["short_call_k"]
    assert ta["short_put_k"] == tb["short_put_k"]
    assert ta["long_call_k"] == tb["long_call_k"]
    assert ta["long_put_k"] == tb["long_put_k"]

    # ...and the settlement change must still move P&L, or the probe proved nothing.
    ra = settle(ta, a.settlement_spot(expiry), CALIBRATED)
    rb = settle(tb, b.settlement_spot(expiry), CALIBRATED)
    assert ra["strangle_net"] != rb["strangle_net"]
