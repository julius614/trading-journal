# C2 - Swing liquidity-sweep reversal on daily bars (data-inspired)


## Verdict: **FAIL**

Chosen on discovery only: `{'N': 20, 'over': 0.5, 'target_R': 3, 'stop_buffer': 0}`. Hold-out (2022-01-01 on): 1133 trades, expectancy -0.2077 R at x1, -0.3421 R at x2; net -117,687 USD vs random 99th percentile -22,339 USD.


## Gates (pre-declared)

| gate | passed |
|---|---|
| JOIN discovery exp>0 @x1 | NO |
| KEEP validate exp>0 @x1 | NO |
| (a) hold-out exp>0 @x1 and >=0 @x2 | NO |
| (b) beats random-direction 99th pct | NO |
| (c) >= 100 hold-out trades | yes |
| (d) > half of walk-forward windows positive | NO |
| (e) plateau: >= 3 of 4 neighbours positive (validate) | NO |


## Chosen combination by period, costs x0 / x1 / x2

| metric | discovery x0 | discovery x1 | discovery x2 | validate x0 | validate x1 | validate x2 | hold-out x0 | hold-out x1 | hold-out x2 |
|---|---|---|---|---|---|---|---|---|---|
| trades | 2,212 | 2,212 | 2,212 | 1,087 | 1,087 | 1,087 | 1,133 | 1,133 | 1,133 |
| win_rate | 0.248 | 0.247 | 0.245 | 0.255 | 0.251 | 0.249 | 0.242 | 0.241 | 0.237 |
| expectancy_R | -0.0435 | -0.1657 | -0.2878 | -0.0124 | -0.1644 | -0.3165 | -0.0734 | -0.2077 | -0.3421 |
| profit_factor | 0.942 | 0.802 | 0.689 | 0.983 | 0.806 | 0.668 | 0.902 | 0.755 | 0.638 |
| net | -48,155.06 | -183,237.10 | -318,319.14 | -6,721.33 | -89,369.65 | -172,017.97 | -41,591.68 | -117,686.72 | -193,781.76 |
| net_pct | -48.16 | -183.24 | -318.32 | -6.72 | -89.37 | -172.02 | -41.59 | -117.69 | -193.78 |
| cagr | -5.12 | nan | nan | -1.37 | -35.96 | nan | -10.71 | nan | nan |
| sharpe | -0.002 | -0.787 | -1.557 | -0.265 | -1.41 | -2.491 | -0.75 | -1.743 | -2.683 |
| max_dd_pct | -34.49 | -110.76 | -215.02 | -30.61 | -88.63 | -154.77 | -49.29 | -106.35 | -165.04 |
| longest_losing_streak | 22 | 22 | 22 | 26 | 26 | 26 | 21 | 21 | 21 |
| top5_share | nan | nan | nan | nan | nan | nan | nan | nan | nan |


## Hold-out by market (x1)

| symbol | trades | exp_R | net |
|---|---|---|---|
| AUDUSD | 102 | -0.2113 | -10,776.54 |
| EURUSD | 93 | 0.0547 | 2,543.69 |
| GBPUSD | 103 | -0.0928 | -4,779.09 |
| NZDUSD | 115 | 0.09533 | 5,481.21 |
| US30 | 113 | -0.3233 | -18,268.76 |
| US500 | 115 | -0.4874 | -28,026.35 |
| USDCAD | 114 | -0.293 | -16,698.76 |
| USDCHF | 97 | -0.354 | -17,168.11 |
| USDJPY | 94 | -0.3015 | -14,169.66 |
| USTECH100M | 108 | -0.2703 | -14,596.43 |
| XAUUSD | 79 | -0.03109 | -1,227.94 |


## Walk-forward (4-year train, 1-year test, x1)

| test_start | test_end | chosen | trades | exp_R | net |
|---|---|---|---|---|---|
| 2008-01-01 | 2009-01-01 | {'N': 50, 'over': 0.25, 'target_R': 3, 'stop_buffer': 0} | 65 | -0.1458 | -4,739.80 |
| 2009-01-01 | 2010-01-01 | {'N': 50, 'over': 0.25, 'target_R': 3, 'stop_buffer': 0} | 79 | -0.1944 | -7,679.36 |
| 2010-01-01 | 2011-01-01 | {'N': 50, 'over': 0.5, 'target_R': 3, 'stop_buffer': 0} | 114 | -0.0375 | -2,139.28 |
| 2011-01-01 | 2012-01-01 | {'N': 50, 'over': 0.5, 'target_R': 3, 'stop_buffer': 0} | 95 | 0.0925 | 4,395.30 |
| 2012-01-01 | 2013-01-01 | {'N': 50, 'over': 0.5, 'target_R': 3, 'stop_buffer': 0} | 104 | -0.2072 | -10,775.17 |
| 2013-01-01 | 2014-01-01 | {'N': 50, 'over': 0.5, 'target_R': 2, 'stop_buffer': 0} | 164 | -0.2694 | -22,094.47 |
| 2014-01-01 | 2015-01-01 | {'N': 20, 'over': 0.5, 'target_R': 3, 'stop_buffer': 0} | 232 | -0.4471 | -51,862 |
| 2015-01-01 | 2016-01-01 | {'N': 20, 'over': 0.5, 'target_R': 2, 'stop_buffer': 0} | 203 | 0.0357 | 3,619.45 |
| 2016-01-01 | 2017-01-01 | {'N': 20, 'over': 0.5, 'target_R': 2, 'stop_buffer': 0} | 204 | -0.2358 | -24,052.99 |
| 2017-01-01 | 2018-01-01 | {'N': 20, 'over': 0.5, 'target_R': 2, 'stop_buffer': 0} | 241 | -0.303 | -36,515.86 |
| 2018-01-01 | 2019-01-01 | {'N': 20, 'over': 0.5, 'target_R': 2, 'stop_buffer': 0} | 219 | -0.1662 | -18,203.57 |
| 2019-01-01 | 2020-01-01 | {'N': 20, 'over': 0.5, 'target_R': 3, 'stop_buffer': 0} | 197 | -0.0807 | -7,949.58 |
| 2020-01-01 | 2021-01-01 | {'N': 20, 'over': 0.5, 'target_R': 3, 'stop_buffer': 0} | 215 | -0.2326 | -25,006.05 |
| 2021-01-01 | 2022-01-01 | {'N': 20, 'over': 0.5, 'target_R': 3, 'stop_buffer': 0} | 244 | -0.1255 | -15,307.67 |
| 2022-01-01 | 2023-01-01 | {'N': 20, 'over': 0.5, 'target_R': 3, 'stop_buffer': 0} | 243 | -0.1168 | -14,187.63 |
| 2023-01-01 | 2024-01-01 | {'N': 20, 'over': 0.5, 'target_R': 3, 'stop_buffer': 0} | 268 | -0.205 | -27,471.46 |
| 2024-01-01 | 2025-01-01 | {'N': 50, 'over': 0.5, 'target_R': 3, 'stop_buffer': 0} | 147 | -0.3587 | -26,367.03 |
| 2025-01-01 | 2026-01-01 | {'N': 50, 'over': 0.5, 'target_R': 3, 'stop_buffer': 0} | 181 | 0.0959 | 8,678.56 |
| 2026-01-01 | 2026-10-02 | {'N': 50, 'over': 0.5, 'target_R': 3, 'stop_buffer': 0} | 102 | -0.2291 | -11,684.52 |


## Plateau (validate expectancy, x1)

| params | exp_R |
|---|---|
| {'N': 15, 'over': 0.5, 'target_R': 3, 'stop_buffer': 0} | -0.1622 |
| {'N': 25, 'over': 0.5, 'target_R': 3, 'stop_buffer': 0} | -0.1894 |
| {'N': 20, 'over': 0.375, 'target_R': 3, 'stop_buffer': 0} | -0.1912 |
| {'N': 20, 'over': 0.625, 'target_R': 3, 'stop_buffer': 0} | -0.1727 |


## All combinations (discovery columns used for the choice)

| N | over | target_R | stop_buffer | is_trades | is_exp_R | is_pf | is_net |
|---|---|---|---|---|---|---|---|
| 20 | 0.25 | 2 | 0 | 1,823 | -0.2312 | 0.705 | -210,750.61 |
| 20 | 0.25 | 3 | 0 | 1,762 | -0.1988 | 0.766 | -175,120.22 |
| 20 | 0.5 | 2 | 0 | 2,303 | -0.1818 | 0.761 | -209,371.50 |
| 20 | 0.5 | 3 | 0 | 2,212 | -0.1657 | 0.802 | -183,237.10 |
| 50 | 0.25 | 2 | 0 | 1,064 | -0.2597 | 0.673 | -138,135.22 |
| 50 | 0.25 | 3 | 0 | 1,043 | -0.247 | 0.714 | -128,810.77 |
| 50 | 0.5 | 2 | 0 | 1,401 | -0.1963 | 0.744 | -137,523.26 |
| 50 | 0.5 | 3 | 0 | 1,365 | -0.2054 | 0.757 | -140,180.85 |


## Information only: same rule and parameters on H4 bars (2019-2026)

| costs | trades | exp_R | net_pct |
|---|---|---|---|
| x0 | 4358 | -0.0347 | -75.65 |
| x1 | 4358 | -0.178 | -387.83 |
| x2 | 4358 | -0.3212 | -700 |

## Notes

- Rules, periods and gates: `bots/edge/protocol.md` (committed before this run).
- Costs: spread + slippage + swap (indices/gold 5%/yr, FX 2%/yr, Wednesday x3).
- FOMC dates: `data/events.csv`, written from memory (official pages unreachable), so one-day errors are possible.
