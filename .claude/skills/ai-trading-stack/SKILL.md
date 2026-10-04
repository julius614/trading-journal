---
name: ai-trading-stack
description: Research-to-execution workflow built on four open-source projects — OpenBB (market and economic data, also an MCP server), questflowai/investorskills (63 investor "lenses" such as Buffett, Graham, Lynch, Soros, Druckenmiller, Dalio, Livermore, Icahn), TauricResearch/TradingAgents (analysts → bull/bear debate → trader → risk manager veto) and HKUDS/Vibe-Trading (18 brokers, cross-market backtests). Use when the user wants to pull market data, analyse a ticker or idea through famous investors' frameworks, run a multi-agent bull/bear debate, backtest or connect a broker with these tools, or asks about OpenBB, investor skills, TradingAgents or Vibe-Trading. Triggers on "OpenBB", "investor lens", "what would Buffett/Livermore/Soros think", "TradingAgents", "bull vs bear", "Vibe-Trading", "research a trade", "analyse ticker", "AI trading agent". Every idea still has to pass this repo's validation gate before money is risked.
---

# AI Trading Stack — data → judgment → debate → test → (confirmed) execution

Four layers, each from a different open-source project. **They produce data, opinions and
backtests — none of that is proof.** In this repo 12 strategies were tested honestly and
only 1 survived (see `references/validation-gate.md`), so every output from this stack is a
*hypothesis* until it passes the gate.

| Layer | Project | Use it for | Don't use it for | Reference |
|---|---|---|---|---|
| 1. Data | **OpenBB** (`pip install openbb`; MCP: `openbb-mcp`) | Prices (stocks, FX, indices, crypto), fundamentals, options chains, economy (FRED), news | Live order execution; tick-accurate intraday costs | [openbb.md](references/openbb.md) |
| 2. Judgment | **investorskills** (63 `SKILL.md` lenses) | Structured checklists: "does this pass Buffett's moat test / Livermore's breakout rules / Soros's reflexivity view?" | Treating a lens verdict as a signal; mixing lenses that don't fit the asset or horizon | [investor-lenses.md](references/investor-lenses.md) |
| 3. Debate | **TradingAgents** (multi-agent LLM) | A written bull vs bear case on one stock/ETF/crypto ticker for a date | MT5 FX/CFD bots; claiming its decisions are profitable without a test | [tradingagents.md](references/tradingagents.md) |
| 4. Test / execute | **Vibe-Trading** (`pip install vibe-trading-ai`) | Quick backtests across markets; broker connections (Alpaca, IBKR, Binance, …) with **paper or read-only first** | MetaTrader 5 (not supported — use this repo's bots); any live order without the user's explicit "yes" | [vibe-trading.md](references/vibe-trading.md) |
| Gate | **This repo** | Pre-declared rules, real costs, 60/20/20 split, prop-challenge odds, demo runbook | — | [validation-gate.md](references/validation-gate.md) |

## Hard rules
1. **No order without explicit confirmation.** Never place, modify or close a live or
   prop-firm order on your own; demo/paper first. Vibe-Trading's own y/N gate is a minimum,
   not a substitute for asking the user.
2. **Opinions are not evidence.** Investor-lens verdicts and TradingAgents decisions are
   inputs to a hypothesis. Before anything trades, turn it into fixed rules and run the
   gate in `references/validation-gate.md`. Say this plainly to the user.
3. **Cite the source of every claim** — which lens, which agent, which data provider and
   date. If data is missing or stale, say so; never fill gaps with guesses.
4. **Secrets stay in `.env`** (gitignored): LLM keys (`ANTHROPIC_API_KEY`,
   `OPENAI_API_KEY` …), `FRED_API_KEY`, broker credentials. Never print, commit or paste them.
5. **Prop-firm rules come first:** EA allowance, "arbitrage" bans, same-strategy rules,
   weekend/news restrictions (see `knowledge-base/strategies/pairs-eurusd-gbpusd/prop-firm-plan.md`).
6. **Costs and runtime:** a TradingAgents run makes many LLM calls (real money per ticker);
   tell the user before running it at scale.
7. Education and research, not financial advice.

## Workflow for "research this trade / ticker / idea"
1. **Frame**: asset, horizon (intraday / swing / position / long-term), and whether it will
   run on MT5 (FX/CFD bots in this repo) or a Vibe-Trading broker.
2. **Data (OpenBB)**: price history and the few facts the chosen lenses need
   (fundamentals for value lenses; trend/volume for trend lenses; macro series for macro
   lenses). Record provider and as-of date.
3. **Lenses (investorskills)**: pick **2–3 lenses that fit the asset and horizon** (table in
   `references/investor-lenses.md`), follow each skill's own Process and Output Format, and
   report where they **disagree** — disagreement is information.
4. **Debate (optional, stocks/crypto)**: run TradingAgents for the ticker/date; summarise the
   bull case, bear case, the trader's call and whether risk management vetoed it.
5. **Make it testable**: write the idea as fixed rules (entry, exit, stop, size, costs,
   markets) — no tuning after seeing results.
6. **Gate**: commit the rules, then test (Vibe-Trading backtest for a first look; this repo's
   protocol tools for the decision), demo/paper for weeks, and only then discuss live.

### Output template
```
## <Ticker/idea> — research note (as of <date>, data: <provider>)
**Data snapshot:** price/trend/valuation/macro facts used (with sources)
**Lens 1 – <name>:** verdict + the 2–3 checks that drove it
**Lens 2 – <name>:** …
**Where they disagree:** …
**Bull vs bear (TradingAgents, if run):** bull …; bear …; trader decision …; risk manager …
**Testable rule draft:** entry / exit / stop / size / markets / costs
**Gate plan:** what will be pre-declared, which data, pass criteria, demo length
**Status:** hypothesis — not tested. Not financial advice.
```

## Setup on this user's PC (Windows, PowerShell, repo at C:\Users\JULIUS\trading-journal)
- Use a separate virtual environment per tool so their dependencies don't clash with the
  MT5 bots: `python -m venv C:\venvs\openbb` then `C:\venvs\openbb\Scripts\Activate.ps1`.
- Windows Smart App Control has blocked new pandas builds before; if a DLL is blocked,
  install `pandas==2.2.3` in that environment.
- Keys go in a `.env` file next to where the tool runs; never in code or chat.
- Node.js is needed only for `npx skills add …` (investorskills); the skill files can also
  simply be copied into `.claude/skills/`.
