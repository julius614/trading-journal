# Strategy 3 - intraday momentum on FOMC/CPI/NFP days

Markets: US500, USTECH100M (M5, 2019-01-01 -> 2026-10-02). In-sample before 2024-06-05, out-of-sample after.


## Verdict: **FAIL**

Out-of-sample expectancy at costs x1 = 0.1401 R over 36 trades; out-of-sample net 2,521 USD vs random-entry 95th percentile 4,069 USD (strategy beats 87% of 100 random runs).


Chosen on in-sample data only: `{'event': 'FOMC', 'variant': 'base'}`


## Chosen combination: costs x0 / x1 / x2, in-sample vs out-of-sample

| metric | IS x0 | OOS x0 | IS x1 | OOS x1 | IS x2 | OOS x2 |
|---|---|---|---|---|---|---|
| trades | 78 | 36 | 78 | 36 | 78 | 36 |
| win_rate | 0.513 | 0.528 | 0.462 | 0.5 | 0.436 | 0.5 |
| avg_win | 467.19 | 353.72 | 479.50 | 354.84 | 472.10 | 336.71 |
| avg_loss | -387.04 | -209.10 | -381.71 | -214.77 | -399.34 | -232.46 |
| expectancy_R | 0.1021 | 0.1759 | 0.0315 | 0.1401 | -0.039 | 0.1043 |
| profit_factor | 1.271 | 1.891 | 1.077 | 1.652 | 0.914 | 1.448 |
| net | 3,980.08 | 3,166.09 | 1,230.13 | 2,521.32 | -1,519.81 | 1,876.54 |
| net_pct | 3.98 | 3.17 | 1.23 | 2.52 | -1.52 | 1.88 |
| cagr | 0.75 | 1.39 | 0.23 | 1.11 | -0.29 | 0.83 |
| sharpe | 0.234 | 0.87 | 0.073 | 0.703 | -0.09 | 0.529 |
| max_dd_pct | -6 | -1.11 | -7.28 | -1.23 | -9.19 | -1.36 |
| longest_losing_streak | 7 | 3 | 7 | 5 | 7 | 5 |
| top5_share | 1.908 | 1.172 | 5.986 | 1.437 | nan | 1.885 |


## Out-of-sample by market (costs x1) and buy-and-hold of the same market

| symbol | oos_trades | oos_exp_R | oos_net_pct | buy_and_hold_oos_pct |
|---|---|---|---|---|
| US500 | 19 | -0.0196 | -0.19 | 45.32 |
| USTECH100M | 17 | 0.3186 | 2.71 | 64.02 |


**Trade count warning:** chosen combination has 114 trades in total (36 out-of-sample). The spec says not to trust fewer than 50.
Events file: 248 dates, source = memory (official calendar pages could not be fetched from this environment; dates were written from memory and spot-checked by web search for 2025-2026).


## Random-entry baseline (out-of-sample, costs x1, 100 runs)

Same entry times, holding times and sizes, random direction. Percentiles: 5th -3,908, median -139, 95th 4,069 USD. Strategy: 2,521 USD.


## Walk-forward (2-year train, 6-month test, costs x1)

| test_start | test_end | chosen | trades | exp_R | net |
|---|---|---|---|---|---|
| 2021-01-01 | 2021-07-01 | {'event': 'NFP', 'variant': '2B'} | 9 | 0.0289 | 130.08 |
| 2021-07-01 | 2022-01-01 | {'event': 'NFP', 'variant': '2B'} | 5 | -0.1506 | -376.42 |
| 2022-01-01 | 2022-07-01 | {'event': 'NFP', 'variant': '2B'} | 4 | -0.6587 | -1,317.39 |
| 2022-07-01 | 2023-01-01 | {'event': 'CPI', 'variant': '2B'} | 10 | -0.1799 | -899.64 |
| 2023-01-01 | 2023-07-01 | {'event': 'FOMC', 'variant': 'base'} | 2 | 0.1586 | 158.56 |
| 2023-07-01 | 2024-01-01 | {'event': 'FOMC', 'variant': 'base'} | 4 | 0.3405 | 681.07 |
| 2024-01-01 | 2024-07-01 | {'event': 'FOMC', 'variant': 'base'} | 8 | -0.3716 | -1,486.52 |
| 2024-07-01 | 2025-01-01 | {'event': 'FOMC', 'variant': 'base'} | 8 | -0.1192 | -476.64 |
| 2025-01-01 | 2025-07-01 | {'event': 'all', 'variant': '2B'} | 14 | -0.189 | -1,323.35 |
| 2025-07-01 | 2026-01-01 | {'event': 'FOMC', 'variant': 'base'} | 8 | -0.0459 | -183.55 |
| 2026-01-01 | 2026-07-01 | {'event': 'FOMC', 'variant': 'base'} | 7 | -0.0821 | -287.50 |
| 2026-07-01 | 2026-10-02 | {'event': 'FOMC', 'variant': 'base'} | 3 | 1.044 | 1,565.58 |


Walk-forward total: -3,816 USD over 82 trades; 4 of 12 test windows positive.


## Extra check: short-history markets (~1.5 years, chosen parameters, costs x1, low confidence)

| market | from | trades | exp_R | pf | net_pct |
|---|---|---|---|---|---|
| US30 | 2025-03-19 | 12 | -0.0101 | 0.941 | -0.06 |


## All combinations

Choice uses the in-sample columns only; out-of-sample columns are shown so nothing is hidden, not for picking.

| event | variant | is_trades | is_exp_R | is_pf | is_net | oos_trades | oos_exp_R | oos_net |
|---|---|---|---|---|---|---|---|---|
| FOMC | base | 78 | 0.0315 | 1.077 | 1,230.13 | 36 | 0.1401 | 2,521.32 |
| FOMC | 2B | 36 | -0.0802 | 0.814 | -1,444.34 | 19 | 0.0624 | 593.02 |
| CPI | base | 118 | -0.1517 | 0.374 | -8,951.84 | 51 | -0.172 | -4,385.86 |
| CPI | 2B | 67 | -0.1986 | 0.358 | -6,652.80 | 31 | -0.1375 | -2,131.93 |
| NFP | base | 118 | -0.202 | 0.327 | -11,916.54 | 50 | 0.0134 | 335.04 |
| NFP | 2B | 55 | -0.0999 | 0.582 | -2,747.74 | 29 | -0.0075 | -108.72 |
| all | base | 310 | -0.118 | 0.608 | -18,294.16 | 135 | -0.0211 | -1,422.57 |
| all | 2B | 156 | -0.1235 | 0.59 | -9,634.54 | 77 | -0.04 | -1,540.69 |


## Notes

- Data: M5 bars only (no 1-minute bars, no bid/ask quotes). Fills use M5 bar opens and highs/lows; stop-before-target is assumed whenever one bar covers both.
- Long history 2019-2026: HistData M5 until 2025, then the MetaQuotes-Demo broker feed (data/intraday_hd). Short history (~1.5 years, 2025-2026, broker only): USDJPY, AUDUSD, US30 - reported separately as an extra check, low confidence.
- US500 / USTECH100M are broker index CFDs used as stand-ins for SPY / QQQ, not the ETFs. Their costs are the broker's own bar spread (median where unknown) plus half a spread of slippage per market/stop fill; no commission; 4x leverage cap. That is roughly 3-4 basis points per round trip - about 4-5x the spec's ETF costs (~0.8 bp on SPY), so for the ETFs themselves the truth would sit between the x0 and x1 columns.
- FX costs are the spec defaults (0.8 pip EURUSD / 1.2 pip others spread, 0.2 pip slippage on market/stop fills, 3.5 USD per 100k per side) - not real bid/ask around the fixes.
- These markets/years overlap earlier tests in this repo, so this is not a fully fresh sample; the out-of-sample part (last 30% of dates) was touched once, here.
- 1R = 0.5% of the 100,000 starting equity (500) for every setup, including the ones without a stop (1x notional), so R is comparable. No compounding.


Files: `trades.csv`, `monthly_returns.csv`, `all_combinations.csv`, `equity_curve.png`, `drawdown.png`.
