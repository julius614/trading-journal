# 15-Minute ORB Backtester ("Max way" rules)

Python backtester and TradingView strategy for the 15-minute Opening Range Breakout.
Rules, sources, assumptions and the validation plan are in
[`knowledge-base/strategies/orb-15min-max/README.md`](../../knowledge-base/strategies/orb-15min-max/README.md).

| File | What it is |
|---|---|
| `orb.py` | Rules engine: load CSV → 15-minute bars → trades → stats |
| `run_backtest.py` | Command-line runner |
| `make_sample_data.py` | Random-walk sample data (pipeline check only) |
| `orb_max_way.pine` | TradingView Pine v5 strategy with the same rules |
| `tests/test_orb.py` | Unit tests on hand-built days with known outcomes |

## Setup

```bash
pip install pandas pytest
cd strategies/orb_15min
pytest -q tests
```

## Get data

Any intraday OHLCV CSV with a time column (`datetime`, `timestamp`, `time` or `date`)
and `open, high, low, close`. 1- or 5-minute bars are best (they're resampled to
15 minutes); 15-minute bars work too.
- **TradingView:** open a 5-minute chart → *Export chart data* (Unix time is handled).
- **Broker / data vendor:** any CSV; naive timestamps are assumed to be New York time,
  timestamps with an offset or `Z` are converted (`--tz` to change).

## Run

```bash
python run_backtest.py --csv SPY_5min.csv                                 # breakout, midline stop, 2R
python run_backtest.py --csv SPY_5min.csv --mode bnr --slippage 0.01
python run_backtest.py --csv SPY_5min.csv --stop opposite --target eod --out trades.csv
python run_backtest.py --csv SPY_5min.csv --bias --max-or-width 0.8 --long-only
```

Key options: `--mode breakout|bnr`, `--stop mid|opposite`, `--target 1|2|eod`,
`--no-failed-exit`, `--bias`, `--max-or-width`, `--min-or-width`, `--slippage`
(per share, each side), `--commission` (per share, round trip), `--out` (trades CSV).

## Reading the output

All results are in **R** (multiples of the risk per trade): expectancy (average R per
trade), win rate, profit factor, total R, max drawdown in R — overall, by year, by side
and by exit reason. The trades CSV columns match the ORB journal template.

**Try the sample first:** `python make_sample_data.py && python run_backtest.py --csv sample_5min.csv`.
The data is random, so the result should be near zero — it was +0.1R/trade over 204
trades (noise). A real edge needs to beat that clearly, after costs, out of sample.

## Known simplifications
- Uses 15-minute bars: if stop and target fall inside the same bar, the stop is assumed
  to hit first. TradingView's emulator may decide differently, so results can differ a little.
- One trade per day; no re-entry after a stop.
- No relative-volume filter or news calendar yet.
- The TradingView script hasn't been compiled here (no access) — add it on TradingView
  and fix anything the editor flags.
