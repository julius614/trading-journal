# Validation gate — how an idea earns real money in this repo

Every idea from the stack (a lens verdict, a TradingAgents decision, a Vibe-Trading backtest,
a YouTube strategy) goes through the same steps. They exist because most ideas fail.

## Base rate in this repo (2026-10)
12 strategies tested honestly → **1 reliable** (AUD/NZD pairs, ~1–2 %/yr, slow), 4 small and
unreliable, 7 lost money after costs. Details: `knowledge-base/README.md` (Strategies table).

## The steps
1. **Write fixed rules** — entry, exit, stop, sizing, markets, costs — from the source
   (paper, lens, video) without looking at results.
2. **Commit them before running on data** (git history proves the order). Pre-declare the
   pass/fail thresholds too.
3. **Real costs**: the broker's own spreads (MT5 `spread` column, by hour), slippage, FX
   commission, swaps for multi-day holds; a doubled-cost check must still be positive.
4. **Split by time**: discovery 60 % → validate 20 % → hold-out 20 % reported once.
   Judge portfolios, not hand-picked markets.
5. **Prop-firm odds**: bootstrap the daily P&L (`bots/statarb_3leg/portfolio.py`:
   `bootstrap_paths`, `challenge_odds`) — chance of +10 % before −10 % / −5 % day, within
   3 and 12 months.
6. **Plateau check**: ±25 % on each parameter must not break it (check only, never re-pick).
7. **Demo/paper 6–8 weeks**, comparing every trade with the backtest
   (`knowledge-base/strategies/pairs-eurusd-gbpusd/demo-runbook.md`).
8. Only then discuss a prop trial or live money — with the user's explicit decision.

## Tools already in the repo
| Tool | Path |
|---|---|
| MT5 history download (M5…D1, date chunks, broker specs) | `bots/amd_fx/download_history.py` |
| Long M5 history (HistData / Dukascopy) with broker spreads | `bots/intraday/research/histdata.py`, `dukascopy.py` |
| Intraday race (pre-declared, costs, odds, plateau) | `bots/intraday/research/protocol.py` |
| Break-even cost table (post-hoc diagnostic) | `bots/intraday/research/costs.py` |
| Daily trend-following test | `bots/trend/research/trend.py` |
| Pairs bot backtest / tuning / portfolio odds | `bots/statarb_3leg/backtest.py`, `tune.py`, `portfolio.py` |
| Live/demo bot with `--check` preflight | `bots/statarb_3leg/main.py` |

## Red flags that mean "not proven"
Tuned after seeing results; no costs or only spread; one market or one lucky year; fewer
than ~100 trades; no hold-out; "win rate 70 %" with no average win/loss; an LLM or lens
saying "buy" with no test.
