# Pairs Trading EURUSD vs GBPUSD (H1, Kalman hedge ratio) — Strategy Review

- **Source:** the user's pivot from the triangle (2026-10-03). **Code:** [`bots/statarb_3leg/`](../../../bots/statarb_3leg/).
- **Status:** built; tested on synthetic data (37 tests) and on **real OANDA H1 data,
  2014 – May 2020, with default settings and no tuning: −3.3%, PF 0.88.**

## 1. Hypothesis
EUR and GBP are both European currencies quoted against the same USD, so EURUSD and GBPUSD
share a common driver. When one moves unusually far from its usual relationship with the
other, part of the gap tends to close.
- **Who's on the other side:** flows that push one currency on its own news (ECB vs BoE).
- **Weak point:** the relationship is economic, not an arbitrage. It can break for weeks or
  months (Brexit vote 2016, BoE/ECB policy splits, 2020 Covid).

## 2. Real-data result (OANDA H1, 2014-01 to 2020-05, raw costs, defaults)
| | Value |
|---|---|
| Trades | 81 (about one a month); all 81 passed the fee gate |
| Edge vs cost | median 120 pips vs **1.4 pips** — costs are ~1% of the move |
| Win rate | 63% |
| Average win / loss | +$49 / **−$95** |
| Total | **−$330 (−3.3%)**, PF 0.88, max drawdown −10.8% |
| Hedge ratio β | 0.39 – 0.83 (median 0.52); fell from 0.81 to 0.40 over the period |
| By year | 2014 −76, 2015 −289, **2016 −485**, 2017 +75, **2018 +615**, 2019 +289, 2020 −460 |

**Where the money went**
| Exit | Trades | Total |
|---|---|---|
| Spread reverted (Z back to ~0) | 67 (51 win / 16 lose) | **+$1,970** |
| Time stop (240 bars, ~10 days) | 11 | **−$1,817** |
| Entry-relative Z stop | 2 | −$473 |
| Prop Shield | 1 | −$9 |

**Reading:** the mean reversion itself works — trades that revert make money, and costs are
negligible (the reason for pivoting from the triangle was correct). The losses come from a
few divergences that **don't** revert within 10 days, which wipe out dozens of small
wins. That's the classic pairs-trading failure: the relationship shifted (β fell by half
over 6 years).

## 3. How this backtest could lie
- [ ] **Regime breaks:** results swing by year; 6 years is only a handful of regimes.
- [ ] **Tuning temptation:** shortening the time stop or raising the entry Z could "fix"
      the 11 losers *in this data*. Any change must be chosen on 2014–2017 and confirmed once
      on 2018–2020 (and on the broker's 2025–2026 data), as in the AMD study.
- [ ] **Exit labelled "reverted" can still lose:** Z can return to 0 because the Kalman fair
      value moved towards the price, not because the price came back (16 such losers).
- [ ] **Fills:** H1 closes with fixed spreads; weekend gaps and news spikes are worse live.

## 4. Possible next research (pre-declare before testing)
1. **Time stop length** {48, 96, 240 bars} and **entry Z** {2.0, 2.5, 3.0} — small grid,
   tune 2014–2017, validate 2018–2020.
2. **Regime filter:** skip entries when β has moved sharply in the last N bars (relationship
   breaking).
3. **Other pairs** with tighter fundamentals: AUDUSD/NZDUSD (`STATARB_PAIR=AUDUSD,NZDUSD`).

## 5. Version 2 (2026-10-03): 48-bar time stop + rolling cointegration gate
New rules:
- **Time stop:** 48 H1 bars (was 240).
- **Entry gate:** no entries unless an Engle–Granger test over the last 250 bars gives
  p < 0.05 and the residual half-life is < 48 bars.
- **Default pair:** now AUDUSD/NZDUSD.

**Ablation sweep, OANDA EURUSD/GBPUSD H1 2014-01 → 2020-05, raw costs**
(`python -m bots.statarb_3leg.sweep …`)

| Variant | Trades | P&L | Win | Avg win / loss | PF | Max DD | Years + |
|---|---|---|---|---|---|---|---|
| Old: 240-bar stop, no gate | 81 | −$330 | 63% | +49 / −95 | 0.88 | −10.8% | 3/7 |
| **48-bar stop only** | **125** | **+$363** | 54% | +45 / **−47** | **1.14** | **−4.3%** | **5/7** |
| Gate only (240-bar stop) | 7 | −$130 | 57% | +47 / −106 | 0.59 | −2.5% | 3/6 |
| New: 48-bar stop + gate | 7 | +$72 | 57% | +37 / −26 | 1.94 | −0.4% | 4/6 |

**What it shows**
- **The 48-bar stop does what it was meant to:** average loss halves (−$95 → −$47),
  drawdown falls from −10.8% to −4.3%, and the result flips from −3.3% to +3.6%. But 104 of
  125 trades exit on the time stop, not by full reversion, so the edge is "partial
  reversion within 2 days".
- **The gate blocks almost everything on EUR/GBP:** 7 of 1,733 checks passed (median p 0.87).
  Over 250 H1 bars, EURUSD and GBPUSD are almost never cointegrated by Engle–Granger. Seven
  trades in 6 years can't be evaluated.
- **The gate is also weak on genuinely reverting data:** on a synthetic pair with a 15-bar
  half-life it passes only ~17% of windows. 250 bars give the test little power, so p < 0.05
  is a very strict bar.
- **In-sample caveat:** the 48-bar rule was chosen after seeing this data's 10-day-stop
  losses, so the +3.6% is not out-of-sample. Confirm on the broker's 2021–2026 H1 data
  and on AUDUSD/NZDUSD, which isn't in the public dataset (no NZDUSD), using the sweep
  on broker downloads.

## Self-check questions
1. Why is a positive win rate (63%) still a losing strategy here?
2. Why can a "reverted" exit lose money with a Kalman fair value?
3. Why did costs stop mattering when moving from the triangle (M5) to the pair (H1)?
