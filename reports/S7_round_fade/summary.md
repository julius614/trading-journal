# Strategy 7 - round-number fade

Markets: EURUSD, GBPUSD (M5, 2019-01-01 -> 2026-10-02). In-sample before 2024-06-05, out-of-sample after.


## Verdict: **FAIL**

Out-of-sample expectancy at costs x1 = -0.0679 R over 362 trades; out-of-sample net -12,291 USD vs random-entry 95th percentile 383 USD (strategy beats 55% of 100 random runs).


Chosen on in-sample data only: `{'entry_buffer': 5, 'stop_pips': 25, 'target_R': 2, 'approach_atr': 1}`


## Chosen combination: costs x0 / x1 / x2, in-sample vs out-of-sample

| metric | IS x0 | OOS x0 | IS x1 | OOS x1 | IS x2 | OOS x2 |
|---|---|---|---|---|---|---|
| trades | 1,112 | 362 | 1,112 | 362 | 1,112 | 362 |
| win_rate | 0.471 | 0.497 | 0.433 | 0.464 | 0.409 | 0.423 |
| avg_win | 440.34 | 359.10 | 442.81 | 348.92 | 433.92 | 346.98 |
| avg_loss | -387.94 | -353.19 | -396.02 | -365.51 | -414.26 | -373.34 |
| expectancy_R | 0.0047 | 0.002 | -0.0648 | -0.0679 | -0.1344 | -0.1378 |
| profit_factor | 1.012 | 1.006 | 0.855 | 0.827 | 0.725 | 0.68 |
| net | 2,630 | 358.33 | -36,053.91 | -12,290.68 | -74,737.83 | -24,939.69 |
| net_pct | 2.63 | 0.36 | -36.05 | -12.29 | -74.74 | -24.94 |
| cagr | 0.48 | 0.15 | -7.92 | -5.5 | -22.43 | -11.64 |
| sharpe | 0.065 | 0.026 | -0.887 | -0.889 | -1.823 | -1.786 |
| max_dd_pct | -14.56 | -8.05 | -40.96 | -17.25 | -76.39 | -27.09 |
| longest_losing_streak | 8 | 8 | 13 | 8 | 13 | 10 |
| top5_share | 1.901 | 13.95 | nan | nan | nan | nan |


## Out-of-sample by market (costs x1) and buy-and-hold of the same market

| symbol | oos_trades | oos_exp_R | oos_net_pct | buy_and_hold_oos_pct |
|---|---|---|---|---|
| EURUSD | 147 | -0.0765 | -5.63 | 3.37 |
| GBPUSD | 215 | -0.062 | -6.67 | 3.51 |


Buy-and-hold is not a meaningful benchmark for FX pairs (shown for completeness).


## Random-entry baseline (out-of-sample, costs x1, 100 runs)

Same entry times, holding times and sizes, random direction. Percentiles: 5th -27,160, median -13,201, 95th 383 USD. Strategy: -12,291 USD.


## Walk-forward (2-year train, 6-month test, costs x1)

| test_start | test_end | chosen | trades | exp_R | net |
|---|---|---|---|---|---|
| 2021-01-01 | 2021-07-01 | {'entry_buffer': 0, 'stop_pips': 25, 'target_R': 1, 'approach_atr': 1} | 66 | -0.0271 | -894.74 |
| 2021-07-01 | 2022-01-01 | {'entry_buffer': 2, 'stop_pips': 25, 'target_R': 2, 'approach_atr': 1} | 58 | -0.1065 | -3,087.76 |
| 2022-01-01 | 2022-07-01 | {'entry_buffer': 0, 'stop_pips': 25, 'target_R': 1, 'approach_atr': 1} | 100 | -0.0476 | -2,379.70 |
| 2022-07-01 | 2023-01-01 | {'entry_buffer': 0, 'stop_pips': 25, 'target_R': 2, 'approach_atr': 1} | 137 | -0.1031 | -7,061.24 |
| 2023-01-01 | 2023-07-01 | {'entry_buffer': 0, 'stop_pips': 25, 'target_R': 2, 'approach_atr': 1} | 81 | -0.297 | -12,026.66 |
| 2023-07-01 | 2024-01-01 | {'entry_buffer': 5, 'stop_pips': 25, 'target_R': 1.5, 'approach_atr': 2} | 79 | -0.0013 | -51.07 |
| 2024-01-01 | 2024-07-01 | {'entry_buffer': 5, 'stop_pips': 25, 'target_R': 2, 'approach_atr': 1} | 61 | -0.0075 | -228.98 |
| 2024-07-01 | 2025-01-01 | {'entry_buffer': 5, 'stop_pips': 15, 'target_R': 2, 'approach_atr': 1} | 76 | 0.0528 | 2,006.27 |
| 2025-01-01 | 2025-07-01 | {'entry_buffer': 5, 'stop_pips': 25, 'target_R': 2, 'approach_atr': 2} | 81 | -0.2153 | -8,721.61 |
| 2025-07-01 | 2026-01-01 | {'entry_buffer': 2, 'stop_pips': 25, 'target_R': 2, 'approach_atr': 1} | 58 | -0.1743 | -5,055.94 |
| 2026-01-01 | 2026-07-01 | {'entry_buffer': 2, 'stop_pips': 25, 'target_R': 2, 'approach_atr': 1} | 66 | -0.006 | -198.48 |
| 2026-07-01 | 2026-10-02 | {'entry_buffer': 2, 'stop_pips': 25, 'target_R': 2, 'approach_atr': 1} | 21 | -0.287 | -3,013.97 |


Walk-forward total: -40,714 USD over 884 trades; 1 of 12 test windows positive.


## Extra check: short-history markets (~1.5 years, chosen parameters, costs x1, low confidence)

| market | from | trades | exp_R | pf | net_pct |
|---|---|---|---|---|---|
| AUDUSD | 2025-06-13 | 36 | -0.0775 | 0.747 | -1.4 |
| USDJPY | 2025-06-02 | 143 | -0.1395 | 0.712 | -9.97 |


## All combinations

Choice uses the in-sample columns only; out-of-sample columns are shown so nothing is hidden, not for picking.

| entry_buffer | stop_pips | target_R | approach_atr | is_trades | is_exp_R | is_pf | is_net | oos_trades | oos_exp_R | oos_net |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 10 | 1 | 1 | 863 | -0.2494 | 0.606 | -107,623.30 | 268 | -0.1988 | -26,644.75 |
| 0 | 10 | 1 | 2 | 698 | -0.2577 | 0.596 | -89,939.15 | 210 | -0.2139 | -22,457.55 |
| 0 | 10 | 1.5 | 1 | 863 | -0.2503 | 0.663 | -107,998.30 | 268 | -0.1923 | -25,774.75 |
| 0 | 10 | 1.5 | 2 | 698 | -0.2581 | 0.654 | -90,084.15 | 210 | -0.229 | -24,047.55 |
| 0 | 10 | 2 | 1 | 863 | -0.2471 | 0.695 | -106,638.30 | 268 | -0.1834 | -24,569.75 |
| 0 | 10 | 2 | 2 | 698 | -0.252 | 0.689 | -87,939.15 | 210 | -0.2234 | -23,452.55 |
| 0 | 15 | 1 | 1 | 862 | -0.1518 | 0.734 | -65,420.63 | 268 | -0.1482 | -19,863.17 |
| 0 | 15 | 1 | 2 | 697 | -0.1555 | 0.728 | -54,201.20 | 210 | -0.1533 | -16,098.37 |
| 0 | 15 | 1.5 | 1 | 862 | -0.1579 | 0.762 | -68,047.30 | 268 | -0.1691 | -22,656.50 |
| 0 | 15 | 1.5 | 2 | 697 | -0.169 | 0.747 | -58,884.53 | 210 | -0.2061 | -21,645.03 |
| 0 | 15 | 2 | 1 | 862 | -0.2106 | 0.709 | -90,773.97 | 268 | -0.1378 | -18,466.50 |
| 0 | 15 | 2 | 2 | 697 | -0.2185 | 0.7 | -76,137.87 | 210 | -0.1895 | -19,895.03 |
| 0 | 25 | 1 | 1 | 862 | -0.0714 | 0.848 | -30,758.38 | 268 | -0.067 | -8,973.90 |
| 0 | 25 | 1 | 2 | 697 | -0.0954 | 0.803 | -33,250.72 | 210 | -0.0938 | -9,849.02 |
| 0 | 25 | 1.5 | 1 | 862 | -0.099 | 0.81 | -42,654.38 | 268 | -0.082 | -10,981.90 |
| 0 | 25 | 1.5 | 2 | 697 | -0.1334 | 0.753 | -46,498.72 | 210 | -0.1196 | -12,553.02 |
| 0 | 25 | 2 | 1 | 862 | -0.0909 | 0.83 | -39,182.38 | 268 | -0.0742 | -9,937.90 |
| 0 | 25 | 2 | 2 | 697 | -0.1305 | 0.763 | -45,486.72 | 210 | -0.1248 | -13,101.02 |
| 2 | 10 | 1 | 1 | 973 | -0.1847 | 0.689 | -89,878.35 | 313 | -0.1185 | -18,547.56 |
| 2 | 10 | 1 | 2 | 778 | -0.2168 | 0.646 | -84,342.82 | 250 | -0.1469 | -18,362.40 |
| 2 | 10 | 1.5 | 1 | 973 | -0.2104 | 0.703 | -102,374.18 | 313 | -0.0991 | -15,514.23 |
| 2 | 10 | 1.5 | 2 | 778 | -0.229 | 0.681 | -89,080.32 | 250 | -0.1076 | -13,445.73 |
| 2 | 10 | 2 | 1 | 973 | -0.2061 | 0.731 | -100,282.52 | 313 | -0.1354 | -21,193.39 |
| 2 | 10 | 2 | 2 | 778 | -0.2358 | 0.696 | -91,742.82 | 250 | -0.1676 | -20,949.90 |
| 2 | 15 | 1 | 1 | 972 | -0.1351 | 0.755 | -65,665.68 | 313 | -0.081 | -12,674.75 |
| 2 | 15 | 1 | 2 | 777 | -0.15 | 0.731 | -58,270.01 | 250 | -0.0813 | -10,161.69 |
| 2 | 15 | 1.5 | 1 | 972 | -0.149 | 0.765 | -72,398.04 | 313 | -0.0865 | -13,533.57 |
| 2 | 15 | 1.5 | 2 | 777 | -0.1752 | 0.728 | -68,058.25 | 250 | -0.1017 | -12,717.58 |
| 2 | 15 | 2 | 1 | 972 | -0.1726 | 0.745 | -83,880.39 | 313 | -0.0904 | -14,145.34 |
| 2 | 15 | 2 | 2 | 777 | -0.2102 | 0.695 | -81,652.37 | 250 | -0.1198 | -14,973.46 |
| 2 | 25 | 1 | 1 | 972 | -0.0891 | 0.806 | -43,308.02 | 313 | -0.0269 | -4,206.32 |
| 2 | 25 | 1 | 2 | 777 | -0.1276 | 0.732 | -49,584.82 | 250 | -0.0417 | -5,209.21 |
| 2 | 25 | 1.5 | 1 | 972 | -0.0911 | 0.815 | -44,282.10 | 313 | -0.0415 | -6,491.51 |
| 2 | 25 | 1.5 | 2 | 777 | -0.1431 | 0.721 | -55,608.90 | 250 | -0.0644 | -8,053.66 |
| 2 | 25 | 2 | 1 | 972 | -0.0807 | 0.839 | -39,220.99 | 313 | -0.0253 | -3,965.58 |
| 2 | 25 | 2 | 2 | 777 | -0.1322 | 0.745 | -51,377.42 | 250 | -0.0583 | -7,288.84 |
| 5 | 10 | 1 | 1 | 1,112 | -0.1573 | 0.722 | -87,451.16 | 362 | -0.1162 | -21,031.36 |
| 5 | 10 | 1 | 2 | 902 | -0.1528 | 0.728 | -68,918.66 | 288 | -0.0887 | -12,769.79 |
| 5 | 10 | 1.5 | 1 | 1,112 | -0.1447 | 0.776 | -80,461.16 | 362 | -0.1534 | -27,768.02 |
| 5 | 10 | 1.5 | 2 | 902 | -0.1539 | 0.762 | -69,428.66 | 288 | -0.1477 | -21,266.46 |
| 5 | 10 | 2 | 1 | 1,112 | -0.1895 | 0.73 | -105,351.16 | 362 | -0.1642 | -29,711.36 |
| 5 | 10 | 2 | 2 | 902 | -0.2025 | 0.712 | -91,305.32 | 288 | -0.173 | -24,909.79 |
| 5 | 15 | 1 | 1 | 1,112 | -0.1096 | 0.788 | -60,913.37 | 362 | -0.0861 | -15,588.52 |
| 5 | 15 | 1 | 2 | 902 | -0.1126 | 0.782 | -50,788.99 | 288 | -0.0753 | -10,844.84 |
| 5 | 15 | 1.5 | 1 | 1,112 | -0.1537 | 0.74 | -85,463.37 | 362 | -0.1409 | -25,503.52 |
| 5 | 15 | 1.5 | 2 | 902 | -0.1664 | 0.719 | -75,026.49 | 288 | -0.151 | -21,742.34 |
| 5 | 15 | 2 | 1 | 1,112 | -0.1321 | 0.782 | -73,450.87 | 362 | -0.1238 | -22,408.52 |
| 5 | 15 | 2 | 2 | 902 | -0.14 | 0.769 | -63,143.99 | 288 | -0.1304 | -18,772.34 |
| 5 | 25 | 1 | 1 | 1,112 | -0.0876 | 0.794 | -48,722.25 | 362 | -0.0874 | -15,822.34 |
| 5 | 25 | 1 | 2 | 902 | -0.1122 | 0.744 | -50,619.33 | 288 | -0.1008 | -14,511.56 |
| 5 | 25 | 1.5 | 1 | 1,112 | -0.0664 | 0.85 | -36,910.58 | 362 | -0.0644 | -11,659.01 |
| 5 | 25 | 1.5 | 2 | 902 | -0.0879 | 0.806 | -39,627.66 | 288 | -0.0782 | -11,264.90 |
| 5 | 25 | 2 | 1 | 1,112 | -0.0648 | 0.855 | -36,053.91 | 362 | -0.0679 | -12,290.68 |
| 5 | 25 | 2 | 2 | 902 | -0.0892 | 0.806 | -40,224.33 | 288 | -0.0891 | -12,831.56 |


## Notes

- Data: M5 bars only (no 1-minute bars, no bid/ask quotes). Fills use M5 bar opens and highs/lows; stop-before-target is assumed whenever one bar covers both.
- Long history 2019-2026: HistData M5 until 2025, then the MetaQuotes-Demo broker feed (data/intraday_hd). Short history (~1.5 years, 2025-2026, broker only): USDJPY, AUDUSD, US30 - reported separately as an extra check, low confidence.
- US500 / USTECH100M are broker index CFDs used as stand-ins for SPY / QQQ, not the ETFs. Their costs are the broker's own bar spread (median where unknown) plus half a spread of slippage per market/stop fill; no commission; 4x leverage cap. That is roughly 3-4 basis points per round trip - about 4-5x the spec's ETF costs (~0.8 bp on SPY), so for the ETFs themselves the truth would sit between the x0 and x1 columns.
- FX costs are the spec defaults (0.8 pip EURUSD / 1.2 pip others spread, 0.2 pip slippage on market/stop fills, 3.5 USD per 100k per side) - not real bid/ask around the fixes.
- These markets/years overlap earlier tests in this repo, so this is not a fully fresh sample; the out-of-sample part (last 30% of dates) was touched once, here.
- 1R = 0.5% of the 100,000 starting equity (500) for every setup, including the ones without a stop (1x notional), so R is comparable. No compounding.


Files: `trades.csv`, `monthly_returns.csv`, `all_combinations.csv`, `equity_curve.png`, `drawdown.png`.
