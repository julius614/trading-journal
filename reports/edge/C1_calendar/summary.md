# C1 - Calendar sleeve: turn-of-the-month + pre-FOMC drift (long indices)

## Verdict: **FAIL**

Hold-out (2023-01-01 on): 188 trades, expectancy 0.1138 R at x1 and 0.0704 R at x2; net 10,695 USD vs random-dates 99th percentile 32,222 USD (median 10,257).


## Gates (pre-declared)

| gate | passed |
|---|---|
| JOIN discovery exp>0 @x1 | NO |
| KEEP validate exp>0 @x1 | yes |
| (a) hold-out exp>0 @x1 and >=0 @x2 | yes |
| (b) beats random-dates 99th pct | NO |
| (c) >= 100 hold-out trades | yes |
| (d) > half of years 2019+ positive | yes |
| (e) plateau: >= 3 of 4 TOM shifts positive | yes |


## Results by period, costs x0 / x1 / x2

| metric | discovery x0 | discovery x1 | discovery x2 | validate x0 | validate x1 | validate x2 | hold-out x0 | hold-out x1 | hold-out x2 |
|---|---|---|---|---|---|---|---|---|---|
| trades | 205 | 205 | 205 | 180 | 180 | 180 | 188 | 188 | 188 |
| win_rate | 0.507 | 0.483 | 0.459 | 0.594 | 0.567 | 0.556 | 0.553 | 0.521 | 0.516 |
| expectancy_R | -0.0188 | -0.0652 | -0.1116 | 0.1508 | 0.1072 | 0.0636 | 0.1572 | 0.1138 | 0.0704 |
| profit_factor | 0.936 | 0.794 | 0.673 | 1.337 | 1.23 | 1.131 | 1.474 | 1.325 | 1.191 |
| net | -1,924.44 | -6,682.74 | -11,441.03 | 13,574.27 | 9,647.49 | 5,720.71 | 14,772.18 | 10,695.37 | 6,618.55 |
| net_pct | -1.92 | -6.68 | -11.44 | 13.57 | 9.65 | 5.72 | 14.77 | 10.7 | 6.62 |
| cagr | -0.31 | -1.08 | -1.9 | 3.29 | 2.37 | 1.42 | 3.87 | 2.84 | 1.78 |
| sharpe | -0.142 | -0.384 | -0.622 | 0.535 | 0.394 | 0.251 | 0.665 | 0.488 | 0.305 |
| max_dd_pct | -6.03 | -9.88 | -13.96 | -6.12 | -6.7 | -7.28 | -8.07 | -8.85 | -9.64 |
| longest_losing_streak | 8 | 8 | 8 | 5 | 6 | 6 | 11 | 12 | 12 |
| top5_share | nan | nan | nan | 0.604 | 0.839 | 1.396 | 0.516 | 0.685 | 1.089 |


## By part and market (costs x1)

| part | market | discovery trades | discovery exp_R | validate trades | validate exp_R | hold-out trades | hold-out exp_R |
|---|---|---|---|---|---|---|---|
| TOM | US30 | 77 | -0.0701 | 48 | 0.0606 | 43 | 0.161 |
| TOM | US500 | 77 | -0.0617 | 48 | 0.08 | 43 | 0.1673 |
| TOM | USTECH100M | 0 | nan | 31 | 0.0104 | 44 | 0.1421 |
| FOMC | US500 | 51 | -0.0631 | 33 | 0.1019 | 29 | -0.1171 |
| FOMC | USTECH100M | 0 | nan | 20 | 0.4431 | 29 | 0.1524 |


## Calendar years 2019+ (net USD, costs x1)

| year | net |
|---|---|
| 2019 | -2,158 |
| 2020 | 7,986 |
| 2021 | 2,169 |
| 2022 | 2,549 |
| 2023 | 6,168 |
| 2024 | -3,493 |
| 2025 | 3,963 |
| 2026 | 3,159 |


## Plateau: TOM shifted one day (validate + hold-out expectancy, x1)

| entry (from month end) | exit (trading day) | exp_R |
|---|---|---|
| 3 | 3 | 0.1763 |
| 1 | 3 | 0.1152 |
| 2 | 2 | 0.1081 |
| 2 | 4 | 0.1037 |


## Buy-and-hold over the hold-out (1x, for scale)

| market | buy_and_hold_holdout_pct |
|---|---|
| US500 | 100.60 |
| US30 | 53.8 |
| USTECH100M | 181.20 |


Random-dates null: being long on random days of the same hold-out earned a median 10,257 USD, about the same as the sleeve - so in this sample the calendar days added little beyond the market's general rise.


The sleeve is in the market about 25% of days (TOM about 5 of 21 days, plus FOMC days), so it should be compared with buy-and-hold per day held, not in total.


## Information only: pre-FOMC drift on M5, 14:00 ET day before -> 13:55 ET (2019-2026, US500 + USTECH100M, 0.5x each)

| costs | trades | exp_R | win_rate | net_pct |
|---|---|---|---|---|
| x0 | 119 | 0.1982 | 0.613 | 11.79 |
| x1 | 119 | 0.1512 | 0.58 | 9 |
| x2 | 119 | 0.1041 | 0.555 | 6.2 |

## Notes

- Rules, periods and gates: `bots/edge/protocol.md` (committed before this run).
- Costs: spread + slippage + swap (indices/gold 5%/yr, FX 2%/yr, Wednesday x3).
- FOMC dates: `data/events.csv`, written from memory (official pages unreachable), so one-day errors are possible.
