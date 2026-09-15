"""
Applies a named, versioned cost scenario to raw structure P&L.

This exists as its own stage specifically because the original research
session's "calibrated" cost numbers were quoted in the final report with no
persisted, traceable file behind them -- a pre-publication audit caught the
gap. Every net-P&L number downstream of this module can now be traced to a
specific YAML file, not inline arithmetic in a throwaway script.
"""
from dataclasses import dataclass
import yaml


@dataclass
class CostScenario:
    name: str
    short_leg_cost: float
    wing_leg_cost: float
    statutory_pct: float

    @classmethod
    def load(cls, path: str) -> "CostScenario":
        with open(path) as f:
            cfg = yaml.safe_load(f)
        name = path.split("/")[-1].replace(".yaml", "")
        return cls(name=name, **cfg)


def net_pnl(gross_pnl: float, credit: float, n_short_legs: int, n_wing_legs: int,
            scenario: CostScenario) -> float:
    """
    credit: gross premium collected on the SHORT legs only (statutory cost
    applies to sold premium, not bought wings -- matches real STT treatment).
    """
    cost = (n_short_legs * scenario.short_leg_cost
            + n_wing_legs * scenario.wing_leg_cost
            + credit * scenario.statutory_pct)
    return gross_pnl - cost
