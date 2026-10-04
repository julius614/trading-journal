# Pairs-Trading Bot — AUDUSD vs NZDUSD (default) or EURUSD vs GBPUSD, H1 (MetaTrader 5)

> **Status: SHELVED (2026-10-04).** It works but is too slow for a prop challenge. See
> section 8 of the strategy note and `prop-firm-plan.md`. The code is kept unchanged for
> later use.

Two-leg statistical arbitrage: a Kalman filter tracks a moving hedge ratio between two
USD-quoted pairs. When one leg is unusually cheap compared with the other, buy it and sell
the hedge, then close when the gap closes.

> The folder is still called `statarb_3leg` so existing commands keep working. The original
> **3-leg EURUSD/GBPUSD/EURGBP triangle** version is in git history (commit `e5b753f`). It
> found no tradeable edge: M5 triangle gaps were far smaller than 3-leg costs (see
> `knowledge-base/strategies/statarb-triangle/`).
>
> **Latest results (2026-10-03), default rules (48-bar time stop, cointegration gate off),
> broker H1 data, raw-account costs ($7/lot):**
> - **AUDUSD/NZDUSD, Sep 2018 – Oct 2026 (out-of-sample for the 48-bar rule):** 145 trades,
>   **+$825 (+8.2%)**, PF 1.38, 57% wins, avg win **+$37** / avg loss **−$35**, max drawdown
>   −4.8%, **7 of 9 years profitable**.
> - EURUSD/GBPUSD, OANDA 2014 – 2020: 125 trades, +$363 (+3.6%), PF 1.14, max DD −4.3%.
>
> - **Pre-declared tuning** (entry Z × time stop, tune 2018–22 / validate 2023–24 / hold-out
>   2025–26) **kept the defaults**: the tune-period winner (2.0, 96) failed validation and
>   lost $290 in the hold-out. The default was positive in all three periods, but the hold-out
>   was thin (+$49). Details in section 7 of the strategy note.
>
> - **Prop-firm workarounds** (section 8 of the strategy note, and
>   `knowledge-base/strategies/pairs-eurusd-gbpusd/prop-firm-plan.md`):
>   - Adding more pairs failed the pre-declared test; only AUD/NZD qualifies.
>   - Safe size is about 2×, which means roughly a 2% chance of reaching +10% within
>     12 months.
>   - Closing before the weekend removes about 70% of the profit.
>   - So it's a slow, no-time-limit FTMO (Swing) attempt at best.
>
> Promising, not proven: about 1% a year at 1× notional, roughly 1.8 standard errors from
> zero. Demo-trade before risking money. See
> `knowledge-base/strategies/pairs-eurusd-gbpusd/README.md`. Education, not financial advice.

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
| `tune.py` | Pre-declared grid (entry Z × time stop) with tune/validate/hold-out split and a fixed selection rule |
| `portfolio.py` | Pre-declared multi-pair test (6 USD pairs) and a prop-challenge pass-probability simulator |
| `tests/` | 73 tests: Kalman, cointegration, fee gate, position balancer, signals/end-to-end, tuning, portfolio, prop rules |

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
| Cointegration gate | **Off by default** (`use_coint_gate=False`). When on: over the last 250 H1 bars, Engle–Granger p < 0.05 AND residual half-life < 48 bars, otherwise no new entries. Disabled because it almost never passes (see below). |
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

## Why the cointegration gate is off
Over 250 H1 bars an Engle–Granger test at p < 0.05 almost never passes on FX pairs:

| Data | Signals checked | Passed | Trades with gate on | Result |
|---|---|---|---|---|
| EURUSD/GBPUSD 2014–2020 | 1,733 | 7 (median p 0.87) | 7 | +$72 (48-bar stop) |
| AUDUSD/NZDUSD 2018–2026 | — | — | 5 | −$2 (48-bar stop) |

Even on a synthetic pair built to revert with a 15-bar half-life, it passes only ~17% of
windows. 250 bars give the test little power, and fitting β in the same window makes
it stricter still. With the gate on, the bot hardly trades, and the trades it allows aren't
better. It stays in the code (`cointegration.py`, `use_coint_gate=True`). Choosing a looser
threshold now would be fitting to these results, so any new setting must be pre-declared
and tested on unseen data.

## Setup and run (from the repo root)
```powershell
pip install -r bots/statarb_3leg/requirements.txt
pytest -q bots/statarb_3leg/tests            # 73 passed
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
# prop-firm variants: --flat-weekend, --notional-mult 2, --risk-per-trade 0.005
python -m bots.statarb_3leg.portfolio --data-dir data/amd_fx       # all 6 pairs + challenge odds
```

### 3. Live on a demo account (only if the backtest justifies it)
1. Copy `bots/statarb_3leg/.env.example` to `.env` in the repo root and fill it in.
2. Create a current news calendar CSV (format: `news_calendar.example.csv`).
3. `python -m bots.statarb_3leg.main --live`

Each leg gets a wide **emergency stop** at the broker (250 pips; `STATARB_EMERGENCY_SL_PIPS`)
in case the PC or connection dies. If one leg disappears (its stop fired, or it was closed by
hand), the bot closes the other leg straight away. Everything else is managed by the bot.
An open basket is recovered from the state file after a restart.

### Prop-firm settings (`.env`)
| Variable | Default | Meaning |
|---|---|---|
| `STATARB_NOTIONAL_MULT` | 1.0 | Size. About 2.0 is the safe maximum for a 10% max-loss account |
| `STATARB_RISK_PER_TRADE` | off | Fixed-risk sizing instead (e.g. 0.005 = lose ~0.5% at the Z stop). Not backtested as a default |
| `STATARB_EMERGENCY_SL_PIPS` | 250 | Broker-side stop per leg; `off` to disable |
| `STATARB_FLAT_WEEKEND` | 0 | 1 = no entries from Friday 12:00 NY, close at 16:00 NY (costs ~70% of profit) |
| `STATARB_NEWS_EXIT_BUFFER_MIN` | off | e.g. 2 for FTMO funded: normal exits wait out the news window |

To trade a second pair, run a second copy with its own `STATARB_PAIR` and `STATARB_MAGIC`.
Both share the account's Prop Shield, but only AUD/NZD has passed testing so far.
