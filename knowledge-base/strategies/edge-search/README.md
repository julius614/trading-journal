# Edge search: low-turnover candidates (run once, 2026-10-22)

**Source & capture:** designed from our own test history plus published research:
- McConnell & Xu 2008 (turn of the month);
- Lucca & Moench 2015 (pre-FOMC drift);
- our spec10 S9 result (sweep reversal).

The protocol `bots/edge/protocol.md` was committed before the first run, together with one
amendment based only on data coverage.

## Candidates and results

| Candidate | Hold-out trades | Exp. R ×1 | Exp. R ×2 | Verdict | Why it failed |
|---|---|---|---|---|---|
| C1 Calendar: turn of month + pre-FOMC, long US indices (D1) | 188 | +0.114 | +0.070 | FAIL | Lost money in 2012–18 discovery; long on random days of the same period earned about the same (it is mostly the market's rise) |
| C2 Sweep reversal on daily bars, 11 markets | 1133 | -0.208 | -0.342 | FAIL | Negative even before costs (win rate 24% at 3R targets) |

Information only:
- **Pre-FOMC on M5, 2019–26:** 119 trades, +0.15 R at ×1. This is the drift the papers
  describe, but the sample is small and the dates are not verified.
- **Sweep reversal on H4:** -0.18 R.

## What we learned
- **The calendar sleeve made money in 2019–2026,** but so did being long on random days,
  because US indices doubled. The "edge" is the market's upward drift, not the calendar.
  Before 2019 it lost money.
- **The sweep-reversal gross edge seen on 2019–26 intraday data does not exist on daily
  bars.** It was likely noise.
- **Scoreboard after this round:** 24 setups tested; 1 reliable (AUD/NZD pairs). The one
  steady source of return in our data is owning equity indices over years (buy-and-hold).
  That is investing, not a trading edge, and it does not fit prop-firm rules.

## Self-check questions
1. Why is "beats random long days" the right test for a long-only calendar rule?
2. Why can a strategy look good in a rising market and still have no edge?

## Applying it to my journal
When a long-only idea looks good, compare it with simply holding the market for the same
number of days.
