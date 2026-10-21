# Strategy 8 - stop-run continuation through round numbers

Markets: EURUSD, GBPUSD (M5, 2019-01-01 -> 2026-10-02). In-sample before 2024-06-05, out-of-sample after.


## Verdict: **FAIL**

Out-of-sample expectancy at costs x1 = -0.1173 R over 143 trades; out-of-sample net -8,388 USD vs random-entry 95th percentile -225 USD (strategy beats 36% of 100 random runs).


Chosen on in-sample data only: `{'break_pips': 10, 'stop_pips': 10, 'target_R': 1}`


## Chosen combination: costs x0 / x1 / x2, in-sample vs out-of-sample

| metric | IS x0 | OOS x0 | IS x1 | OOS x1 | IS x2 | OOS x2 |
|---|---|---|---|---|---|---|
| trades | 583 | 143 | 583 | 143 | 583 | 143 |
| win_rate | 0.489 | 0.49 | 0.479 | 0.455 | 0.465 | 0.434 |
| avg_win | 437.34 | 362.21 | 404.41 | 347.59 | 373.84 | 322.86 |
| avg_loss | -435.67 | -378.14 | -474.23 | -397.20 | -508.95 | -426.46 |
| expectancy_R | -0.0178 | -0.0315 | -0.1075 | -0.1173 | -0.1972 | -0.2032 |
| profit_factor | 0.96 | 0.918 | 0.783 | 0.729 | 0.638 | 0.579 |
| net | -5,188.20 | -2,249.96 | -31,335.12 | -8,387.78 | -57,482.05 | -14,525.60 |
| net_pct | -5.19 | -2.25 | -31.34 | -8.39 | -57.48 | -14.53 |
| cagr | -0.99 | -0.98 | -6.81 | -3.71 | -14.82 | -6.55 |
| sharpe | -0.189 | -0.313 | -1.125 | -1.151 | -2.009 | -1.93 |
| max_dd_pct | -10.74 | -6.4 | -34.25 | -10.05 | -59.44 | -15.5 |
| longest_losing_streak | 7 | 11 | 7 | 11 | 7 | 11 |
| top5_share | nan | nan | nan | nan | nan | nan |


## Out-of-sample by market (costs x1) and buy-and-hold of the same market

| symbol | oos_trades | oos_exp_R | oos_net_pct | buy_and_hold_oos_pct |
|---|---|---|---|---|
| EURUSD | 68 | -0.1286 | -4.37 | 3.37 |
| GBPUSD | 75 | -0.1071 | -4.02 | 3.51 |


Buy-and-hold is not a meaningful benchmark for FX pairs (shown for completeness).


## Random-entry baseline (out-of-sample, costs x1, 100 runs)

Same entry times, holding times and sizes, random direction. Percentiles: 5th -15,545, median -6,281, 95th -225 USD. Strategy: -8,388 USD.


## Walk-forward (2-year train, 6-month test, costs x1)

| test_start | test_end | chosen | trades | exp_R | net |
|---|---|---|---|---|---|
| 2021-01-01 | 2021-07-01 | {'break_pips': 10, 'stop_pips': 5, 'target_R': 1} | 26 | 0.0981 | 1,274.79 |
| 2021-07-01 | 2022-01-01 | {'break_pips': 10, 'stop_pips': 5, 'target_R': 1} | 20 | 0.0415 | 415 |
| 2022-01-01 | 2022-07-01 | {'break_pips': 10, 'stop_pips': 5, 'target_R': 1} | 56 | -0.361 | -10,108.67 |
| 2022-07-01 | 2023-01-01 | {'break_pips': 10, 'stop_pips': 10, 'target_R': 1} | 132 | -0.1099 | -7,251.16 |
| 2023-01-01 | 2023-07-01 | {'break_pips': 10, 'stop_pips': 10, 'target_R': 1} | 61 | -0.0539 | -1,643.48 |
| 2023-07-01 | 2024-01-01 | {'break_pips': 10, 'stop_pips': 10, 'target_R': 1} | 32 | -0.1695 | -2,712.10 |
| 2024-01-01 | 2024-07-01 | {'break_pips': 10, 'stop_pips': 10, 'target_R': 1} | 21 | 0.1681 | 1,765.17 |
| 2024-07-01 | 2025-01-01 | {'break_pips': 10, 'stop_pips': 10, 'target_R': 1} | 25 | -0.1219 | -1,524.18 |
| 2025-01-01 | 2025-07-01 | {'break_pips': 10, 'stop_pips': 5, 'target_R': 2} | 68 | -0.1901 | -6,464.29 |
| 2025-07-01 | 2026-01-01 | {'break_pips': 10, 'stop_pips': 5, 'target_R': 3} | 17 | 0.0217 | 184.79 |
| 2026-01-01 | 2026-07-01 | {'break_pips': 10, 'stop_pips': 10, 'target_R': 3} | 21 | -0.3464 | -3,637.14 |
| 2026-07-01 | 2026-10-02 | {'break_pips': 10, 'stop_pips': 10, 'target_R': 3} | 7 | 0.1947 | 681.37 |


Walk-forward total: -29,020 USD over 486 trades; 5 of 12 test windows positive.


## Extra check: short-history markets (~1.5 years, chosen parameters, costs x1, low confidence)

| market | from | trades | exp_R | pf | net_pct |
|---|---|---|---|---|---|
| AUDUSD | 2025-06-18 | 13 | -0.3592 | 0.304 | -2.34 |
| USDJPY | 2025-05-30 | 94 | -0.1688 | 0.682 | -7.94 |


## All combinations

Choice uses the in-sample columns only; out-of-sample columns are shown so nothing is hidden, not for picking.

| break_pips | stop_pips | target_R | is_trades | is_exp_R | is_pf | is_net | oos_trades | oos_exp_R | oos_net |
|---|---|---|---|---|---|---|---|---|---|
| 2 | 5 | 1 | 2,272 | -0.2566 | 0.589 | -291,449.48 | 832 | -0.3144 | -130,773.69 |
| 2 | 5 | 2 | 2,149 | -0.2682 | 0.656 | -288,143.82 | 794 | -0.3759 | -149,249.55 |
| 2 | 5 | 3 | 2,117 | -0.2587 | 0.685 | -273,862.12 | 785 | -0.3671 | -144,106.23 |
| 2 | 10 | 1 | 2,114 | -0.1733 | 0.682 | -183,176.68 | 778 | -0.197 | -76,638.28 |
| 2 | 10 | 2 | 2,022 | -0.1813 | 0.715 | -183,288.78 | 757 | -0.2067 | -78,239.09 |
| 2 | 10 | 3 | 2,007 | -0.1893 | 0.709 | -189,925.52 | 754 | -0.2123 | -80,049.72 |
| 5 | 5 | 1 | 1,509 | -0.1879 | 0.674 | -141,797.05 | 479 | -0.2174 | -52,071.62 |
| 5 | 5 | 2 | 1,473 | -0.1727 | 0.752 | -127,200.91 | 470 | -0.25 | -58,756.01 |
| 5 | 5 | 3 | 1,462 | -0.1613 | 0.778 | -117,936.32 | 466 | -0.2782 | -64,826.31 |
| 5 | 10 | 1 | 1,446 | -0.1278 | 0.75 | -92,392.70 | 460 | -0.1604 | -36,889.45 |
| 5 | 10 | 2 | 1,408 | -0.1366 | 0.768 | -96,197.40 | 451 | -0.1977 | -44,584.99 |
| 5 | 10 | 3 | 1,399 | -0.1437 | 0.763 | -100,507.71 | 451 | -0.2011 | -45,352.61 |
| 10 | 5 | 1 | 596 | -0.1099 | 0.789 | -32,743.46 | 144 | -0.1685 | -12,130.47 |
| 10 | 5 | 2 | 588 | -0.1448 | 0.769 | -42,566.35 | 143 | -0.1704 | -12,186.98 |
| 10 | 5 | 3 | 586 | -0.1181 | 0.818 | -34,599.42 | 143 | -0.1483 | -10,601.56 |
| 10 | 10 | 1 | 583 | -0.1075 | 0.783 | -31,335.12 | 143 | -0.1173 | -8,387.78 |
| 10 | 10 | 2 | 575 | -0.1414 | 0.752 | -40,638.92 | 142 | -0.1346 | -9,554.74 |
| 10 | 10 | 3 | 574 | -0.1279 | 0.779 | -36,694.94 | 142 | -0.1117 | -7,932.37 |


## Notes

- Data: M5 bars only (no 1-minute bars, no bid/ask quotes). Fills use M5 bar opens and highs/lows; stop-before-target is assumed whenever one bar covers both.
- Long history 2019-2026: HistData M5 until 2025, then the MetaQuotes-Demo broker feed (data/intraday_hd). Short history (~1.5 years, 2025-2026, broker only): USDJPY, AUDUSD, US30 - reported separately as an extra check, low confidence.
- US500 / USTECH100M are broker index CFDs used as stand-ins for SPY / QQQ, not the ETFs. Their costs are the broker's own bar spread (median where unknown) plus half a spread of slippage per market/stop fill; no commission; 4x leverage cap. That is roughly 3-4 basis points per round trip - about 4-5x the spec's ETF costs (~0.8 bp on SPY), so for the ETFs themselves the truth would sit between the x0 and x1 columns.
- FX costs are the spec defaults (0.8 pip EURUSD / 1.2 pip others spread, 0.2 pip slippage on market/stop fills, 3.5 USD per 100k per side) - not real bid/ask around the fixes.
- These markets/years overlap earlier tests in this repo, so this is not a fully fresh sample; the out-of-sample part (last 30% of dates) was touched once, here.
- 1R = 0.5% of the 100,000 starting equity (500) for every setup, including the ones without a stop (1x notional), so R is comparable. No compounding.


Files: `trades.csv`, `monthly_returns.csv`, `all_combinations.csv`, `equity_curve.png`, `drawdown.png`.

## S7 vs S8 on identical dates

Dates where both chosen versions traded the same pair: 318. Fade (S7) total -108.0 R, mean -0.340 R/day; break (S8) total -48.0 R, mean -0.151 R/day (costs x1).


Model-free check - first touch of a round level each day (07:00-17:00 London): did price go 20 pips THROUGH (break) or 20 pips BACK (reverse) first, within 2 hours?

| symbol | break | reverse | undecided |
|---|---|---|---|
| EURUSD | 335 | 292 | 552 |
| GBPUSD | 662 | 610 | 390 |
