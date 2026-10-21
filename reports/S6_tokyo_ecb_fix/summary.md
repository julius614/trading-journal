# Strategy 6 - Tokyo & ECB fix reversals

Markets: EURUSD, GBPUSD (M5, 2019-01-01 -> 2026-10-02). In-sample before 2024-06-05, out-of-sample after.


## Verdict: **FAIL**

Out-of-sample expectancy at costs x1 = -0.0176 R over 1195 trades; out-of-sample net -10,501 USD vs random-entry 95th percentile -15,272 USD (strategy beats 100% of 100 random runs).


Chosen on in-sample data only: `{'window': 1, 'fix': 'ECB'}`


## Chosen combination: costs x0 / x1 / x2, in-sample vs out-of-sample

| metric | IS x0 | OOS x0 | IS x1 | OOS x1 | IS x2 | OOS x2 |
|---|---|---|---|---|---|---|
| trades | 2,570 | 1,195 | 2,570 | 1,195 | 2,570 | 1,195 |
| win_rate | 0.517 | 0.529 | 0.445 | 0.442 | 0.374 | 0.359 |
| avg_win | 100.31 | 89.96 | 96.38 | 87.31 | 94.35 | 87.08 |
| avg_loss | -106.37 | -80.6 | -110.13 | -84.86 | -115.20 | -91.17 |
| expectancy_R | 0.0009 | 0.0192 | -0.0364 | -0.0176 | -0.0737 | -0.0544 |
| profit_factor | 1.008 | 1.253 | 0.702 | 0.814 | 0.489 | 0.535 |
| net | 1,104.44 | 11,477.71 | -46,795.49 | -10,500.56 | -94,695.42 | -32,478.84 |
| net_pct | 1.1 | 11.48 | -46.8 | -10.5 | -94.7 | -32.48 |
| cagr | 0.2 | 4.79 | -10.98 | -4.67 | -41.81 | -15.56 |
| sharpe | 0.051 | 1.342 | -2.141 | -1.228 | -4.319 | -3.797 |
| max_dd_pct | -10.85 | -2.14 | -47.44 | -11.74 | -94.91 | -33.23 |
| longest_losing_streak | 10 | 9 | 10 | 15 | 22 | 15 |
| top5_share | 3.783 | 0.396 | nan | nan | nan | nan |


## Out-of-sample by market (costs x1) and buy-and-hold of the same market

| symbol | oos_trades | oos_exp_R | oos_net_pct | buy_and_hold_oos_pct |
|---|---|---|---|---|
| EURUSD | 598 | -0.01 | -2.99 | 3.37 |
| GBPUSD | 597 | -0.0252 | -7.51 | 3.51 |


Buy-and-hold is not a meaningful benchmark for FX pairs (shown for completeness).


Tokyo trades end by 13:00 Tokyo time and ECB trades start at 14:20 Berlin time, so 'both' never holds two positions in the same pair at once.


## Random-entry baseline (out-of-sample, costs x1, 100 runs)

Same entry times, holding times and sizes, random direction. Percentiles: 5th -30,284, median -22,326, 95th -15,272 USD. Strategy: -10,501 USD.


## Walk-forward (2-year train, 6-month test, costs x1)

| test_start | test_end | chosen | trades | exp_R | net |
|---|---|---|---|---|---|
| 2021-01-01 | 2021-07-01 | {'window': 1, 'fix': 'ECB'} | 254 | -0.0412 | -5,230.80 |
| 2021-07-01 | 2022-01-01 | {'window': 3, 'fix': 'ECB'} | 262 | -0.0766 | -10,029.04 |
| 2022-01-01 | 2022-07-01 | {'window': 1, 'fix': 'ECB'} | 259 | -0.0461 | -5,973.12 |
| 2022-07-01 | 2023-01-01 | {'window': 1, 'fix': 'ECB'} | 258 | -0.0891 | -11,490.13 |
| 2023-01-01 | 2023-07-01 | {'window': 2, 'fix': 'ECB'} | 124 | -0.1043 | -6,469.61 |
| 2023-07-01 | 2024-01-01 | {'window': 2, 'fix': 'ECB'} | 230 | -0.0675 | -7,757.49 |
| 2024-01-01 | 2024-07-01 | {'window': 2, 'fix': 'ECB'} | 258 | -0.0263 | -3,396.76 |
| 2024-07-01 | 2025-01-01 | {'window': 2, 'fix': 'ECB'} | 259 | -0.0363 | -4,703.40 |
| 2025-01-01 | 2025-07-01 | {'window': 1, 'fix': 'ECB'} | 256 | -0.0057 | -733.71 |
| 2025-07-01 | 2026-01-01 | {'window': 3, 'fix': 'ECB'} | 259 | -0.0592 | -7,670.02 |
| 2026-01-01 | 2026-07-01 | {'window': 1, 'fix': 'ECB'} | 258 | -0.0184 | -2,369.16 |
| 2026-07-01 | 2026-10-02 | {'window': 3, 'fix': 'ECB'} | 134 | -0.0098 | -655.01 |


Walk-forward total: -66,478 USD over 2811 trades; 0 of 12 test windows positive.


## Extra check: short-history markets (~1.5 years, chosen parameters, costs x1, low confidence)

| market | from | trades | exp_R | pf | net_pct |
|---|---|---|---|---|---|
| AUDUSD | 2025-06-02 | 345 | -0.0433 | 0.664 | -7.47 |
| USDJPY | 2025-06-02 | 344 | -0.0363 | 0.68 | -6.24 |
| 4-pair USD basket | 2025-06-02 | 1392 | -0.008 | 0.705 | -5.57 |


## All combinations

Choice uses the in-sample columns only; out-of-sample columns are shown so nothing is hidden, not for picking.

| window | fix | is_trades | is_exp_R | is_pf | is_net | oos_trades | oos_exp_R | oos_net |
|---|---|---|---|---|---|---|---|---|
| 1 | Tokyo | 2574 | -0.0396 | 0.496 | -50,942.13 | 1191 | -0.0363 | -21,611.40 |
| 1 | ECB | 2570 | -0.0364 | 0.702 | -46,795.49 | 1195 | -0.0176 | -10,500.56 |
| 1 | both | 5144 | -0.038 | 0.621 | -97,737.62 | 2386 | -0.0269 | -32,111.97 |
| 2 | Tokyo | 2639 | -0.0457 | 0.542 | -60,335.71 | 1198 | -0.035 | -20,961.30 |
| 2 | ECB | 2641 | -0.0375 | 0.79 | -49,567.97 | 1203 | -0.028 | -16,830.80 |
| 2 | both | 5280 | -0.0416 | 0.701 | -109,903.69 | 2401 | -0.0315 | -37,792.10 |
| 3 | Tokyo | 2133 | -0.0474 | 0.559 | -50,603.47 | 1060 | -0.0356 | -18,872.19 |
| 3 | ECB | 2608 | -0.0457 | 0.797 | -59,632.64 | 1199 | -0.0191 | -11,472.53 |
| 3 | both | 4741 | -0.0465 | 0.73 | -110,236.11 | 2259 | -0.0269 | -30,344.73 |


## Notes

- Data: M5 bars only (no 1-minute bars, no bid/ask quotes). Fills use M5 bar opens and highs/lows; stop-before-target is assumed whenever one bar covers both.
- Long history 2019-2026: HistData M5 until 2025, then the MetaQuotes-Demo broker feed (data/intraday_hd). Short history (~1.5 years, 2025-2026, broker only): USDJPY, AUDUSD, US30 - reported separately as an extra check, low confidence.
- US500 / USTECH100M are broker index CFDs used as stand-ins for SPY / QQQ, not the ETFs. Their costs are the broker's own bar spread (median where unknown) plus half a spread of slippage per market/stop fill; no commission; 4x leverage cap. That is roughly 3-4 basis points per round trip - about 4-5x the spec's ETF costs (~0.8 bp on SPY), so for the ETFs themselves the truth would sit between the x0 and x1 columns.
- FX costs are the spec defaults (0.8 pip EURUSD / 1.2 pip others spread, 0.2 pip slippage on market/stop fills, 3.5 USD per 100k per side) - not real bid/ask around the fixes.
- These markets/years overlap earlier tests in this repo, so this is not a fully fresh sample; the out-of-sample part (last 30% of dates) was touched once, here.
- 1R = 0.5% of the 100,000 starting equity (500) for every setup, including the ones without a stop (1x notional), so R is comparable. No compounding.


Files: `trades.csv`, `monthly_returns.csv`, `all_combinations.csv`, `equity_curve.png`, `drawdown.png`.
