# Daily Trend-Following Across Many Markets — pre-declared test

- **Source:** the user's choice (option 2) after the intraday race failed (2026-10-05).
- **Code:** [`bots/trend/research/trend.py`](../../../bots/trend/research/trend.py).
- **Status (2026-10-05):** run once. **Nothing passed**; the gross edge was smaller than costs (see Results).
- **Holding:** days to weeks, including nights and weekends. On a prop firm this needs an
  account that allows weekend holding, e.g. **FTMO Swing**. It is *not* the intraday-only
  style chosen earlier.

## Why trend-following
- **It's the best-documented systematic edge** across asset classes. It shows up over
  more than 100 years and dozens of futures markets (Moskowitz, Ooi & Pedersen 2012,
  "Time Series Momentum"; Hurst, Ooi & Pedersen 2017, "A Century of Evidence on
  Trend-Following").
- **It needs many markets.** One market alone is mostly noise, so the test judges each
  rule on the **whole portfolio**, never picking the markets that happened to work.
- **The known weakness:** long flat or losing stretches (e.g. 2012–2013, 2016, 2023), and
  modest Sharpe ratios (about 0.5–1.0 historically, before costs). Passing a 10% target
  quickly is not its nature; the test measures how quickly it could.

## Rules (fixed)

| ID | Rule |
|---|---|
| TS | Long if the last 252-day return is positive, short if negative |
| MA | Long if the 50-day average is above the 200-day, else short |
| DC | Donchian: long on a close above the prior 50-day high, exit below the prior 25-day low; short mirrored |
| ALL | Equal mix of TS, MA and DC |

- **Timing:** signals are taken at the daily close and held over the next day.
- **Sizing:** 10% annual volatility per market (60-day EWMA), positions capped at 5×.
  The portfolio is the average across markets.
- **Costs:**
  - spread and slippage on every position change, using the broker's daily spread;
  - **2% a year financing** (CFD swaps) on the position held.

## Protocol
- **Universe:** every downloaded market with at least 5 years of daily bars. At least 8
  markets are needed.
- **Split:** discovery 60%, validate 20%, hold-out 20%.
- **Join:** discovery Sharpe ≥ 0.4, and still profitable with doubled costs.
- **Keep:** validate Sharpe ≥ 0.2.
- **"Strong":** the same as the intraday race. On validate + hold-out days only, at a scale
  with under 2% risk of a −5% day and at most 15% risk of failing, the chance of +10%
  within 12 months must be at least 50%. No single year or market may earn more than half
  the profit.
- **Also reported:** the 3-month pass chance.

## Results
**Run once on 2026-10-05**, on the user's MT5 daily bars:
- **19 markets:** 13 FX pairs, gold, silver, WTI, US500, US30, Nasdaq and UK100.
- **History:** mostly 2005–2026. US indices start in 2012, Nasdaq and UK100 in 2020.
- **Split:** discovery to 2017-10, validate to 2022-04, hold-out to 2026-10.

| Candidate | Discovery Sharpe | Validate Sharpe | Hold-out Sharpe | Discovery %/yr |
|---|---|---|---|---|
| TS | 0.06 | −0.40 | −0.12 | +0.25% |
| MA | 0.08 | −0.54 | −0.47 | +0.38% |
| DC | −0.09 | −0.56 | −0.79 | −0.39% |
| ALL | 0.13 | −0.43 | −0.39 | +0.51% |

**Verdict: nothing joined, so nothing was kept, and no strategy is strong.**

**Diagnostic, before vs after costs** (whole history, not part of the verdict):

| Candidate | Gross %/yr | Costs %/yr | Gross Sharpe | Net Sharpe |
|---|---|---|---|---|
| TS | +1.96% | 2.27% | 0.44 | −0.07 |
| MA | +1.53% | 2.15% | 0.34 | −0.14 |
| DC | +0.40% | 1.68% | 0.09 | −0.31 |
| ALL | +1.30% | 1.55% | 0.35 | −0.07 |

- **The trend effect is there** (TS gross Sharpe 0.44), roughly what the literature shows
  for 2005–2026, a weak era for trend-following.
- **Costs, mostly the assumed 2%/yr financing on positions held, take it all.**
- **By market (TS gross Sharpe):**
  - Gold 0.55, Nasdaq 0.53, silver 0.51, UK100 0.44 and GBPJPY 0.44 were best.
  - Most USD FX pairs were about zero or negative.
- **Even before costs, the return is ~2%/yr at 10% volatility per market:** nowhere near
  a fast challenge pass.

**Possible follow-up (would be a new pre-declared test):** a metals + indices-only trend
book, with real per-symbol swap rates instead of a flat 2%. It would be judged on new
data, since these markets' history has now been seen.
