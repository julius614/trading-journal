# Comparison - BACKTEST_SPEC.md setups

Out-of-sample = last 30% of dates, touched once. Each setup's parameters were chosen on the first 70% only. PASS = OOS expectancy > 0 at costs x1 AND beats the 95th percentile of 100 random-entry runs.


| Strategy | OOS trades | OOS expectancy (R) @ x1 | OOS expectancy (R) @ x2 | IS expectancy (R) @ x1 | Sharpe @ x1 | Max DD % | Beats random 95%? | Verdict |
|---|---|---|---|---|---|---|---|---|
| S1B_orb_index | 1098 | -0.0632 | -0.1322 | -0.0706 | -0.687 | -40.14 | no | FAIL |
| S2_intraday_momentum | 500 | -0.0771 | -0.1128 | -0.0219 | -2.041 | -20.43 | no | FAIL |
| S3_news_momentum | 36 | 0.1401 | 0.1043 | 0.0315 | 0.703 | -1.23 | no | FAIL |
| S4_vwap_trend | 2494 | -0.0265 | -0.0627 | -0.0147 | -0.594 | -46.04 | no | FAIL |
| S5_london_fix | 37 | -0.0047 | -0.0417 | 0.0499 | -0.055 | -0.98 | no | FAIL |
| S6_tokyo_ecb_fix | 1195 | -0.0176 | -0.0544 | -0.0364 | -1.228 | -11.74 | yes | FAIL |
| S7_round_fade | 362 | -0.0679 | -0.1378 | -0.0648 | -0.889 | -17.25 | no | FAIL |
| S8_round_break | 143 | -0.1173 | -0.2032 | -0.1075 | -1.151 | -10.05 | no | FAIL |
| S9_sweep_M15 | 1939 | -0.2397 | -0.5402 | -0.2653 | -4.175 | -229.71 | yes | FAIL |
| S9_sweep_H1 | 457 | -0.1339 | -0.3882 | -0.1646 | -1.135 | -34.87 | yes | FAIL |
| S1_orb_stocks_in_play | - | - | - | - | - | - | - | NOT TESTABLE |
| S10_liquidity_provision | - | - | - | - | - | - | - | NOT TESTABLE |


'Beats random' alone is not enough: random entries pay the same costs, so a losing setup can still beat a worse-losing random baseline. Max DD is measured on non-compounded equity (100,000 + cumulative P&L), so it can exceed -100% when a setup loses more than the starting equity over the test.


## Not testable with our data

- **S1_orb_stocks_in_play**: needs 1-minute + daily data for the full US stock universe including delisted stocks; we only have index CFDs.
- **S10_liquidity_provision**: needs order-book (Level 2) data and queue modelling; the spec itself says 1-minute bars cannot test it honestly.


## Correlation of daily returns

0 setup(s) passed, so there is nothing to combine.


## Round numbers: reverse or break? (S7 vs S8)

Dates where both chosen versions traded the same pair: 318. Fade (S7) total -108.0 R, mean -0.340 R/day; break (S8) total -48.0 R, mean -0.151 R/day (costs x1).


Model-free check - first touch of a round level each day (07:00-17:00 London): did price go 20 pips THROUGH (break) or 20 pips BACK (reverse) first, within 2 hours?

| symbol | break | reverse | undecided |
|---|---|---|---|
| EURUSD | 335 | 292 | 552 |
| GBPUSD | 662 | 610 | 390 |


## Data notes

- Data: M5 bars only (no 1-minute bars, no bid/ask quotes). Fills use M5 bar opens and highs/lows; stop-before-target is assumed whenever one bar covers both.
- Long history 2019-2026: HistData M5 until 2025, then the MetaQuotes-Demo broker feed (data/intraday_hd). Short history (~1.5 years, 2025-2026, broker only): USDJPY, AUDUSD, US30 - reported separately as an extra check, low confidence.
- US500 / USTECH100M are broker index CFDs used as stand-ins for SPY / QQQ, not the ETFs. Their costs are the broker's own bar spread (median where unknown) plus half a spread of slippage per market/stop fill; no commission; 4x leverage cap. That is roughly 3-4 basis points per round trip - about 4-5x the spec's ETF costs (~0.8 bp on SPY), so for the ETFs themselves the truth would sit between the x0 and x1 columns.
- FX costs are the spec defaults (0.8 pip EURUSD / 1.2 pip others spread, 0.2 pip slippage on market/stop fills, 3.5 USD per 100k per side) - not real bid/ask around the fixes.
- These markets/years overlap earlier tests in this repo, so this is not a fully fresh sample; the out-of-sample part (last 30% of dates) was touched once, here.
- 1R = 0.5% of the 100,000 starting equity (500) for every setup, including the ones without a stop (1x notional), so R is comparable. No compounding.
