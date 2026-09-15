# Data

## What's here

`derived/` contains the output of every analysis in this project — daily
realized-vol estimators, the backtest P&L series, the term-structure and
Granger-causality tables, and so on. These are aggregated/transformed
statistics, safe to publish and directly reproducible from the pipeline
code given the raw inputs below.

## What's NOT here, and why

- **Raw NSE weekly-options chain data** (per-strike 1-minute OHLCV+OI, the
  source for every backtest in this repo). Provenance/redistribution rights
  for this data are unclear, so it's excluded rather than assumed fine to
  publish.
- **The full 1-minute NIFTY spot reconstruction** (~17MB) — derived from
  the same source, same reasoning.

`pipeline/backtest/engine.py` is written against a small `OptionChainSource`
/ `SpotCloseSource` interface (see the module docstring) specifically so
that plugging in your own data source — a paid vendor feed, a broker API,
your own scrape — is a ~20-line adapter, not a rewrite.

## External market data

India VIX, NIFTY futures (continuous), GIFT Nifty, MCX Crude Oil, and
USDINR series in `derived/` were pulled via the Kite Connect API and *are*
included — daily OHLC index/futures data, not a licensed options feed.
