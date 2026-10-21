# Strategy 4 - VWAP trend-following

Markets: US500, USTECH100M (M5, 2019-01-01 -> 2026-10-02). In-sample before 2024-06-05, out-of-sample after.


## Verdict: **FAIL**

Out-of-sample expectancy at costs x1 = -0.0265 R over 2494 trades; out-of-sample net -33,103 USD vs random-entry 95th percentile -3,291 USD (strategy beats 68% of 100 random runs).


Chosen on in-sample data only: `{'check_every': 15, 'buffer': 0.001}`


## Chosen combination: costs x0 / x1 / x2, in-sample vs out-of-sample

| metric | IS x0 | OOS x0 | IS x1 | OOS x1 | IS x2 | OOS x2 |
|---|---|---|---|---|---|---|
| trades | 5,798 | 2,494 | 5,798 | 2,494 | 5,798 | 2,494 |
| win_rate | 0.383 | 0.391 | 0.358 | 0.375 | 0.338 | 0.36 |
| avg_win | 606.83 | 463.11 | 613.45 | 464.23 | 615.31 | 465.55 |
| avg_loss | -332.79 | -288.88 | -353.89 | -299.65 | -377.48 | -310.44 |
| expectancy_R | 0.0543 | 0.0096 | -0.0147 | -0.0265 | -0.0837 | -0.0627 |
| profit_factor | 1.132 | 1.027 | 0.968 | 0.929 | 0.832 | 0.842 |
| net | 157,391.16 | 11,969.23 | -42,693.81 | -33,103.14 | -242,778.78 | -78,175.52 |
| net_pct | 157.39 | 11.97 | -42.69 | -33.1 | -242.78 | -78.18 |
| cagr | 19.05 | 4.98 | -9.76 | -15.88 | nan | -48.05 |
| sharpe | 1.059 | 0.218 | -0.279 | -0.594 | -1.536 | -1.38 |
| max_dd_pct | -18.24 | -21.38 | -72.36 | -46.04 | -242.18 | -81.75 |
| longest_losing_streak | 15 | 14 | 16 | 15 | 16 | 15 |
| top5_share | 0.172 | 2.497 | nan | nan | nan | nan |


## Out-of-sample by market (costs x1) and buy-and-hold of the same market

| symbol | oos_trades | oos_exp_R | oos_net_pct | buy_and_hold_oos_pct |
|---|---|---|---|---|
| US500 | 1165 | -0.0273 | -15.88 | 45.32 |
| USTECH100M | 1329 | -0.0259 | -17.22 | 64.02 |


Positions per trading day (chosen combination): mean 4.58, max 16.


## Random-entry baseline (out-of-sample, costs x1, 100 runs)

Same entry times, holding times and sizes, random direction. Percentiles: 5th -93,962, median -43,995, 95th -3,291 USD. Strategy: -33,103 USD.


## Walk-forward (2-year train, 6-month test, costs x1)

| test_start | test_end | chosen | trades | exp_R | net |
|---|---|---|---|---|---|
| 2021-01-01 | 2021-07-01 | {'check_every': 15, 'buffer': 0.001} | 544 | 0.0024 | 641.59 |
| 2021-07-01 | 2022-01-01 | {'check_every': 15, 'buffer': 0.001} | 482 | 0.0649 | 15,652.64 |
| 2022-01-01 | 2022-07-01 | {'check_every': 15, 'buffer': 0.001} | 770 | 0.0078 | 2,990.10 |
| 2022-07-01 | 2023-01-01 | {'check_every': 15, 'buffer': 0.001} | 709 | -0.0001 | -20.63 |
| 2023-01-01 | 2023-07-01 | {'check_every': 15, 'buffer': 0.0005} | 217 | 0.0914 | 9,912.37 |
| 2023-07-01 | 2024-01-01 | {'check_every': 15, 'buffer': 0.0005} | 638 | -0.0587 | -18,741.05 |
| 2024-01-01 | 2024-07-01 | {'check_every': 15, 'buffer': 0.0005} | 735 | -0.0257 | -9,433.34 |
| 2024-07-01 | 2025-01-01 | {'check_every': 15, 'buffer': 0.001} | 500 | 0.0918 | 22,949.68 |
| 2025-01-01 | 2025-07-01 | {'check_every': 15, 'buffer': 0.001} | 636 | -0.0658 | -20,937.01 |
| 2025-07-01 | 2026-01-01 | {'check_every': 15, 'buffer': 0.001} | 481 | -0.0299 | -7,182.52 |
| 2026-01-01 | 2026-07-01 | {'check_every': 5, 'buffer': 0.0005} | 977 | -0.0362 | -17,665.39 |
| 2026-07-01 | 2026-10-02 | {'check_every': 5, 'buffer': 0.0005} | 508 | -0.0399 | -10,135.45 |


Walk-forward total: -31,969 USD over 7197 trades; 5 of 12 test windows positive.


## Extra check: short-history markets (~1.5 years, chosen parameters, costs x1, low confidence)

| market | from | trades | exp_R | pf | net_pct |
|---|---|---|---|---|---|
| US30 | 2025-03-05 | 768 | -0.0325 | 0.905 | -12.5 |


## All combinations

Choice uses the in-sample columns only; out-of-sample columns are shown so nothing is hidden, not for picking.

| check_every | buffer | is_trades | is_exp_R | is_pf | is_net | oos_trades | oos_exp_R | oos_net |
|---|---|---|---|---|---|---|---|---|
| 5 | 0 | 21,430 | -0.0549 | 0.747 | -588,787.35 | 9,029 | -0.0282 | -127,307.99 |
| 5 | 0.0005 | 10,995 | -0.0482 | 0.856 | -264,872.54 | 4,555 | -0.0146 | -33,331.59 |
| 5 | 0.001 | 7,697 | -0.0462 | 0.889 | -177,652.28 | 3,152 | -0.0206 | -32,543.12 |
| 15 | 0 | 11,926 | -0.0324 | 0.887 | -193,454.50 | 5,007 | -0.0289 | -72,449.67 |
| 15 | 0.0005 | 7,718 | -0.0197 | 0.949 | -75,904.79 | 3,331 | -0.0333 | -55,541.12 |
| 15 | 0.001 | 5,798 | -0.0147 | 0.968 | -42,693.81 | 2,494 | -0.0265 | -33,103.14 |


## Notes

- Data: M5 bars only (no 1-minute bars, no bid/ask quotes). Fills use M5 bar opens and highs/lows; stop-before-target is assumed whenever one bar covers both.
- Long history 2019-2026: HistData M5 until 2025, then the MetaQuotes-Demo broker feed (data/intraday_hd). Short history (~1.5 years, 2025-2026, broker only): USDJPY, AUDUSD, US30 - reported separately as an extra check, low confidence.
- US500 / USTECH100M are broker index CFDs used as stand-ins for SPY / QQQ, not the ETFs. Their costs are the broker's own bar spread (median where unknown) plus half a spread of slippage per market/stop fill; no commission; 4x leverage cap. That is roughly 3-4 basis points per round trip - about 4-5x the spec's ETF costs (~0.8 bp on SPY), so for the ETFs themselves the truth would sit between the x0 and x1 columns.
- FX costs are the spec defaults (0.8 pip EURUSD / 1.2 pip others spread, 0.2 pip slippage on market/stop fills, 3.5 USD per 100k per side) - not real bid/ask around the fixes.
- These markets/years overlap earlier tests in this repo, so this is not a fully fresh sample; the out-of-sample part (last 30% of dates) was touched once, here.
- 1R = 0.5% of the 100,000 starting equity (500) for every setup, including the ones without a stop (1x notional), so R is comparable. No compounding.


Files: `trades.csv`, `monthly_returns.csv`, `all_combinations.csv`, `equity_curve.png`, `drawdown.png`.
