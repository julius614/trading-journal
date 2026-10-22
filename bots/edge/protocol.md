# Edge search: low-turnover strategies (pre-declared, 2026-10-22)

This protocol was written and committed **before** any of these rules were run on data;
the git history shows the order. Nothing below may be changed after seeing results. A
change made later must be listed under "Amendments", with its reason, and is reported as
post-hoc.

## Why these ideas
Our 22 earlier tests share one pattern. Intraday setups often have a small edge before
costs, but trading often with tight stops pays more in spread and slippage than the edge
earns. So the candidates here meet three conditions:
- they trade rarely;
- they hold for days, so the move is large next to the spread;
- they have a published cause.

Holding overnight is allowed (user's decision, 2026-10-22). This costs swap, which is
modelled below.

## Candidates (parameters fixed)

**C1. Calendar sleeve.** One portfolio, judged as a whole. It has two parts.

**TOM: turn-of-the-month, long only.** Source: McConnell & Xu 2008; Lakonishok & Smidt 1988.
- Markets: US500, USTECH100M, US30, UK100 (D1, `data/trend`).
- Trading days are the bar dates in each market's own data.
- Entry: buy at the close of the 2nd-to-last trading day of each month.
- Exit: sell at the close of the 3rd trading day of the next month.
- No stop. Notional is 0.25× equity per market, so 1× in total.

**FOMC: pre-FOMC drift, long only.** Source: Lucca & Moench 2015.
- Markets: US500, USTECH100M.
- Entry: buy at the close of the trading day before each scheduled FOMC statement date
  (`data/events.csv`).
- Exit: sell at the close of the statement day. The D1 close comes after the 14:00 ET
  statement, so the trade includes the announcement reaction.
- Notional is 0.5× equity per market.
- An information-only M5 version (2019+, 14:00 ET the day before → 13:55 ET on the
  statement day) is reported but not judged.

**C2. Swing liquidity-sweep reversal on D1.** This is the spec10 S9 rule (`strategies.s9`)
on daily bars.
- Markets: EURUSD, GBPUSD, USDJPY, AUDUSD, NZDUSD, USDCAD, USDCHF, XAUUSD, US500,
  USTECH100M, US30, UK100.
- Grid: N {20, 50} × over {0.25, 0.5} × target_R {2, 3}, with stop_buffer 0.
- Time stop: 24 bars. Sizing: 0.5% risk, with spec10 leverage caps (10× FX and gold,
  4× indices).
- **Data-inspired:** S9 showed a gross edge on 2019–2026 intraday data. On D1, only data
  before 2019 is untouched.

**C2-info. Same as C2 on H4 bars built from M5 (2019–2026).** Reported for information
only; it cannot pass.

## Costs (every result at ×0, ×1, ×2)
- **Spread:**
  - FX: the spec10 `fx_costs` (0.8 pip EURUSD / 1.2 pip others, 3.5 USD per 100k per side
    commission, 0.2 pip slippage).
  - Indices and gold: the market's median non-zero D1 spread, plus half a spread of
    slippage per market fill.
- **Financing (swap)** on every 21:00 UTC weekday rollover the position is held through:
  - Wednesday counts ×3;
  - indices and gold: 5%/yr of notional; FX: 2%/yr of notional;
  - charged long or short (conservative).

## Periods
- **C1:** discovery 2012-08 → 2018-12, validate 2019 → 2022, hold-out 2023 → 2026-09.
- **C2:** discovery 2004 → 2016, validate 2017 → 2021, hold-out 2022 → 2026-09.
  - The combination is chosen by discovery expectancy (R, costs ×1, at least 30 trades).

## Gates
- **JOIN:** discovery expectancy > 0 at costs ×1.
- **KEEP:** validate expectancy > 0 at costs ×1.
- **PASS: all of these on the hold-out, run once.**
  - (a) expectancy > 0 at ×1 AND ≥ 0 at ×2.
  - (b) beats the **99th** percentile of 100 random runs.
    - C1: random dates. Same number of trades, same holding length, long, random entry
      days in the same period and markets. This asks whether these days are better than
      random days.
    - C2: the same trades with random direction (spec10 `random_entry_totals`).
  - (c) at least 100 hold-out trades. For C1, TOM and FOMC trades are pooled.
  - (d) walk-forward:
    - C1 has no parameters, so its calendar years in validate + hold-out must be positive
      in more than half.
    - C2: rolling 4-year train / 1-year test, positive in more than half of the test
      windows.
  - (e) plateau check, which never re-picks parameters:
    - C1: TOM shifted by one day (entry 3rd-to-last or last day, exit 2nd or 4th day);
      validate + hold-out expectancy at ×1 must stay > 0 for at least 3 of the 4 shifts.
    - C2: N and over each ×0.75 and ×1.25 around the chosen values; validate expectancy at
      ×1 must stay > 0 for at least 3 of the 4.

## If something passes
- Combine it with the AUD/NZD pairs bot's daily P&L (`bots/statarb_3leg/portfolio.py`).
- Report correlation and prop-firm odds (`odds_table`).
- Then run 6–8 weeks of demo, following the pairs `demo-runbook.md`.

No live or prop money is used without the user's explicit decision.

## Amendments
(none)
