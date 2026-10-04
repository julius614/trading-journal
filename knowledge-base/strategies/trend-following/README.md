# Daily Trend-Following Across Many Markets — pre-declared test

- **Source:** the user's choice (option 2) after the intraday race failed (2026-10-05).
- **Code:** [`bots/trend/research/trend.py`](../../../bots/trend/research/trend.py).
- **Status:** rules committed **before** any data was downloaded. No results yet.
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
*(to be filled in after the user's data is downloaded and the test is run once)*
