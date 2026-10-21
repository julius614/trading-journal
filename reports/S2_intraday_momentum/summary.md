# Strategy 2 - first half-hour predicts last half-hour

Markets: US500, USTECH100M (M5, 2019-01-01 -> 2026-10-02). In-sample before 2024-06-05, out-of-sample after.


## Verdict: **FAIL**

Out-of-sample expectancy at costs x1 = -0.0771 R over 500 trades; out-of-sample net -19,271 USD vs random-entry 95th percentile -644 USD (strategy beats 1% of 100 random runs).


Chosen on in-sample data only: `{'variant': '2B', 'skip_small': True}`


## Chosen combination: costs x0 / x1 / x2, in-sample vs out-of-sample

| metric | IS x0 | OOS x0 | IS x1 | OOS x1 | IS x2 | OOS x2 |
|---|---|---|---|---|---|---|
| trades | 1,030 | 500 | 1,030 | 500 | 1,030 | 500 |
| win_rate | 0.534 | 0.448 | 0.443 | 0.404 | 0.381 | 0.358 |
| avg_win | 215.76 | 139.02 | 221.40 | 135.18 | 221.18 | 133.54 |
| avg_loss | -194.77 | -150.31 | -195.55 | -156.30 | -210.75 | -162.31 |
| expectancy_R | 0.0489 | -0.0414 | -0.0219 | -0.0771 | -0.0927 | -0.1128 |
| profit_factor | 1.269 | 0.751 | 0.899 | 0.586 | 0.645 | 0.459 |
| net | 25,176.38 | -10,345.38 | -11,289.88 | -19,271.03 | -47,756.14 | -28,196.68 |
| net_pct | 25.18 | -10.35 | -11.29 | -19.27 | -47.76 | -28.2 |
| cagr | 4.23 | -4.59 | -2.19 | -8.8 | -11.3 | -13.28 |
| sharpe | 0.71 | -1.105 | -0.319 | -2.041 | -1.344 | -2.952 |
| max_dd_pct | -6.34 | -12.44 | -17.24 | -20.43 | -47.98 | -28.78 |
| longest_losing_streak | 8 | 9 | 11 | 13 | 21 | 14 |
| top5_share | 0.443 | nan | nan | nan | nan | nan |


## Out-of-sample by market (costs x1) and buy-and-hold of the same market

| symbol | oos_trades | oos_exp_R | oos_net_pct | buy_and_hold_oos_pct |
|---|---|---|---|---|
| US500 | 260 | -0.06 | -7.8 | 45.32 |
| USTECH100M | 240 | -0.0956 | -11.47 | 64.02 |


## Random-entry baseline (out-of-sample, costs x1, 100 runs)

Same entry times, holding times and sizes, random direction. Percentiles: 5th -16,481, median -9,033, 95th -644 USD. Strategy: -19,271 USD.


## Walk-forward (2-year train, 6-month test, costs x1)

| test_start | test_end | chosen | trades | exp_R | net |
|---|---|---|---|---|---|
| 2021-01-01 | 2021-07-01 | {'variant': '2B', 'skip_small': True} | 98 | 0.0362 | 1,774.49 |
| 2021-07-01 | 2022-01-01 | {'variant': '2B', 'skip_small': True} | 80 | -0.0033 | -130.77 |
| 2022-01-01 | 2022-07-01 | {'variant': '2B', 'skip_small': True} | 111 | 0.0412 | 2,287.77 |
| 2022-07-01 | 2023-01-01 | {'variant': '2B', 'skip_small': True} | 113 | 0.061 | 3,446.52 |
| 2023-01-01 | 2023-07-01 | {'variant': '2B', 'skip_small': True} | 30 | 0.1086 | 1,629.07 |
| 2023-07-01 | 2024-01-01 | {'variant': '2B', 'skip_small': True} | 76 | -0.0246 | -935.56 |
| 2024-01-01 | 2024-07-01 | {'variant': '2B', 'skip_small': True} | 99 | -0.156 | -7,722.78 |
| 2024-07-01 | 2025-01-01 | {'variant': '2B', 'skip_small': False} | 140 | -0.0064 | -450.93 |
| 2025-01-01 | 2025-07-01 | {'variant': '2B', 'skip_small': False} | 123 | -0.1413 | -8,689.94 |
| 2025-07-01 | 2026-01-01 | {'variant': 'base', 'skip_small': False} | 234 | -0.0637 | -7,448.54 |
| 2026-01-01 | 2026-07-01 | {'variant': 'base', 'skip_small': False} | 218 | -0.0086 | -941.09 |
| 2026-07-01 | 2026-10-02 | {'variant': 'base', 'skip_small': False} | 125 | -0.026 | -1,624.04 |


Walk-forward total: -18,806 USD over 1447 trades; 4 of 12 test windows positive.


## Extra check: short-history markets (~1.5 years, chosen parameters, costs x1, low confidence)

| market | from | trades | exp_R | pf | net_pct |
|---|---|---|---|---|---|
| US30 | 2025-03-07 | 152 | -0.0692 | 0.559 | -5.26 |


## All combinations

Choice uses the in-sample columns only; out-of-sample columns are shown so nothing is hidden, not for picking.

| variant | skip_small | is_trades | is_exp_R | is_pf | is_net | oos_trades | oos_exp_R | oos_net |
|---|---|---|---|---|---|---|---|---|
| base | False | 2455 | -0.0565 | 0.754 | -69,340.40 | 1086 | -0.0365 | -19,838.70 |
| base | True | 1964 | -0.0579 | 0.762 | -56,891.65 | 887 | -0.0437 | -19,397.31 |
| 2B | False | 1283 | -0.0265 | 0.874 | -17,005.52 | 598 | -0.0558 | -16,675.79 |
| 2B | True | 1030 | -0.0219 | 0.899 | -11,289.88 | 500 | -0.0771 | -19,271.03 |


## Notes

- Data: M5 bars only (no 1-minute bars, no bid/ask quotes). Fills use M5 bar opens and highs/lows; stop-before-target is assumed whenever one bar covers both.
- Long history 2019-2026: HistData M5 until 2025, then the MetaQuotes-Demo broker feed (data/intraday_hd). Short history (~1.5 years, 2025-2026, broker only): USDJPY, AUDUSD, US30 - reported separately as an extra check, low confidence.
- US500 / USTECH100M are broker index CFDs used as stand-ins for SPY / QQQ, not the ETFs. Their costs are the broker's own bar spread (median where unknown) plus half a spread of slippage per market/stop fill; no commission; 4x leverage cap. That is roughly 3-4 basis points per round trip - about 4-5x the spec's ETF costs (~0.8 bp on SPY), so for the ETFs themselves the truth would sit between the x0 and x1 columns.
- FX costs are the spec defaults (0.8 pip EURUSD / 1.2 pip others spread, 0.2 pip slippage on market/stop fills, 3.5 USD per 100k per side) - not real bid/ask around the fixes.
- These markets/years overlap earlier tests in this repo, so this is not a fully fresh sample; the out-of-sample part (last 30% of dates) was touched once, here.
- 1R = 0.5% of the 100,000 starting equity (500) for every setup, including the ones without a stop (1x notional), so R is comparable. No compounding.


Files: `trades.csv`, `monthly_returns.csv`, `all_combinations.csv`, `equity_curve.png`, `drawdown.png`.
