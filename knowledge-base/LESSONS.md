# LESSONS: what this knowledge base has learned

This is the knowledge base's long-term memory. Claude reads this file at the start of
every session and before answering any trading question. Each lesson is short and has an
evidence level and a link to its source. When new material agrees with a lesson, it is
added as support; when it contradicts one, both views are kept and marked **CONFLICT**
until a test settles it. Lessons are never deleted; if one is overturned, it is struck
through with the reason.

**Evidence levels** (strongest first):
- **TESTED:** our own pre-declared backtest with costs and a hold-out.
- **RESEARCH:** a peer-reviewed paper or large-data study.
- **USER:** your own trades and experience.
- **CLAIM:** an article, video or opinion that has not been tested.

## Costs and edge
- **TESTED.** Intraday setups often have a small edge before costs; spread and slippage
  usually erase it. This held across 3 runs: [intraday race](strategies/intraday-momentum/README.md),
  [spec10](strategies/backtest-spec-10/README.md) and [edge search](strategies/edge-search/README.md).
- **TESTED.** Tight stops make costs a large share of the risk. The S9 sweep reversal had
  +0.12 R per trade before costs on H1, and costs were about 0.25 R per trade
  ([spec10](strategies/backtest-spec-10/README.md)).
- **TESTED.** Index CFDs cost about 4–5× more than the ETFs (SPY/QQQ). A strategy that
  needs ETF-level costs will not survive on CFDs.
- **TESTED.** Holding for days adds swap (financing) costs. Both daily trend-following and
  the D1 sweep reversal lost money after spread and swap
  ([trend](strategies/trend-following/README.md), [edge](strategies/edge-search/README.md)).

## What worked / what didn't (24 setups tested by 2026-10-22)
- **TESTED.** The only reliable setup is the AUD/NZD pairs bot (H1, Kalman hedge ratio).
  It makes about 1–2% a year with PF 1.38 and trades about 0.35 times a week. It is running
  on the demo account ([pairs](strategies/pairs-eurusd-gbpusd/README.md)).
- **TESTED.** These setups had no edge after costs:
  - ICT/AMD session liquidity sweeps;
  - the triangle stat-arb;
  - 5-min/15-min ORB;
  - noise-area momentum and late-half-hour momentum;
  - VWAP trend;
  - the London, Tokyo and ECB fix reversals;
  - round-number fade and break;
  - liquidity-sweep reversals on M15, H1, H4 and D1;
  - daily trend-following;
  - the turn-of-month calendar.
- **TESTED.** Round numbers: after the first touch of a level, price broke through slightly
  more often than it reversed (EURUSD 335 vs 292, GBPUSD 662 vs 610). Neither direction was
  tradable after costs.
- **TESTED, but only a weak signal.** Pre-FOMC drift (long US500/US100 from 14:00 ET the
  day before to 13:55 ET on Fed day) gave +0.15 R per trade after costs over 119 trades
  from 2019–26. The sample is small, and the dates come from memory. Watch it; do not trade
  it yet.

## How to judge any idea
- **TESTED.** A long-only idea in a rising market will look good. Always compare it with
  being long on random days. The turn-of-month calendar earned the same as random days.
- **TESTED.** Rules must be fixed before the data is seen, the hold-out used once, costs
  doubled as a check, and there must be at least 100 trades. Fewer than 50 trades is noise.
- **TESTED.** "Beats random" is meaningless if the strategy still loses money, because the
  random trades pay the same costs.

## Prop firms
- **TESTED.** A typical challenge (+10% target, −10% max, −5% daily) needs an edge that is
  both steady and big enough. The pairs bot alone passes too slowly
  ([prop-firm plan](strategies/pairs-eurusd-gbpusd/prop-firm-plan.md)).

## Data and tools
- The MetaQuotes-Demo history is capped at about 100k M5 bars (about 1.5 years). Long
  history comes from HistData (`bots/intraday/research/histdata.py`).
- The MT5 server time is "ny_close" (UTC+2 in winter, UTC+3 in summer). Always convert to
  UTC.
- Tools to add knowledge:
  - `bots/kb/trades.py` exports and analyses your trades;
  - `bots/kb/prices.py` checks and files price CSVs;
  - test engines: `bots/spec10`, `bots/edge`.

## Market knowledge (from notes)
_(empty: lessons from pasted articles, videos and books will appear here, each with a link
to its note in `notes/`)_

## My trading (from my own trades)
_(empty: lessons from `my-trading/` reports will appear here)_

## Open questions to test
- Pre-FOMC drift with verified dates and more history.
- A larger multi-pair version of the pairs bot (more pairs means more trades at the same
  edge).
