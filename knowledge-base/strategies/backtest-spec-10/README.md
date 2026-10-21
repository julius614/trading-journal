# BACKTEST_SPEC.md - 10 day-trading setups (run once, 2026-10-21)

**Source & capture:** `BACKTEST_SPEC.md` by Denis (uploaded by the user), read in full. The
rules, grids and PASS test below come from that file; interpretations of loose wording are
marked in `bots/spec10/strategies.py`.

## What was run
- Code: `bots/spec10/` (`engine.py` shared rules, `strategies.py`, `run.py`, tests).
  Run with `python -m bots.spec10.run`.
- Output: `reports/<setup>/` holds `summary.md`, `trades.csv`, `monthly_returns.csv`,
  `all_combinations.csv` and the charts. `reports/COMPARISON.md` has the overview.
- Data: M5 bars, 2019-01 to 2026-10. Sources: HistData plus the MetaQuotes-Demo broker feed.
  - Indices: US500 and USTECH100M CFDs, standing in for SPY and QQQ.
  - FX: EURUSD and GBPUSD.
  - Short history (2025-26) as an extra check: USDJPY, AUDUSD, US30.
- Method: the parameters were chosen on the first 70% of dates (costs ×1). The last 30% was
  touched once. The run also includes a 100-run random-entry baseline and a 2-year/6-month
  walk-forward.
- PASS means two things: out-of-sample expectancy above 0 at costs ×1, AND beating the 95th
  percentile of the random-entry runs.

## Result: 0 of 10 passed; 2 setups not testable

| Setup | OOS trades | OOS exp. R ×0 (no costs) | OOS exp. R ×1 | Verdict |
|---|---|---|---|---|
| S1B ORB (index CFDs) | 1098 | +0.006 | -0.063 | FAIL |
| S2 intraday momentum | 500 | -0.041 | -0.077 | FAIL |
| S3 momentum on FOMC days | 36 | +0.176 | +0.140 | FAIL (too few trades, did not beat random p95) |
| S4 VWAP trend | 2494 | +0.010 | -0.027 | FAIL |
| S5 London 4pm fix | 37 | +0.032 | -0.005 | FAIL |
| S6 Tokyo/ECB fix | 1195 | +0.019 | -0.018 | FAIL |
| S7 round-number fade | 362 | +0.002 | -0.068 | FAIL |
| S8 round-number break | 143 | -0.032 | -0.117 | FAIL |
| S9 sweep reversal M15 | 1939 | +0.061 | -0.240 | FAIL |
| S9 sweep reversal H1 | 457 | +0.120 | -0.134 | FAIL |
| S1 stocks in play, S10 market making | - | - | - | NOT TESTABLE (no stock-universe or order-book data) |

## What we learned
- **Costs are the problem, as before.** Most setups have a tiny edge before costs
  (S1B, S4, S6, S9), and costs turn every one of them negative.
- **S9 (liquidity sweep) on H1 has the largest gross edge: +0.12 R per trade.** Its tight
  stops make costs about 0.25 R per trade. The spec's claim that "it only works at 2R–3R"
  did not hold: all targets lost money after costs.
- **S3 on FOMC days was positive out-of-sample** (+0.14 R), but on only 36 trades, and the
  walk-forward lost money. Under the spec's own rule (fewer than 50 trades → don't trust it),
  this is noise until more data exists.
- **Round numbers:** in the model-free check, a round level was broken slightly more often
  than it reversed after the first touch (EURUSD 335 vs 292, GBPUSD 662 vs 610). Both the
  fade (S7) and the break (S8) lost money after costs.
- **Index CFD costs are about 4–5× the spec's ETF costs.** For real SPY/QQQ the truth would
  sit between the ×0 and ×1 columns. Even so, S1B and S4 were barely positive gross
  out-of-sample.

## Caveats
- M5 bars only, with no 1-minute data and no bid/ask. The FX spreads are the spec's fixed
  defaults.
- These markets and years overlap earlier tests in this repo.
- `data/events.csv` dates were written from memory, with spot-checks against web search for
  2025–26; the official pages could not be fetched.

## Self-check questions
1. Why does a "beats random" result not count for a setup that loses money?
2. Why does a tight-stop setup like S9 need a much larger gross edge than a wide-stop one?

## Applying it to my journal
Before taking any of these setups by hand, log the spread you actually paid and compare
the average cost per trade with the R you are risking.
