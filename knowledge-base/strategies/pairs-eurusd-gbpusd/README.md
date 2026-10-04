# Pairs Trading EURUSD vs GBPUSD (H1, Kalman hedge ratio) — Strategy Review

- **Source:** the user's pivot from the triangle (2026-10-03). **Code:** [`bots/statarb_3leg/`](../../../bots/statarb_3leg/).
- **Status: SHELVED (2026-10-04).** It's validated but slow: about +1%/yr at 1×, with
  about a 2% chance of passing a 10% challenge within 12 months at the safe 2× size
  (section 8, [prop-firm-plan.md](prop-firm-plan.md)). The code and settings are kept as
  they are. Possible later use: a slow FTMO Swing account, or a low-correlation second
  strategy next to a stronger one.
- **Earlier status (2026-10-03):** default pair is now AUDUSD/NZDUSD with a 48-bar time stop and
  the cointegration gate off. Out of sample on AUD/NZD 2018–2026: **+8.2%, PF 1.38, 7/9
  winning years** (section 6). The original 10-day-stop version lost 3.3% on EUR/GBP
  2014–2020 (section 2).

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

## 6. Out-of-sample test: AUDUSD vs NZDUSD (broker H1, Sep 2018 – Oct 2026)
The 48-bar stop was chosen from EUR/GBP results, so AUD/NZD is a genuine out-of-sample
test of it. Sweep (`python -m bots.statarb_3leg.sweep …`), raw costs, $7/lot:

| Variant | Trades | P&L | Win | Avg win / loss | PF | Max DD | Years + |
|---|---|---|---|---|---|---|---|
| Old: 240-bar stop, no gate | 97 | +$521 | 65% | +43 / −65 | 1.24 | −4.8% | 4/9 |
| **48-bar stop only** | **145** | **+$825 (+8.2%)** | 57% | **+37 / −35** | **1.38** | −4.8% | **7/9** |
| Gate only (240-bar stop) | 5 | −$204 | 40% | +36 / −92 | 0.26 | −2.5% | 1/4 |
| 48-bar stop + gate | 5 | −$2 | 40% | +43 / −30 | 0.97 | −0.8% | 1/4 |

**Conclusions (2026-10-03)**
1. **The 48-bar time stop held up out of sample.** It improved both pairs (EUR/GBP −3.3% →
   +3.6%; AUD/NZD +5.2% → +8.2%, 7/9 profitable years). Losses are now about the size of
   wins, so single divergences no longer erase many winners. Most exits (115/145) are the
   time stop: the edge is partial reversion within ~2 days.
2. **The cointegration gate is now off by default.** It blocked almost every trade on both
   pairs (5 and 7 trades in 6–8 years) without improving the ones it allowed. Re-tuning its
   threshold now would be fitting to these results.
3. **Strength of evidence:** about $5.70 per trade over 145 trades, roughly 1.8 standard
   errors from zero. Suggestive, not conclusive, and only about 1% a year at 1× notional
   (more size scales the drawdown too).
4. **Next:** demo-trade AUD/NZD with the defaults for a few months, compare live fills and
   spreads with the backtest, and keep size at 1× until they agree.

## 7. Pre-declared tuning (AUDUSD/NZDUSD, broker H1, 2018-09 → 2026-10)
Protocol in `bots/statarb_3leg/tune.py`, committed (`5012601`) **before** the data was pushed
(`6580de2`):
- **Grid:** entry Z {1.75, 2.0, 2.5} × time stop {24, 48, 96} bars.
- **Splits:** trades split by entry time into tune 2018–2022, validate 2023–2024, hold-out
  2025–2026.
- **Selection:** neighbour-median $/trade on the tune period, with ≥ 60 trades and PF > 1.
- **Acceptance:** the pick replaces the default only if it is profitable on validate with
  PF ≥ 1.1 and beats the default there.

| Entry Z | Hold | Tune trades | Tune P&L | Tune PF | Val trades | Val P&L | Val PF | Hold-out trades | Hold-out P&L | Hold-out PF |
|---|---|---|---|---|---|---|---|---|---|---|
| 1.75 | 24 | 174 | +245 | 1.12 | 65 | +195 | 1.33 | 73 | −157 | 0.83 |
| 1.75 | 48 | 121 | +283 | 1.15 | 48 | +312 | 1.66 | 49 | −82 | 0.90 |
| 1.75 | 96 | 95 | +561 | 1.31 | 39 | +79 | 1.11 | 36 | −230 | 0.74 |
| 2.00 | 24 | 109 | +105 | 1.08 | 35 | +145 | 1.53 | 47 | −25 | 0.96 |
| **2.00** | **48** | **82** | **+540** | **1.41** | **30** | **+236** | **1.84** | **33** | **+49** | **1.09** |
| 2.00 | 96 | 67 | +936 | 1.75 | 26 | +16 | 1.04 | 22 | −290 | 0.55 |
| 2.50 | 24 | 43 | −352 | 0.58 | 9 | +34 | 1.48 | 19 | +55 | 1.20 |
| 2.50 | 48 | 29 | −147 | 0.83 | 8 | +61 | 1.75 | 15 | +66 | 1.25 |
| 2.50 | 96 | 23 | +49 | 1.06 | 7 | +26 | 1.22 | 12 | +74 | 1.32 |

**Outcome:** the tune period picked **(2.0, 96)**. On validation it made only +$16 vs +$236 for
the default, so the rule **rejected it and kept the default (2.0, 48)**. Its hold-out
(−$290) confirms the rejection was right.

**What it means**
- **The default is the robust choice:** it's the only mid-grid setting that is positive in
  tune, validate and hold-out.
- **Longer holds fit 2018–2022 but fail afterwards** — exactly the overfitting the protocol
  exists to catch.
- **The recent period is weak:** 6 of 9 settings lost money in 2025–2026, and the default made
  only +$49 (PF 1.09). Expect a thin live edge.
- Entry Z 2.5 looks better recently but has very few trades (12–19) — too few to act on.
- **No parameter change.** Next step: demo-trade the defaults and compare with the backtest.

## 8. Prop-firm workarounds tested (2026-10-03)

The problem: about +1%/yr at 1× notional, so a 10% challenge target takes years. Four fixes
were tried. The protocols (`portfolio.py`, commit `158e813`) were committed before any of
them ran on the data.

### 8a. More pairs: failed
Pre-declared rule: a pair joins only if, on 2018–22, it has at least 40 trades and PF ≥ 1.1,
and it stays only if its 2023–24 PF is above 1.0. Figures are for $100k at 1×, using the
defaults.

| Pair | Tune P&L | Tune PF | Validate P&L | Validate PF | Hold-out P&L | Hold-out PF |
|---|---|---|---|---|---|---|
| EUR/GBP | −3,971 | 0.75 | +1,475 | 1.36 | −1,965 | 0.73 |
| EUR/AUD | −9,036 | 0.60 | +2,042 | 1.51 | −1,006 | 0.86 |
| EUR/NZD | −7,217 | 0.67 | +1,277 | 1.20 | −384 | 0.94 |
| GBP/AUD | +2,752 | 1.10 | +6,036 | 2.70 | +668 | 1.10 |
| GBP/NZD | −6,950 | 0.78 | +5,764 | 2.15 | +2,559 | 1.59 |
| **AUD/NZD** | **+5,215** | **1.37** | **+2,567** | **1.90** | **+468** | **1.08** |

- **Only AUD/NZD qualifies.** GBP/AUD missed PF 1.1 by 0.002 on the tune period, and the
  rule is not bent after the fact.
- Every pair did well in 2023–24, which shows why one good period proves nothing.
- GBP/NZD and GBP/AUD may be worth a **new** pre-declared test on future data. They
  can't be added now.

### 8b. Bigger size: limited by drawdown, not by the daily limit
Simulated challenge: 10,000 bootstrap paths, a target of +10%, failure at −10% overall or a
−5% day, and no time limit.

| Scale | Data | P(pass) | P(fail) | P(pass within 12 months) | Median time to pass |
|---|---|---|---|---|---|
| 2× | 2023–26 (out of sample) | 22% | 1% | 0.5% | 27 months |
| 3.5× | 2023–26 (out of sample) | 55% | 10% | 11% | 19 months |
| 2× | 2018–26 (all, in sample) | 38% | 7% | 2% | 24 months |
| 2.5× | 2018–26 (all, in sample) | 52% | 11% | 7% | 21 months |
| 3× | 2018–26 (all, in sample) | 57% | 29% | 14% | 18 months |

- The pre-declared rule picks **3.5×** on 2023–26. But that period has no shock like
  March 2020. Over the full history, max drawdown at 1× is −5.1% and the worst day is −1.9%,
  so 3× already fails 29% of the time.
- **Recommended: 2×** (`STATARB_NOTIONAL_MULT=2`). The two data sets are combined
  conservatively.
- **Bottom line: this bot cannot pass a 10% challenge quickly at a safe size.** At 2×, about
  98 in 100 tries would not pass within 12 months. Most simply wouldn't finish yet; few
  would fail.

### 8c. Flat before the weekend: too expensive
`--flat-weekend` blocks entries from Friday 12:00 NY and closes at 16:00 NY.

| | Trades | P&L | PF | Win rate |
|---|---|---|---|---|
| Normal (2018–26) | 145 | +$8,251 | 1.37 | 57% |
| Flat before weekend | 153 | +$2,570 | 1.12 | 48% |

It removes about 70% of the profit, because Friday positions get closed before they
revert. On a funded account, use the **FTMO Swing** account (weekend holding allowed), not
this flag.

### 8d. Emergency stop per leg
- A live-only broker stop at 250 pips per leg. Legs moved that far 3 times in 8 years
  (12 times at 150 pips, which is why the default is 250).
- If a stop (or a manual close) removes one leg, the bot now closes the other leg at once
  ("leg closed outside bot"), so the account isn't left with a one-sided position.

### 8e. Other additions
- **Fixed-risk sizing** (`STATARB_RISK_PER_TRADE`): sizes each trade so the Z stop loses
  about that fraction of equity. It is **not** part of the tested results above.
- **News exit buffer** (`STATARB_NEWS_EXIT_BUFFER_MIN=2`): normal exits wait out FTMO's
  2-minute news window. The Z stop and the Prop Shield never wait.

See [prop-firm-plan.md](prop-firm-plan.md) for what this means in practice.

## Self-check questions
1. Why is a positive win rate (63%) still a losing strategy here?
2. Why can a "reverted" exit lose money with a Kalman fair value?
3. Why did costs stop mattering when moving from the triangle (M5) to the pair (H1)?
