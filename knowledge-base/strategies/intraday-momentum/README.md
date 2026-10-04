# Intraday Momentum Race — indices, gold, oil, FX (M5, flat every night)

- **Source:** the user's request for a "strong" strategy after the pairs bot was shelved
  (2026-10-04).
- **Constraints the user chose:**
  - intraday only (no overnight or weekend risk, so it fits any prop account);
  - FX + gold + indices + oil.
- **Code:** [`bots/intraday/research/`](../../../bots/intraday/research/).
- **Status:** the protocol was committed **before** any data was downloaded. No results yet.

## 1. Why these three candidates
All three are documented in peer-reviewed or widely replicated research. Each has a
reason to exist (forced hedging and flows), and the parameters are fixed from the papers,
so there is nothing to curve-fit.

| ID | Idea | Source | Why it might work |
|---|---|---|---|
| **NA** | Trade breakouts of the "noise area" around the open, checked every 30 minutes, with a trailing VWAP/band stop | Zarattini, Aziz & Barbon (2024), *Beat the Market: An Effective Intraday Momentum Strategy for S&P500 ETF (SPY)* | Options dealers' gamma hedging and leveraged-ETF rebalancing push in the direction of the day's move |
| **LH** | The return from the previous close to 30 minutes after the open predicts the last 30 minutes | Gao, Han, Li & Zhou (2018, *Journal of Financial Economics*); Baltussen, Da, Lammers & Martens (2021, *JFE*): 60+ futures | Late-day hedging flows and slow-reacting traders |
| **OR** | Direction of the first 5-minute candle; stop 10% of ATR, target 10R | Zarattini, Barbon & Aziz (2023), *Can Day Trading Really Be Profitable?* | The control. Our earlier ORB note found it thin (≈0 after costs), so it must earn its place again |

## 2. Protocol (fixed before seeing data)
- **Sessions** (local time, DST handled automatically):
  - US indices, gold and oil: 09:30–16:00 New York.
  - GER40: 09:00–17:30 Frankfurt.
  - UK100: 08:00–16:30 London.
  - FX: 08:00–16:00 London.
  - Half days and broken days are dropped.
- **Which strategy runs where:**
  - NA: every symbol.
  - LH: US-session symbols only.
  - OR: every non-FX symbol.
- **Costs:**
  - The broker's own per-bar spread, plus slippage of half the median spread on each side.
  - FX also pays $7 per $100k.
  - A doubled-slippage version must also be profitable.
- **Sizing:** NA and LH target 1% daily volatility (14-day estimate, capped at 4×). OR
  risks 1% at its stop.
- **Split:** one calendar for all symbols. The first 60% is *discovery*, the next 20% is
  *validate*, and the last 20% is the *hold-out*, reported once.
- **Join:** at least 150 discovery trades, PF ≥ 1.15, and still profitable with doubled
  slippage.
- **Keep:** validate PF ≥ 1.05.
- **Portfolio:** an equal-weight average of the kept combinations.
- **"Strong" means all of these, on validate + hold-out days only:**
  - at the largest size with under a 2% chance of a −5% day and at most a 15% chance of
    failing, the chance of reaching +10% within 12 months is **at least 50%**;
  - no single year or single symbol earns more than half the profit. One lucky market or
    year isn't enough, so a single combination can never be "strong" alone.
- **Plateau check** (kept combinations only): each parameter is moved about 25%. Every
  variant must keep PF > 1. This is a check only; nothing is re-chosen from it.
- **If nothing qualifies,** the verdict says so and **no bot is built.**

### Data-source amendment (2026-10-04, before any strategy was run)
- **The problem:** the broker's MT5 server keeps only about 100,000 M5 bars, roughly 1.5
  years for most symbols. That is too short for a 60/20/20 split.
- **Prices:** these now come from **Dukascopy's free 1-minute BID candles** (UTC),
  resampled to M5, from 2019 on.
- **Costs:** still the **broker's own spreads**, as the median for each UTC hour of the
  week, measured from the broker's M5 data.
- **Price scale:** matched to the broker's prices. The median gap is printed and stored in
  each `_spec.json`.
- **Unchanged:** the rules, parameters and pass/fail thresholds.
- **New risk:** Dukascopy's index CFDs and your broker's can differ slightly at the open.
  The hold-out period can be re-checked on the broker's own 1.5 years.

## 3. How this test could still lie
- **History length:**
  - MT5 brokers often keep only 2–5 years of M5 data for CFDs.
  - A short hold-out (under a year) is weak evidence.
  - Record the dates in the results.
- **Spread data:** MT5's bar spread is usually the spread at bar close (or the minimum),
  so real fills at the open, near news or in fast markets will be worse. The
  doubled-slippage check partly covers this.
- **CFD vs futures/ETF:** the papers used SPY/QQQ/futures. A CFD's quotes and session
  (nearly 24h) differ, which is why we anchor to the cash session.
- **Multiple testing:** about 20 combinations are tested, so a few will pass discovery by
  luck. That is why validate and hold-out exist and why the bar is a portfolio, not one
  winner.
- **Crowding:** the NA paper (2024) is famous. Its edge may shrink after publication.

## 4. Results
*(to be filled in after the user's data is downloaded and the protocol is run once)*

## Self-check questions
1. Why is "strong" defined on validate + hold-out only, not on the full history?
2. Why can a single market never meet the "strong" definition here?
3. What does it mean if the plateau check breaks but validation passed?
