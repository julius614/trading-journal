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

## Strategies

| Strategy | Source | Notes | Code |
|---|---|---|---|
| 15-min ORB "the MAX way" | Max Options Trading (YouTube) | [strategies/orb-15min-max/README.md](strategies/orb-15min-max/README.md) | [strategies/orb_15min/](../strategies/orb_15min/) |
| AMD session liquidity sweep (FX bot) | User spec (ICT-style AMD) | [strategies/amd-session-sweep/README.md](strategies/amd-session-sweep/README.md) | [bots/amd_fx/](../bots/amd_fx/) |
| Triangular stat-arb (EURUSD/GBPUSD/EURGBP) — retired | User spec | [strategies/statarb-triangle/README.md](strategies/statarb-triangle/README.md) | git commit `e5b753f` |
| Pairs trading AUDUSD/NZDUSD & EURUSD/GBPUSD (H1, Kalman hedge ratio) — shelved: real but slow (~1%/yr) | User spec | [strategies/pairs-eurusd-gbpusd/README.md](strategies/pairs-eurusd-gbpusd/README.md) | [bots/statarb_3leg/](../bots/statarb_3leg/) — prop-firm plan: [prop-firm-plan.md](strategies/pairs-eurusd-gbpusd/prop-firm-plan.md) |
| Intraday momentum race: noise area, late half hour, 5-min ORB (indices, gold, oil, FX; M5, flat nightly) — protocol committed, awaiting data | Zarattini et al. 2023/2024; Gao et al. 2018; Baltussen et al. 2021 | [strategies/intraday-momentum/README.md](strategies/intraday-momentum/README.md) | [bots/intraday/](../bots/intraday/) |

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
