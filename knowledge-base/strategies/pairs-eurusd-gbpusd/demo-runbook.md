# Demo runbook — AUD/NZD pairs bot on MT5

The goal of the demo is to check that **live trading behaves like the backtest**: same
kind of trades, similar costs, and no technical problems. It is *not* to make money.
Plan for 6–8 weeks.

## 1. One-time setup (PowerShell, in `C:\Users\JULIUS\trading-journal`)
1. Get the code: `git pull origin claude/gallant-faraday-r0l3ni`
2. Create the settings file: `notepad .env`
   - Click **Yes** if Notepad asks to create it.
   - Paste the block below, then save and close.

```
MT5_SERVER_TIMEZONE=ny_close
STATARB_PAIR=AUDUSD,NZDUSD
STATARB_ACCOUNT_CCY=EUR
STATARB_NOTIONAL_MULT=1.0
STATARB_COMMISSION_PER_LOT=7.0
STATARB_EMERGENCY_SL_PIPS=250
STATARB_FLAT_WEEKEND=0
STATARB_REQUIRE_NEWS_CALENDAR=0
```

Notes on these settings:
- **Login lines:** leave out `MT5_LOGIN` / `MT5_PASSWORD` / `MT5_SERVER`. The bot then
  uses whatever account MT5 is logged into, so log MT5 into the **demo**.
- **`STATARB_ACCOUNT_CCY`:** must match the account's currency (the demo is in EUR). The
  check command tells you if it's wrong.
- **`STATARB_REQUIRE_NEWS_CALENDAR=0`:** turns news blackouts off. That's acceptable for
  a demo only, and must be turned back on (with a news CSV) before any prop or real account.

## 2. Check before trading
`python -m bots.statarb_3leg.main --check`

It places **no orders**. It shows:
- the account, and whether it's a demo;
- prices and spreads for AUDUSD, NZDUSD and EURUSD;
- that the history loaded and the current Z-score;
- the lot sizes it *would* trade;
- the risk settings.

It must end with **READY**. If it says **NOT READY**, it lists exactly what to fix.

## 3. Start the bot
`python -m bots.statarb_3leg.main --live`
- **Leave the window open and the PC on.** Windows Settings > System > Power: set sleep
  to **Never**. MT5 must stay open and logged in, with **Algo Trading** switched on (the
  toolbar button shows green).
- **To stop:** press **Ctrl + C**. If a trade is open, it's saved, and the bot carries on
  managing it when restarted.
- **After a PC restart:** open MT5, then PowerShell, `cd C:\Users\JULIUS\trading-journal`,
  `$env:MT5_SERVER_TIMEZONE="ny_close"`, and start the bot again.
- **Logs:** `logs\statarb_3leg\bot.log`.

## 4. What to expect (from the 2018–2026 backtest at 1× size)
- **Trade frequency:** about **1–2 trades a month**, and some months none. Days or weeks
  of "nothing happening" are normal.
- **Each trade:** two positions at once, e.g. BUY ~1.6 lots AUDUSD and SELL ~1.4 lots
  NZDUSD (or the reverse). They open and close together.
- **Holding time:** at most **48 hours**. Most trades close on the time limit; some close
  early when the spread returns to normal ("reverted").
- **Results per trade:** wins ~57% of trades. The average win and the average loss are
  each about **0.35–0.4% of the account** (about €350–400 on €100k). The worst backtest
  trade was about −1.9%.
- **Over a month:** about 2 in 3 months with trades end positive. Expect small amounts,
  around +0.1% a month on average. This is a slow, low-risk strategy.

## 5. Weekly check-in
Once a week, send:
- the bot's **OPEN** and **CLOSE** lines: `Select-String -Path logs\statarb_3leg\bot.log -Pattern "OPEN|CLOSE|ERROR|CRITICAL"`;
- or a screenshot of MT5's **History** tab.

I compare each trade with what the backtest would have done: entry Z, holding time,
costs and slippage.

## 6. When is the demo "passed"? (after 6–8 weeks)
- No technical problems: no ERROR/CRITICAL lines, never a single leg left open, and it
  restarts cleanly.
- Fills and spreads are close to the backtest's (AUDUSD ~0.3 pip, NZDUSD ~0.7 pip on a raw
  account).
- Results are within the backtest's normal range. With only ~10 trades, P&L alone proves
  little, so behaviour matters more than profit.

Only then consider an FTMO Free Trial (Swing account, `STATARB_NOTIONAL_MULT` up to 2.0,
news calendar ON). See [prop-firm-plan.md](prop-firm-plan.md).
