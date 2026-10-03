# AMD Session Liquidity Sweep — Strategy Review

## Source & capture
- **Source:** the user's own spec (2026-10-03): Asian-range liquidity sweep
  (Accumulation, Manipulation, Distribution) on EURUSD/GBPUSD, with a Kalman Z-score gate,
  a volatility-spike filter and "Prop Shield" risk rules. AMD is an ICT / "smart money"
  concept; no external source was used.
- **Code:** [`bots/amd_fx/`](../../../bots/amd_fx/) — the full rule table and run instructions
  are in its README.
- **Status (2026-10-03): tested on real data — no edge found.** See the
  [tuning report](tuning-report.md): 6.4 years of OANDA data plus the user's broker data;
  1,944 configurations; the best tuned versions lost money on unseen years. **Do not trade it.**

## 1. Hypothesis — why might this work?
- The Asian session is quiet, so its high and low collect **resting stop orders** (stops
  of range traders and breakout entries).
- At the London/New York open, larger players need liquidity. A fast push through the
  range triggers those stops (the **sweep**), and a quick close back inside suggests the
  push failed — **trapped breakout traders** must exit, which fuels the move back
  through the range (**distribution**).
- **Who is on the other side:** breakout traders and stopped-out range traders.
- **Weak points:** "stop hunts" are easy to see on a chart afterwards and hard to tell
  apart from real breakouts in real time. The edge may be small or absent; the Z-score
  and volatility filters exist to separate the two, and must prove they do.

## 2. Rules (summary)
Range 00:00–06:00 UTC → skip if > 2 × D1 ATR(14) → in 07:00–10:00 / 12:00–15:00, an
8–20-pip sweep beyond the range → a close back inside within 1–3 bars → Kalman
Z beyond ±1.5 during the sweep and a 3-vs-20-bar volatility spike → enter. SL 2.5 pips
beyond the extreme; 50% off at the Asian midpoint (then break-even +0.5 pip); the rest
at the opposite boundary. 1% risk, 2% daily breaker, max 2 trades, no entries at rollover.

## 3. Lifecycle fit
| Stage | In this strategy |
|---|---|
| Features | Asian high/low/mid, range vs. D1 ATR, sweep size, bars to displacement, Kalman Z, volatility ratio |
| Prediction | A failed breakout reverts through the range |
| Portfolio / risk | Fixed 1% risk; 2% daily stop; max 2 concurrent trades (EURUSD and GBPUSD are highly correlated — effectively one bet) |
| Execution | Market order after the M5 close; spread and slippage matter at 5–20-pip targets |

## 4. How this backtest could lie — checklist
- [ ] **Overfitting:** 10+ parameters (sweep 8/20, 1–3 bars, ±1.5 Z, 1.3× vol, 2× ATR,
      2.5-pip buffer, windows). Fix them **before** the test; change none after looking.
- [ ] **Look-ahead:** the range is final only at 06:00; entries use closed bars; ATR uses
      prior days; Z uses past bars. (The code does this — keep it that way.)
- [ ] **Costs:** targets are 5–20 pips, so 0.8–1.5 pips of spread plus commission is a big
      share. Replay with `--spread 1.0 --commission 7` and again with double costs.
- [ ] **Bar granularity:** M5 bars hide whether SL or TP came first; the replay assumes SL.
      Confirm with M1 data.
- [ ] **Reward-to-risk:** a full win in the textbook case is **+0.53R** against −1R. Check the
      real average win; the strategy needs a very high win rate.
- [ ] **Correlation:** EURUSD and GBPUSD sweeps often fire together — two "independent"
      trades can be one bet at 2% risk.
- [ ] **Regime and news:** split results by year, volatility and news days (NFP/CPI/FOMC).
- [ ] **Data snooping:** "smart money" setups are often chosen from charts after the fact;
      only a rule-based test counts.

## 5. Validation plan
1. Get **≥ 3 years of M1 or M5 data** for EURUSD and GBPUSD (broker export or Dukascopy).
2. Replay with the default config and realistic costs. Look at the setup funnel with
   `--log-level INFO`: how many sweeps → displacements → filter passes → trades.
3. Variants decided in advance: Z measured at sweep vs. displacement; filters on/off
   (do they add value?); TP2 only vs. the TP1/TP2 split.
4. In-sample: first 2 years. Out-of-sample: the rest, **run once**.
5. Pass only if out-of-sample: ≥ 150 trades, expectancy > +0.1R after costs, profit
   factor > 1.2, max drawdown < 10R, and it holds with doubled costs.
6. **Demo-trade for ≥ 1 month** (≥ 30 trades); compare demo fills and slippage with the replay.
7. Live at 0.25–0.5% risk for 50 trades before going to 1%.

## 6. Risk rules (already in the code)
1% per trade, 2% daily breaker on equity (realized + floating), max 2 trades, no entries
21:50–22:15 UTC, spread cap 2 pips, broker-side SL/TP on every leg.

## Self-check questions
1. Why does the code measure the Z-score during the sweep and not at the displacement bar?
2. What is the break-even win rate if a full win is +0.53R and a loss is −1R?
3. Why is the ATR gate on D1 and not M5?
4. Why might EURUSD and GBPUSD signals together count as one bet?
5. What would you check in the setup funnel if replays produce almost no trades?
