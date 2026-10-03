# Triangular Stat-Arb (EURUSD / GBPUSD / EURGBP) — Strategy Review

- **Source:** the user's spec (2026-10-03). **Code:** git history, commit `e5b753f` — the
  folder `bots/statarb_3leg/` now holds the 2-leg pairs version
  ([review](../pairs-eurusd-gbpusd/README.md)).
- **Status (2026-10-03):** measured on the user's broker data (May 2025 – Oct 2026). **No
  tradeable edge** — see section 5.

## 1. Hypothesis
EURGBP should equal EURUSD ÷ GBPUSD. If it drifts away, trade the gap back.
- **Who is on the other side:** whoever quoted the stale or out-of-line leg. In practice
  that's mostly banks' and HFT firms' pricing engines, which keep the triangle consistent
  within milliseconds.
- **Weak point:** this is one of the most heavily arbitraged relationships in finance.
  Gaps big enough to pay three spreads plus commissions are rare, short-lived (often under
  a second), and mostly captured by co-located HFT. On 5-minute closes, most of what looks
  like a gap is just bar-timing noise between the three pairs.

## 2. The cost hurdle (raw account)
| Item | EURGBP-pip equivalents |
|---|---|
| EURGBP spread 0.6 pip | 0.60 |
| EURUSD spread 0.2 pip (1 lot) | 0.16 |
| GBPUSD spread 0.5 pip (0.87 lots) | 0.34 |
| Commission $7/lot × 2.87 lots | 1.58 |
| **Total round trip** | **≈ 2.7 pips** |
| **Gap needed at 2.5×** | **≈ 6.7 pips** |

Synthetic check with 0.15-pip noise (typical M5 bar-timing noise): median gap 0.1 pips,
99.9th percentile 0.5 pips, and 284 signals with |Z| > 2 → **0 passed the gate**.

## 3. How this backtest could lie
- [ ] **Bar timing:** M5 closes of three pairs aren't simultaneous ticks. Apparent gaps can
      be pure timing artefacts that can't be traded. Check with tick or M1 data.
- [ ] **Stale quotes / bad ticks:** the largest "gaps" are often data errors or illiquid
      moments (rollover, news). Those are exactly when the gate might pass, and when fills
      are worst.
- [ ] **Fills:** the paper broker fills at the bar close. Live fills on three legs
      happen in sequence, with slippage on each.
- [ ] **Costs:** use your real spreads (the downloaded CSVs include them) and commissions.

## 4. Validation plan
1. Download EURUSD, GBPUSD and EURGBP M5 history (with spreads) from your broker.
2. Run the backtest and read the deviation report. If the 99.9th-percentile gap is far below
   the ~6.7-pip hurdle, stop: there is nothing to trade at this timeframe.
3. If some trades pass, inspect each one. Were they at rollover, at news, or on a single bad
   bar? Only gaps outside those count.
4. Need ≥ 100 baskets with positive net P&L across different months before even a demo test.

## 5. Real-data result (user's broker, M5, May 2025 – Oct 2026)
| | Value |
|---|---|
| Gap size (EURGBP pips) | median 0.18, p90 0.73, p99 4.3, p99.9 9.6, max 22.9 |
| Signals with \|Z\| > 2 | 4,466 (964 blocked by the rollover window) |
| Median edge vs cost | 2.24 vs **7.10 pips** (broker's real spreads; ratio 0.34, needed 2.5) |
| Baskets taken | 14, +$43.91 on $10,000, 86% wins, avg hold 4.3 bars |

**Where the 14 came from:** 11 opened at 21:00–21:40 UTC on days from March onwards — US
summer-time **rollover** (17:00 New York = 21:00 UTC), which the original fixed 21:50–22:15
UTC pause didn't cover. Rollover gaps come from frozen EURGBP quotes and blown-out spreads;
the backtest used MT5's recorded bar spread (~1.5 pips), but live rollover spreads are often
5–20+ pips, so those fills aren't real. Outside rollover: 3 trades, +$7.58 in 16 months.

**Fix:** the rollover pause now follows New York time (`rollover_anchor="ny_close"`). The
conclusion stands: in normal hours the triangle's M5 gaps are far smaller than 3-leg costs.

## Self-check questions
1. Why does Z use √(P + R) and not √P?
2. Why do the lot sizes N, N, N × EURGBP make EUR and GBP exposure cancel?
3. Why can a plain sum of three legs' spreads in pips be misleading?
4. Why are triangle dislocations usually invisible on M5 bars?
