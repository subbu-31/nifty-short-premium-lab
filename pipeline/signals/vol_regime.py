"""
The two regime gates used by the core backtest, both thin applications of
walkforward_tercile over a different underlying series:

- realized_vol_gate: trailing 20-day close-to-close realized vol (the gate
  used for the original straddle/strangle/condor tercile split)
- vix_percentile_gate: trailing India VIX percentile rank (the session's
  final, most robust finding -- see README's "open lead")

Kept as two named functions rather than one generic one because they read
different input series and the distinction (realized vs. implied vol) is
the whole point of the comparison in the report.
"""
from pipeline.signals.walkforward import walkforward_tercile


def realized_vol_gate(dates, realized_vols, min_history=60):
    return walkforward_tercile(dates, realized_vols, min_history=min_history)


def vix_percentile_gate(dates, vix_closes, min_history=60):
    return walkforward_tercile(dates, vix_closes, min_history=min_history)
