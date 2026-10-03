# Prop-firm plan for the AUD/NZD pairs bot

*Written 2026-10-03. Firm rules change, so re-read each firm's current rules before buying.*

## The honest summary
- The bot makes about **+1% a year at 1× size** (2018–2026 backtest, after costs).
- The safe maximum is about **2×**. Above that, a repeat of March 2020 would likely break
  the 10% max-loss limit.
- At 2×, the simulation gives about **38% to reach +10% eventually** and **about 2% to reach
  it within 12 months**. The median is about 2 years.
- Adding more pairs did not help: only AUD/NZD passed the pre-declared test.
- So **this bot is not a fast way to pass a challenge.** It can only make sense on a firm
  with **no time limit**, as a slow, low-risk attempt where the only cost is the one-time
  fee.

## Which firm

| | FTMO 2-Step | FundedNext Stellar 2-Step |
|---|---|---|
| EAs / bots | Allowed | Only on accounts **below $50k** |
| Time limit | None | None |
| Pairs trading | Not prohibited | "Arbitrage trading" is prohibited, so **ask support in writing first** |
| Weekend holding (funded) | Standard: no. **Swing: yes** | No |
| News (funded) | Standard: no orders ±2 min around high-impact news | Check current rules |
| Verdict | **Use this.** Swing account, 2× size | Only below $50k, and only after a written "yes" |

## Rules we will NOT work around
Breaking these risks losing the account and any profit:
- **No EA on FundedNext $50k+ accounts.** We won't run it and call it manual trading.
- **No "pass-only" settings.** No higher risk for the challenge and lower risk for funded.
  FundedNext requires the same strategy throughout, and it's the honest way anyway.
- **No copying trades across several accounts or firms** to multiply size, where a firm
  forbids it.
- **No hiding the bot.** If a firm asks what you trade, describe it plainly.

## Message to send FundedNext support before buying
> Hello. I plan to run my own Expert Advisor on a Stellar 2-Step account under $50k. It
> trades a statistical pairs strategy on AUDUSD and NZDUSD on the H1 chart. It opens two
> opposite positions when the price ratio moves far from its recent average, and it holds
> them for up to 48 hours. It does not use latency, price-feed, tick-scalping or
> cross-broker arbitrage, and it holds no hedges across accounts. Is this allowed under
> your "arbitrage trading" rule, on both the challenge and the funded account?

Keep their written answer (a screenshot or email).

## Settings for an FTMO trial or challenge (`.env`)
```
STATARB_PAIR=AUDUSD,NZDUSD
STATARB_NOTIONAL_MULT=2.0        # recommended maximum; 1.0 while on demo
STATARB_EMERGENCY_SL_PIPS=250    # broker-side stop per leg in case your PC goes offline
STATARB_FLAT_WEEKEND=0           # Swing account: keep 0. Standard funded account: 1 (costs ~70% of profit)
STATARB_NEWS_EXIT_BUFFER_MIN=2   # FTMO funded Standard 2-minute news rule
STATARB_NEWS_CSV=data/statarb_3leg/news_calendar.csv
```
The bot's own Prop Shield stops trading for the day at −2%, well inside FTMO's 5%.

## Order of steps
1. **Demo at 1× for 4–8 weeks.** Check that live fills and spreads match the backtest.
2. **FTMO Free Trial at 2×.** It runs the same rules with no money at stake.
3. **Pay for a challenge only if the demo matches.** Expect it to take many months.
