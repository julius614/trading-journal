# Strategy 5 - London 4pm fix reversal

Markets: EURUSD, GBPUSD (M5, 2019-01-01 -> 2026-10-02). In-sample before 2024-06-05, out-of-sample after.


## Verdict: **FAIL**

Out-of-sample expectancy at costs x1 = -0.0047 R over 37 trades; out-of-sample net -87 USD vs random-entry 95th percentile 407 USD (strategy beats 77% of 100 random runs).


Chosen on in-sample data only: `{'exit_time': '17:30', 'min_move': 10, 'days': 'last1'}`


## Chosen combination: costs x0 / x1 / x2, in-sample vs out-of-sample

| metric | IS x0 | OOS x0 | IS x1 | OOS x1 | IS x2 | OOS x2 |
|---|---|---|---|---|---|---|
| trades | 53 | 37 | 53 | 37 | 53 | 37 |
| win_rate | 0.585 | 0.703 | 0.547 | 0.595 | 0.491 | 0.459 |
| avg_win | 182.70 | 73.4 | 175.92 | 66.57 | 176.84 | 66.45 |
| avg_loss | -152.50 | -119.13 | -157.45 | -103.41 | -157.81 | -95.05 |
| expectancy_R | 0.0871 | 0.0323 | 0.0499 | -0.0047 | 0.0127 | -0.0417 |
| profit_factor | 1.688 | 1.456 | 1.35 | 0.944 | 1.079 | 0.594 |
| net | 2,308.53 | 597.92 | 1,322.79 | -86.72 | 337.04 | -771.36 |
| net_pct | 2.31 | 0.6 | 1.32 | -0.09 | 0.34 | -0.77 |
| cagr | 0.45 | 0.29 | 0.26 | -0.04 | 0.07 | -0.37 |
| sharpe | 0.517 | 0.379 | 0.299 | -0.055 | 0.076 | -0.481 |
| max_dd_pct | -1.15 | -0.9 | -1.25 | -0.98 | -1.34 | -1.07 |
| longest_losing_streak | 4 | 2 | 4 | 3 | 4 | 4 |
| top5_share | 0.846 | 1.493 | 1.407 | nan | 5.243 | nan |


## Out-of-sample by market (costs x1) and buy-and-hold of the same market

| symbol | oos_trades | oos_exp_R | oos_net_pct | buy_and_hold_oos_pct |
|---|---|---|---|---|
| EURUSD | 16 | 0.0085 | 0.07 | 3.37 |
| GBPUSD | 21 | -0.0147 | -0.15 | 3.51 |


Buy-and-hold is not a meaningful benchmark for FX pairs (shown for completeness).


## Random-entry baseline (out-of-sample, costs x1, 100 runs)

Same entry times, holding times and sizes, random direction. Percentiles: 5th -1,859, median -568, 95th 407 USD. Strategy: -87 USD.


## Walk-forward (2-year train, 6-month test, costs x1)

| test_start | test_end | chosen | trades | exp_R | net |
|---|---|---|---|---|---|
| 2021-01-01 | 2021-07-01 | {'exit_time': '17:30', 'min_move': 10, 'days': 'last1'} | 6 | 0.0929 | 278.79 |
| 2021-07-01 | 2022-01-01 | {'exit_time': '17:30', 'min_move': 10, 'days': 'last1'} | 5 | -0.1309 | -327.35 |
| 2022-01-01 | 2022-07-01 | {'exit_time': '17:30', 'min_move': 10, 'days': 'last1'} | 3 | 0.2212 | 331.85 |
| 2022-07-01 | 2023-01-01 | {'exit_time': '16:30', 'min_move': 10, 'days': 'last1'} | 5 | 0.2291 | 572.77 |
| 2023-01-01 | 2023-07-01 | {'exit_time': '16:30', 'min_move': 5, 'days': 'last1'} | 8 | 0.0314 | 125.58 |
| 2023-07-01 | 2024-01-01 | {'exit_time': '16:30', 'min_move': 10, 'days': 'last1'} | 7 | -0.0641 | -224.52 |
| 2024-01-01 | 2024-07-01 | {'exit_time': '17:30', 'min_move': 5, 'days': 'last1'} | 3 | -0.1361 | -204.22 |
| 2024-07-01 | 2025-01-01 | {'exit_time': '16:30', 'min_move': 10, 'days': 'last1'} | 7 | -0.0016 | -5.6 |
| 2025-01-01 | 2025-07-01 | {'exit_time': '17:00', 'min_move': 10, 'days': 'last3'} | 17 | -0.0137 | -116.80 |
| 2025-07-01 | 2026-01-01 | {'exit_time': '17:00', 'min_move': 10, 'days': 'last1'} | 9 | 0.112 | 504.08 |
| 2026-01-01 | 2026-07-01 | {'exit_time': '17:00', 'min_move': 10, 'days': 'last1'} | 10 | -0.0254 | -127.14 |
| 2026-07-01 | 2026-10-02 | {'exit_time': '17:00', 'min_move': 10, 'days': 'last1'} | 4 | -0.1752 | -350.34 |


Walk-forward total: 457 USD over 84 trades; 5 of 12 test windows positive.


## Extra check: short-history markets (~1.5 years, chosen parameters, costs x1, low confidence)

| market | from | trades | exp_R | pf | net_pct |
|---|---|---|---|---|---|
| AUDUSD | 2025-11-28 | 5 | 0.0631 | 2.052 | 0.16 |
| USDJPY | 2025-05-30 | 10 | 0.0464 | 1.73 | 0.23 |


## All combinations

Choice uses the in-sample columns only; out-of-sample columns are shown so nothing is hidden, not for picking.

| exit_time | min_move | days | is_trades | is_exp_R | is_pf | is_net | oos_trades | oos_exp_R | oos_net |
|---|---|---|---|---|---|---|---|---|---|
| 16:30 | 0 | all | 2595 | -0.0331 | 0.631 | -43,006.97 | 1203 | -0.039 | -23,445.27 |
| 16:30 | 0 | last1 | 128 | -0.0266 | 0.752 | -1,704.04 | 58 | -0.0335 | -972.23 |
| 16:30 | 0 | last3 | 379 | -0.04 | 0.609 | -7,574.96 | 172 | -0.0307 | -2,636.48 |
| 16:30 | 5 | all | 1644 | -0.0343 | 0.639 | -28,186.16 | 697 | -0.0367 | -12,795.52 |
| 16:30 | 5 | last1 | 89 | -0.0203 | 0.821 | -902.62 | 45 | -0.0136 | -305.80 |
| 16:30 | 5 | last3 | 247 | -0.0383 | 0.648 | -4,730.72 | 119 | -0.0171 | -1,017.51 |
| 16:30 | 10 | all | 996 | -0.0315 | 0.683 | -15,699.13 | 378 | -0.0437 | -8,258.20 |
| 16:30 | 10 | last1 | 58 | 0.0094 | 1.103 | 273.98 | 37 | 0.004 | 73.61 |
| 16:30 | 10 | last3 | 156 | -0.0239 | 0.767 | -1,867.90 | 83 | -0.0067 | -277.17 |
| 17:00 | 0 | all | 2570 | -0.0405 | 0.685 | -52,081.38 | 1202 | -0.0374 | -22,483.73 |
| 17:00 | 0 | last1 | 124 | -0.031 | 0.828 | -1,919.44 | 58 | -0.0151 | -437.37 |
| 17:00 | 0 | last3 | 361 | -0.0322 | 0.778 | -5,809.44 | 172 | -0.0127 | -1,095.22 |
| 17:00 | 5 | all | 1632 | -0.0438 | 0.683 | -35,780.38 | 696 | -0.0342 | -11,903.84 |
| 17:00 | 5 | last1 | 85 | -0.0363 | 0.808 | -1,541.59 | 45 | 0.0084 | 188.97 |
| 17:00 | 5 | last3 | 236 | -0.0362 | 0.768 | -4,265.93 | 119 | -0.008 | -478.80 |
| 17:00 | 10 | all | 987 | -0.038 | 0.737 | -18,735.10 | 378 | -0.0536 | -10,133.63 |
| 17:00 | 10 | last1 | 53 | 0.024 | 1.174 | 635.94 | 37 | 0.0247 | 456.25 |
| 17:00 | 10 | last3 | 148 | -0.012 | 0.914 | -884.84 | 83 | -0.0019 | -79.7 |
| 17:30 | 0 | all | 2570 | -0.0371 | 0.733 | -47,618.34 | 1202 | -0.0444 | -26,662.76 |
| 17:30 | 0 | last1 | 124 | -0.0198 | 0.9 | -1,227.39 | 58 | -0.0162 | -469.28 |
| 17:30 | 0 | last3 | 361 | -0.0292 | 0.808 | -5,266.49 | 172 | -0.0027 | -232.40 |
| 17:30 | 5 | all | 1632 | -0.0401 | 0.73 | -32,684.90 | 696 | -0.045 | -15,665.77 |
| 17:30 | 5 | last1 | 85 | -0.0085 | 0.956 | -360.83 | 45 | -0.0078 | -175.60 |
| 17:30 | 5 | last3 | 236 | -0.0258 | 0.831 | -3,044.37 | 119 | -0.0026 | -153.12 |
| 17:30 | 10 | all | 987 | -0.0311 | 0.798 | -15,342.67 | 378 | -0.074 | -13,984.16 |
| 17:30 | 10 | last1 | 53 | 0.0499 | 1.35 | 1,322.79 | 37 | -0.0047 | -86.72 |
| 17:30 | 10 | last3 | 148 | 0.0045 | 1.033 | 334.81 | 83 | -0.0101 | -417.66 |


## Notes

- Data: M5 bars only (no 1-minute bars, no bid/ask quotes). Fills use M5 bar opens and highs/lows; stop-before-target is assumed whenever one bar covers both.
- Long history 2019-2026: HistData M5 until 2025, then the MetaQuotes-Demo broker feed (data/intraday_hd). Short history (~1.5 years, 2025-2026, broker only): USDJPY, AUDUSD, US30 - reported separately as an extra check, low confidence.
- US500 / USTECH100M are broker index CFDs used as stand-ins for SPY / QQQ, not the ETFs. Their costs are the broker's own bar spread (median where unknown) plus half a spread of slippage per market/stop fill; no commission; 4x leverage cap. That is roughly 3-4 basis points per round trip - about 4-5x the spec's ETF costs (~0.8 bp on SPY), so for the ETFs themselves the truth would sit between the x0 and x1 columns.
- FX costs are the spec defaults (0.8 pip EURUSD / 1.2 pip others spread, 0.2 pip slippage on market/stop fills, 3.5 USD per 100k per side) - not real bid/ask around the fixes.
- These markets/years overlap earlier tests in this repo, so this is not a fully fresh sample; the out-of-sample part (last 30% of dates) was touched once, here.
- 1R = 0.5% of the 100,000 starting equity (500) for every setup, including the ones without a stop (1x notional), so R is comparable. No compounding.


Files: `trades.csv`, `monthly_returns.csv`, `all_combinations.csv`, `equity_curve.png`, `drawdown.png`.
