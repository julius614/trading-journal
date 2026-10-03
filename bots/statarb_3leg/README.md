# Pairs-Trading Bot — AUDUSD vs NZDUSD (default) or EURUSD vs GBPUSD, H1 (MetaTrader 5)

Two-leg statistical arbitrage: a Kalman filter tracks a moving hedge ratio between two
USD-quoted pairs. When one leg is unusually cheap compared with the other, buy it and sell
the hedge, then close when the gap closes.

> The folder is still called `statarb_3leg` so existing commands keep working. The original
> **3-leg EURUSD/GBPUSD/EURGBP triangle** version is in git history (commit `e5b753f`). It
> found no tradeable edge: M5 triangle gaps were far smaller than 3-leg costs (see
> `knowledge-base/strategies/statarb-triangle/`).
>
> **Real-data result for this version (OANDA H1 2014–2020, raw-account costs, default
> settings, no tuning): 81 trades, −3.3%, profit factor 0.88.** Costs are no longer the
> problem; spreads that don't revert are. See
> `knowledge-base/strategies/pairs-eurusd-gbpusd/README.md`. Education, not financial
> advice; demo first.

## Layout
| File | Role |
|---|---|
| `config.py` | `StrategyConfig` (H1 defaults), `FilterConfig`, `RiskConfig`, `BrokerConfig`; pair validation; `.env` loading |
| `kalman_statarb.py` | `KalmanHedgeRatio`: 2-state Kalman filter for y = β·x + α on log prices, Z-score |
| `cointegration.py` | Rolling Engle–Granger test (ADF on OLS residuals, MacKinnon p-values) and half-life — numpy only, matches statsmodels `coint` |
| `fee_gate.py` | 2-leg cost vs expected reversion in y-pip equivalents; generic USD-pair currency conversion |
| `risk_manager.py` | β-weighted 2-leg sizing, Prop Shield, NY-time rollover pause, news calendar |
| `data_fetcher.py` | Aligned closed bars for both legs, live ticks, CSV loading (incl. MT5 spreads) |
| `execution.py` | Broker interface + MT5 adapter (shared with `amd_fx`), paper broker, basket executor with rollback |
| `main.py` | `PairsBot` async loop (`--live` MT5, `--paper` replay) |
| `backtest.py` | Replay two CSVs (first = y leg); P&L, swings vs costs, gate stats, β path, P&L by year; `--max-hold`, `--no-coint-gate` |
| `sweep.py` | One-command ablation: old rules vs 48-bar stop vs gate vs both, same data and costs |
| `tests/` | 49 tests: Kalman, cointegration, fee gate, position balancer, signals/end-to-end |

## The model
- **Prices:** y = ln(EURUSD), x = ln(GBPUSD).
- **State:** [β, α], each following a random walk.
- **Filter step:**
  - `H = [x, 1]`
  - `P_pred = P + Q`
  - spread `e = y − H·θ`
  - `S = H·P_pred·Hᵀ + R`
  - **`Z = e / √S`**: the forecast-error variance, i.e. the √(P+R) form with P projected
    through H.
- **R** (observation noise) is estimated online: the average during warm-up, then a 500-bar
  half-life exponential average. Shocks beyond **4σ** are clipped for this update only, so
  one shock can't mute later signals.
- **Q** = diag(q_β, q_α) × R, with defaults 1e-4: the fair value adapts over about 100 H1 bars.
- **Warm-up:** 500 bars before any Z-score is produced.

## Trading rules
| Item | Rule |
|---|---|
| Entry | Z < −2 → **long spread**: BUY y (AUDUSD), SELL x (NZDUSD). Z > +2 → **short spread** (mirror). Cointegration gate and fee gate must pass. |
| Cointegration gate | Over the last **250 H1 bars**: Engle–Granger p-value **< 0.05** AND residual half-life **< 48 bars**. Otherwise no new entries (exits are unaffected). |
| Exit | Z back within ±0.1 of zero, or crossed it |
| Stop | **Entry-relative**: long exits if Z ≤ Z_entry − 2.0, short if Z ≥ Z_entry + 2.0 (`stop_z_extra`) |
| Time stop | **48 H1 bars** (~2 trading days; weekend hours don't count). Not reverted by then → close both legs. |
| Sizing | EURUSD notional = `notional_equity_mult` × equity. GBPUSD notional = β × that (both in USD), so lots = N and N·β·EURUSD/GBPUSD, rounded down. Long EUR / short GBP is the deliberate bet. |
| Fee gate | Expected reversion \|e\| × EURUSD notional vs both legs' spread cost + commission, in EURUSD-pip equivalents; needs ≥ 2.5×. Leg spread > 3 pips → reject. |
| Prop Shield | Equity (realized + floating) −2% from day start → close both legs, no entries until 00:00 UTC |
| News | No entries 15 min before or after high-impact USD/AUD/NZD/EUR/GBP events (calendar CSV) |
| Rollover | No entries 16:50–17:15 New York time (21:50–22:15 UTC in winter, 20:50–21:15 in summer) |
| Execution | Legs are sent in order; if the second fails, the first is closed immediately (rollback). Basket state is saved to `data/statarb_3leg/basket_state.json`. |

Pair: `STATARB_PAIR=AUDUSD,NZDUSD` (default) or `EURUSD,GBPUSD`; the backtest takes the pair
from its two `SYMBOL=CSV` arguments. Both legs must be quoted in USD, and the
account currency must be USD or one leg's base currency.

## Setup and run (from the repo root)
```powershell
pip install -r bots/statarb_3leg/requirements.txt
pytest -q bots/statarb_3leg/tests            # 49 passed
```

### 1. Download H1 history (MT5 open)
```powershell
$env:MT5_SERVER_TIMEZONE="ny_close"
python -m bots.amd_fx.download_history --symbols AUDUSD NZDUSD --timeframe H1 --bars 50000
```

### 2. Sweep (old vs new rules) and backtest
```powershell
python -m bots.statarb_3leg.sweep AUDUSD=data/amd_fx/AUDUSD_H1.csv NZDUSD=data/amd_fx/NZDUSD_H1.csv --commission 7
python -m bots.statarb_3leg.backtest AUDUSD=data/amd_fx/AUDUSD_H1.csv NZDUSD=data/amd_fx/NZDUSD_H1.csv --commission 7 --out baskets.csv
```

### 3. Live on a demo account (only if the backtest justifies it)
1. Copy `bots/statarb_3leg/.env.example` to `.env` in the repo root and fill it in.
2. Create a current news calendar CSV (format: `news_calendar.example.csv`).
3. `python -m bots.statarb_3leg.main --live`

The legs have no broker-side stops. If the bot is stopped, an open basket is unmanaged until
restart (it's recovered from the state file).
