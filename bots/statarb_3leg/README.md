# Triangular Stat-Arb Bot — EURUSD / GBPUSD / EURGBP (MetaTrader 5)

Market-neutral mean reversion on the currency triangle. When EURGBP drifts away from the
EURGBP implied by EURUSD/GBPUSD, sell the rich side and buy the cheap side across all three
legs, then close when the gap reverts.

> **Read this first: the fee gate will reject almost every signal.** The triangle is held
> together by arbitrage, so on M5 closes the gap is usually 0.1–0.5 EURGBP pips, while a
> 3-leg round trip on a raw account costs about 2.7 pips. With the 2.5× rule, a trade
> needs a gap of about 6.7 pips. On realistic synthetic data: 284 signals, **0 passed**.
> The gate is doing its job — it stops the bot paying spreads for an edge that isn't
> there. **Measure your broker's real data with the backtest before expecting trades.**
> Education, not financial advice; demo first.

## Layout
| File | Role |
|---|---|
| `config.py` | `StrategyConfig`, `FilterConfig`, `RiskConfig`, `BrokerConfig`; `.env` loading |
| `kalman_statarb.py` | Log spread, synthetic EURGBP, adaptive local-level Kalman filter, Z-score |
| `fee_gate.py` | 3-leg cost vs expected reversion, in EURGBP-pip equivalents; currency conversion |
| `risk_manager.py` | Dollar-neutral 3-leg sizing, Prop Shield breaker, rollover pause, news calendar |
| `data_fetcher.py` | Aligned M5 closes for the three pairs, live ticks, CSV loading (incl. MT5 spreads) |
| `execution.py` | Broker interface + MT5 adapter (shared with `amd_fx`), paper broker, basket executor with rollback |
| `main.py` | Async event loop (`--live` MT5, `--paper` replay) |
| `backtest.py` | Replay three CSVs; P&L plus a deviation-vs-cost report |
| `tests/` | 38 tests: Kalman, fee gate, position balancer, signals/end-to-end |

## The maths
- **Spread:** `s = ln(EURGBP) − ln(EURUSD / GBPUSD)` (0 when the triangle is consistent).
- **Kalman (local level):** mean follows a random walk (variance Q), the spread = mean +
  noise (variance R).
  - **R** is estimated online: the average during warm-up, then an exponentially weighted
    average with a 288-bar half-life. Outliers beyond 4σ are clipped for this update only.
  - **Q** = `q_ratio` × R (1e-4, i.e. the mean adapts over about 100 bars).
- **Z-score:** `Z = (s − mean_pred) / √(P_pred + R)`, using the *predicted* mean and the
  forecast-error variance.
  - P (state variance) alone would be wrong: it measures uncertainty about the mean and
    shrinks towards 0, which would inflate Z without limit.
  - No Z-score is produced for the first 288 bars (warm-up).
- **Fee gate:**
  - Expected reversion = |s − mean| × EURGBP / 0.0001 pips.
  - Cost = each leg's spread × its size + commission per lot, priced in the account
    currency and divided by the value of one EURGBP pip on the position.
  - A trade needs expected reversion / cost ≥ 2.5.
  - The spec's plain sum of leg pips would mix currencies (a GBPUSD pip ≠ a EURGBP pip in
    money). Converting each cost first makes the ratio exact.
  - Any leg with a spread > 3 pips is also rejected.

## Trading rules
| Item | Rule |
|---|---|
| Entry | Z < −2 → **long spread**: BUY EURGBP, SELL EURUSD, BUY GBPUSD. Z > +2 → **short spread** (mirror). Fee gate must pass. |
| Exit | Z back to within ±0.1 of zero (or crossed it) → close all three legs |
| Emergency exits (added) | Z widens 2 points past the entry Z (`stop_z_extra`); held 288 bars (`max_hold_bars`). Set to `None` to disable. |
| Sizing | EURGBP **N** lots, EURUSD **N** lots, GBPUSD **N × EURGBP** lots. N = `notional_equity_mult` × equity in EUR ÷ 100,000, rounded down. EUR exposure cancels exactly, GBP to lot rounding, and USD is left with only the spread itself (~0). |
| Prop Shield | Equity (realized + floating) down 2% from day start → close all legs, no entries until 00:00 UTC |
| News | No new entries 15 min before or after high-impact USD/EUR/GBP events from your calendar CSV |
| Rollover | No new entries 21:50–22:15 UTC |
| Execution | Legs are sent in order; if one fails, filled legs are closed immediately (**rollback**). Failed closes are retried; a stuck leg is logged as CRITICAL. The open basket is saved to `data/statarb_3leg/basket_state.json`. |

## Setup and run (from the repo root)
```powershell
pip install -r bots/statarb_3leg/requirements.txt
pytest -q bots/statarb_3leg/tests            # 38 passed
```

### 1. Download history, including EURGBP (MT5 open)
```powershell
$env:MT5_SERVER_TIMEZONE="ny_close"
python -m bots.amd_fx.download_history --symbols EURUSD GBPUSD EURGBP --timeframe M5 --bars 300000
```
The CSVs include MT5's historical spreads, which the replay uses.

### 2. Backtest — check whether the gate ever passes on your broker
```powershell
python -m bots.statarb_3leg.backtest EURUSD=data/amd_fx/EURUSD_M5.csv GBPUSD=data/amd_fx/GBPUSD_M5.csv EURGBP=data/amd_fx/EURGBP_M5.csv --commission 7 --out baskets.csv
```
The key lines are "How big are triangle deviations?" and "median edge … vs median cost".

### 3. Live on a demo account
1. Copy `bots/statarb_3leg/.env.example` to `.env` in the repo root and fill it in.
2. Create a news calendar CSV for the coming week, in the format of
   `news_calendar.example.csv` (UTC times). Live mode won't start without a calendar
   that's current.
3. `python -m bots.statarb_3leg.main --live`

It warms the filter up on the last 600 bars, then trades on each new M5 bar. Stop with
Ctrl+C. The three legs have no broker-side stops, so a stopped bot leaves an open basket
unmanaged until you restart it (the basket is recovered from the state file).

## Limits
- Paper fills use bar closes and a spread per bar or per symbol; there's no partial fill
  or latency model. Real triangle dislocations that last seconds are invisible on M5 bars.
- The news calendar has to be supplied (no live feed is built in).
- The account currency must be USD, EUR or GBP.
