# Trading Knowledge Base

Study notes on trading education material, organised by topic. Each entry records
its source, how it was captured, and the key takeaways I can apply in my trading.

## Index

| Topic | Source | Notes |
|---|---|---|
| AI for Trading | [QuantInsti — AI for Trading: How It Works, Uses, Risks, and Skills Guide](https://www.quantinsti.com/articles/ai-for-trading/) | [ai-for-trading/README.md](ai-for-trading/README.md) |
| Quantitative Trader | [QuantInsti — Quant Trader Role: Skills, Salary & Career Path Guide](https://www.quantinsti.com/articles/quantitative-trader/) | [quantitative-trader/README.md](quantitative-trader/README.md) |
| Quantitative Developer | [QuantInsti — Quantitative Developer Guide: Salary, Roadmap, Tools & Career Tips](https://www.quantinsti.com/articles/quantitative-developer/) | [quantitative-developer/README.md](quantitative-developer/README.md) |
| EPAT (course) | [QuantInsti — Executive Programme in Algorithmic Trading](https://www.quantinsti.com/epat) | [epat/README.md](epat/README.md) |

## Tools
- **AI trading stack skill** (`.claude/skills/ai-trading-stack/`): OpenBB data, 63 investor
  lenses (investorskills), TradingAgents bull/bear debate, Vibe-Trading backtests/brokers. Every
  idea from it still goes through the validation gate (`references/validation-gate.md`).

## Learning knowledge base (paste data, Claude learns)

- **Memory:** [LESSONS.md](LESSONS.md) holds everything learned, with evidence levels.
  Claude reads it at the start of every session.
- **Contents:** [INDEX.md](INDEX.md).
- **How to add:** paste anything in the chat and say "learn this", or drop files in
  [`inbox/`](../inbox/README.md).
- **Where things are filed:**
  - [notes/](notes/README.md) for articles, videos and books;
  - [ideas/](ideas/README.md) for strategy cards;
  - [my-trading/](my-trading/README.md) for your own trades;
  - `data/user/` for price data.
- **The workflow** is the `kb-learn` skill
  ([`.claude/skills/kb-learn/SKILL.md`](../.claude/skills/kb-learn/SKILL.md)).

## Strategies

| Strategy | Source | Notes | Code |
|---|---|---|---|
| 15-min ORB "the MAX way" | Max Options Trading (YouTube) | [strategies/orb-15min-max/README.md](strategies/orb-15min-max/README.md) | [strategies/orb_15min/](../strategies/orb_15min/) |
| AMD session liquidity sweep (FX bot) | User spec (ICT-style AMD) | [strategies/amd-session-sweep/README.md](strategies/amd-session-sweep/README.md) | [bots/amd_fx/](../bots/amd_fx/) |
| Triangular stat-arb (EURUSD/GBPUSD/EURGBP) — retired | User spec | [strategies/statarb-triangle/README.md](strategies/statarb-triangle/README.md) | git commit `e5b753f` |
| Pairs trading AUDUSD/NZDUSD & EURUSD/GBPUSD (H1, Kalman hedge ratio) — shelved: real but slow (~1%/yr) | User spec | [strategies/pairs-eurusd-gbpusd/README.md](strategies/pairs-eurusd-gbpusd/README.md) | [bots/statarb_3leg/](../bots/statarb_3leg/) — prop-firm plan: [prop-firm-plan.md](strategies/pairs-eurusd-gbpusd/prop-firm-plan.md) |
| Intraday momentum race: noise area, late half hour, 5-min ORB (indices, gold, oil, FX; M5, flat nightly) — run once: nothing passed (gross edge < costs) | Zarattini et al. 2023/2024; Gao et al. 2018; Baltussen et al. 2021 | [strategies/intraday-momentum/README.md](strategies/intraday-momentum/README.md) | [bots/intraday/](../bots/intraday/) |
| Daily trend-following, many markets (TS 12-month momentum, 50/200 MA, Donchian 50/25) — run once: nothing passed (gross Sharpe ~0.4, eaten by costs) | Moskowitz, Ooi & Pedersen 2012; Hurst, Ooi & Pedersen 2017 | [strategies/trend-following/README.md](strategies/trend-following/README.md) | [bots/trend/](../bots/trend/) |
| BACKTEST_SPEC 10 day-trading setups (ORB, intraday momentum, news days, VWAP, London/Tokyo/ECB fixes, round numbers, liquidity sweep) — run once: 0 of 10 passed, 2 not testable | Denis's BACKTEST_SPEC.md | [strategies/backtest-spec-10/README.md](strategies/backtest-spec-10/README.md) | [bots/spec10/](../bots/spec10/), reports in [reports/](../reports/COMPARISON.md) |
| Edge search: calendar sleeve (turn of month + pre-FOMC) and daily sweep reversal — run once: both failed (calendar ≈ market drift) | McConnell & Xu 2008; Lucca & Moench 2015; own S9 result | [strategies/edge-search/README.md](strategies/edge-search/README.md) | [bots/edge/](../bots/edge/), reports in [reports/edge/](../reports/edge/SUMMARY.md) |

## Conventions

- One folder per topic, with a `README.md` holding the study notes.
- Each note starts with a **Source & capture** block saying where the content came from
  and whether it was read in full or reconstructed from excerpts.
- Each note ends with **Self-check questions** and **Applying it to my journal**.

## Skill

All of these notes are packaged as the `quant-trading-mentor` Claude Code skill in
[`.claude/skills/quant-trading-mentor/SKILL.md`](../.claude/skills/quant-trading-mentor/SKILL.md).
It reviews strategies and journal trades, builds study plans, and answers quant career
questions using this knowledge base.
