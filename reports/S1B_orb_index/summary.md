# Strategy 1B - Opening Range Breakout (QQQ/SPY stand-ins)

Markets: US500, USTECH100M (M5, 2019-01-01 -> 2026-10-02). In-sample before 2024-06-05, out-of-sample after.


## Verdict: **FAIL**

Out-of-sample expectancy at costs x1 = -0.0632 R over 1098 trades; out-of-sample net -34,721 USD vs random-entry 95th percentile -1,290 USD (strategy beats 47% of 100 random runs).


Chosen on in-sample data only: `{'or_min': 30}`


## Chosen combination: costs x0 / x1 / x2, in-sample vs out-of-sample

| metric | IS x0 | OOS x0 | IS x1 | OOS x1 | IS x2 | OOS x2 |
|---|---|---|---|---|---|---|
| trades | 2,472 | 1,098 | 2,472 | 1,098 | 2,472 | 1,098 |
| win_rate | 0.27 | 0.34 | 0.262 | 0.337 | 0.254 | 0.332 |
| avg_win | 1,302.88 | 835.67 | 1,282.11 | 815.70 | 1,257.88 | 800.05 |
| avg_loss | -425.15 | -425.58 | -502.37 | -462.27 | -579.18 | -497.43 |
| expectancy_R | 0.0822 | 0.0058 | -0.0706 | -0.0632 | -0.2235 | -0.1322 |
| profit_factor | 1.132 | 1.01 | 0.905 | 0.897 | 0.741 | 0.801 |
| net | 101,619.12 | 3,157.66 | -87,302.36 | -34,720.85 | -276,223.85 | -72,599.37 |
| net_pct | 101.62 | 3.16 | -87.3 | -34.72 | -276.22 | -72.6 |
| cagr | 13.8 | 1.35 | -31.65 | -16.78 | nan | -42.74 |
| sharpe | 0.683 | 0.063 | -0.585 | -0.687 | -1.837 | -1.431 |
| max_dd_pct | -20.25 | -18.86 | -128.09 | -40.14 | -268.17 | -73.92 |
| longest_losing_streak | 27 | 27 | 27 | 27 | 27 | 27 |
| top5_share | 0.246 | 7.805 | nan | nan | nan | nan |


## Out-of-sample by market (costs x1) and buy-and-hold of the same market

| symbol | oos_trades | oos_exp_R | oos_net_pct | buy_and_hold_oos_pct |
|---|---|---|---|---|
| US500 | 557 | -0.0752 | -20.95 | 45.32 |
| USTECH100M | 541 | -0.0509 | -13.77 | 64.02 |


## Random-entry baseline (out-of-sample, costs x1, 100 runs)

Same entry times, holding times and sizes, random direction. Percentiles: 5th -78,859, median -33,736, 95th -1,290 USD. Strategy: -34,721 USD.


## Walk-forward (2-year train, 6-month test, costs x1)

| test_start | test_end | chosen | trades | exp_R | net |
|---|---|---|---|---|---|
| 2021-01-01 | 2021-07-01 | {'or_min': 30} | 250 | 0.0317 | 3,960.07 |
| 2021-07-01 | 2022-01-01 | {'or_min': 30} | 252 | -0.2397 | -30,202.38 |
| 2022-01-01 | 2022-07-01 | {'or_min': 30} | 250 | 0.1113 | 13,907.37 |
| 2022-07-01 | 2023-01-01 | {'or_min': 30} | 247 | 0.2713 | 33,501.29 |
| 2023-01-01 | 2023-07-01 | {'or_min': 30} | 66 | -0.2092 | -6,902.54 |
| 2023-07-01 | 2024-01-01 | {'or_min': 30} | 208 | 0.1427 | 14,839.47 |
| 2024-01-01 | 2024-07-01 | {'or_min': 30} | 247 | -0.2568 | -31,709.73 |
| 2024-07-01 | 2025-01-01 | {'or_min': 30} | 242 | 0.007 | 842.63 |
| 2025-01-01 | 2025-07-01 | {'or_min': 30} | 237 | -0.0482 | -5,707.04 |
| 2025-07-01 | 2026-01-01 | {'or_min': 30} | 238 | -0.0537 | -6,388.24 |
| 2026-01-01 | 2026-07-01 | {'or_min': 30} | 222 | -0.0379 | -4,209.27 |
| 2026-07-01 | 2026-10-02 | {'or_min': 30} | 125 | -0.2357 | -14,728.70 |


Walk-forward total: -32,797 USD over 2584 trades; 5 of 12 test windows positive.


## Extra check: short-history markets (~1.5 years, chosen parameters, costs x1, low confidence)

| market | from | trades | exp_R | pf | net_pct |
|---|---|---|---|---|---|
| US30 | 2025-03-05 | 343 | -0.0495 | 0.91 | -8.48 |


## All combinations

Choice uses the in-sample columns only; out-of-sample columns are shown so nothing is hidden, not for picking.

| or_min | is_trades | is_exp_R | is_pf | is_net | oos_trades | oos_exp_R | oos_net |
|---|---|---|---|---|---|---|---|
| 5 | 2,466 | -0.1844 | 0.767 | -227,422.59 | 1,096 | -0.0818 | -44,817.47 |
| 15 | 2,467 | -0.1018 | 0.87 | -125,611.15 | 1,099 | -0.0451 | -24,803.48 |
| 30 | 2,472 | -0.0706 | 0.905 | -87,302.36 | 1,098 | -0.0632 | -34,720.85 |


## Notes

- Data: M5 bars only (no 1-minute bars, no bid/ask quotes). Fills use M5 bar opens and highs/lows; stop-before-target is assumed whenever one bar covers both.
- Long history 2019-2026: HistData M5 until 2025, then the MetaQuotes-Demo broker feed (data/intraday_hd). Short history (~1.5 years, 2025-2026, broker only): USDJPY, AUDUSD, US30 - reported separately as an extra check, low confidence.
- US500 / USTECH100M are broker index CFDs used as stand-ins for SPY / QQQ, not the ETFs. Their costs are the broker's own bar spread (median where unknown) plus half a spread of slippage per market/stop fill; no commission; 4x leverage cap. That is roughly 3-4 basis points per round trip - about 4-5x the spec's ETF costs (~0.8 bp on SPY), so for the ETFs themselves the truth would sit between the x0 and x1 columns.
- FX costs are the spec defaults (0.8 pip EURUSD / 1.2 pip others spread, 0.2 pip slippage on market/stop fills, 3.5 USD per 100k per side) - not real bid/ask around the fixes.
- These markets/years overlap earlier tests in this repo, so this is not a fully fresh sample; the out-of-sample part (last 30% of dates) was touched once, here.
- 1R = 0.5% of the 100,000 starting equity (500) for every setup, including the ones without a stop (1x notional), so R is comparable. No compounding.


Files: `trades.csv`, `monthly_returns.csv`, `all_combinations.csv`, `equity_curve.png`, `drawdown.png`.
