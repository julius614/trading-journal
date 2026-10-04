# TradingAgents — multi-agent debate layer

Repo: https://github.com/TauricResearch/TradingAgents (Apache-2.0). An LLM "trading firm":

```
Analysts (fundamentals · sentiment · news · technical)
      → Researchers: bull vs bear structured debate
      → Trader: proposes a decision
      → Risk management + Portfolio manager: assess risk, approve or reject (veto)
```

## Install
```
git clone https://github.com/TauricResearch/TradingAgents.git
cd TradingAgents
python -m venv .venv && .venv\Scripts\Activate.ps1      # (README uses conda, python 3.13)
pip install .
```
Docker alternative: `cp .env.example .env` then `docker compose run --rm tradingagents`.

## Keys (in `.env`, one LLM provider is enough)
`ANTHROPIC_API_KEY` or `OPENAI_API_KEY` / `GOOGLE_API_KEY` / `XAI_API_KEY` /
`DEEPSEEK_API_KEY` / `GROQ_API_KEY` / `OLLAMA_BASE_URL` (local models). Optional data:
`FRED_API_KEY`, `ALPHA_VANTAGE_API_KEY`.

## Run
CLI:
```
tradingagents                                                    # interactive
tradingagents --ticker NVDA --date 2026-09-23 --save --no-show   # non-interactive
```
Python:
```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "anthropic"      # provider and model names: see the repo README
config["max_debate_rounds"] = 2
ta = TradingAgentsGraph(debug=True, config=config)
state, decision = ta.propagate("NVDA", "2026-09-01")
ta.save_reports(state, "NVDA")
```
Tickers follow Yahoo Finance (`AAPL`, `SPY`, `0700.HK`, `7203.T`, `BTC-USD`). Data comes
from SEC EDGAR, Yahoo Finance, FRED, news and social feeds — it is built for **stocks/ETFs
and crypto**, not for MT5 FX/CFD symbols or this repo's intraday bots.

## Cost and reliability
- Each run makes many LLM calls (four analysts, multi-round debate, trader, risk team):
  real API cost and minutes per ticker. Confirm with the user before batch runs.
- Output is an LLM judgement on one date. The project itself says it is for research and
  "not intended as financial, investment, or trading advice".
- Never present a decision as a validated signal. To test it: fix the rules that produced
  it (or record decisions over many dates *without changing anything*) and score them
  forward or on pre-declared out-of-sample dates with costs — see `validation-gate.md`.

## Reading the result
Summarise: the four analyst views in one line each; the strongest bull and bear points;
the trader's call; whether risk management / the portfolio manager approved or vetoed, and
why. Flag any data the agents lacked.
