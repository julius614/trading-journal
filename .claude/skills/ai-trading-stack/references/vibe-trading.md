# Vibe-Trading — backtest and broker layer

Repo: https://github.com/HKUDS/Vibe-Trading (MIT). An AI trading agent with market data,
backtesting, portfolio views and broker connectors; can also run as an MCP server (the
README mentions 74 tools over stdio — check the README/wiki at vibetrading.wiki for the
exact launch command and config).

## Install
```
pip install vibe-trading-ai
pip install -U vibe-trading-ai     # upgrade
```
LLM: OpenRouter by default; Claude, GPT and others via environment variables (see README).

## CLI basics
```
vibe-trading connector configure <broker> --yes   # set up a broker connection
vibe-trading connector account                    # balances
vibe-trading portfolio show | refresh | sources   # holdings
vibe-trading show <run_id>                        # results of a run
vibe-trading --swarm-retry <run_id>               # retry a failed run
```
Backtests and analysis are requested in natural language through the agent (the README
names the `backtest` tool but gives no standalone backtest CLI).

## Brokers and markets
- Brokers (README, v0.1.16, Sept 2026 — **18**, more than the "13" in older posts): Alpaca,
  Binance, Dhan, eToro, Futu, Interactive Brokers, Kraken, KIS, OKX, Robinhood, Scalable
  Capital, Shoonya, Toss Securities, Trading 212, Upbit, Zerodha Kite Connect, Nobitex,
  Wallex.
- Markets: US, UK (LSE), Hong Kong, China A-shares, Brazil, Vietnam equities; crypto, forex,
  options, metals, futures.
- **No MetaTrader 5 connector.** This user's prop-firm and FX/CFD work runs on MT5, so
  execution there stays with this repo's bots (`bots/statarb_3leg`, `bots/amd_fx`).

## Backtest notes
Market-specific rules (China T+1, stamp tax, price limits), options fill on the next bar,
perpetual funding every 8 hours. Treat a Vibe-Trading backtest as a first look; decisions
use the pre-declared protocol in `validation-gate.md` (fixed rules before data, real costs,
out-of-sample hold-out).

## Safety
- Live orders need explicit confirmation (Web UI y/N, CLI prompt, or an exact "confirm" in
  messaging). **Additionally, always ask the user in plain words before any live order.**
- Use paper / sandbox / read-only profiles first; paper support depends on the broker.
- Broker credentials stay in its connector store/keyring or `.env` — never in chat or git.
- The project warns that a token, an X account and a Virtuals project using its name are
  not official — ignore anything selling a "Vibe-Trading token".
