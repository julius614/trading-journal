# AMD Session-Sweep FX Bot (MetaTrader 5)

Modular Python framework for the **Asian-range liquidity sweep** (Accumulation →
Manipulation → Distribution) on EURUSD/GBPUSD. It adds a Kalman-filter Z-score and a
volatility-spike filter, plus "Prop Shield" risk rules.

> **Demo first.** This is untested on real market data. Run the replay, then a demo
> account for weeks, before any live money. See the strategy review and validation plan in
> [`knowledge-base/strategies/amd-session-sweep/README.md`](../../knowledge-base/strategies/amd-session-sweep/README.md).
> Education, not financial advice.

## Layout

| File | Role |
|---|---|
| `main.py` | asyncio event loop + state machine (`Bot.step`): daily reset → breaker → rollover → new bar → strategy → risk → orders → trade management |
| `config.py` | Typed settings: sessions, strategy, filters, risk; credentials from env vars |
| `data_fetcher.py` | Closed bars and ticks from the broker, D1 ATR (cached daily), CSV history storage |
| `strategy_amd.py` | Asian range, sweep/displacement state machine, `Signal` with entry/SL/TP1/TP2 |
| `quantitative_filters.py` | 1-D Kalman filter, Kalman Z-score, ATR, volatility spike, range-vs-ATR gate |
| `risk_manager.py` | 1% position sizing, 2% daily breaker, max 2 trades, rollover pause, spread check |
| `execution.py` | `Broker` interface, `MT5Broker`, `PaperBroker`, `TradeManager` (two legs, break-even, trailing, state file) |
| `backtest.py` | Replays CSV bars through the **same** `Bot` on the paper broker |
| `tests/` | 57 pytest tests, including a fake MetaTrader5 module for the adapter |

## Rules as implemented (all times UTC)

| Stage | Rule | Config |
|---|---|---|
| Accumulation | High/low of bars opening 00:00–05:55 | `SessionConfig.asian_*` |
| Range gate | Skip the day if range > 2 × **D1** ATR(14); skip if ATR unavailable | `max_range_atr_mult`, `atr_timeframe` |
| Manipulation | In 07:00–10:00 or 12:00–15:00, price goes 8–20 pips beyond the Asian high/low (> 20 = breakout → void) | `sweep_min/max_pips` |
| Displacement | 1–3 bars after the bar that made the sweep extreme, a bar closes back inside the range | `displacement_max_bars` |
| Z-score gate | Kalman Z < −1.5 for longs, > +1.5 for shorts — measured as the **most extreme Z during the sweep** by default | `z_threshold`, `z_measure` |
| Volatility gate | std of the last 3 log returns > 1.3 × std of the 20 before them, at the displacement bar | `vol_*` |
| Entry | Market at the next tick after the displacement close; re-checks SL < price < TP1 | — |
| Stop | 2.5 pips beyond the sweep extreme | `sl_buffer_pips` |
| TP1 | Asian midpoint — leg A (50%) closes; leg B's SL → entry ± 0.5 pip | `tp1_fraction`, `be_offset_pips` |
| TP2 | Opposite Asian boundary — leg B | — |
| Size | 1.0% of equity ÷ (entry − SL) value, rounded **down** to the lot step | `risk_per_trade` |
| Daily breaker | Equity (realized + floating) ≤ day-start equity − 2% → close all, lock until 00:00 UTC | `daily_loss_limit`, `flatten_on_breaker` |
| Exposure | Max 2 open trades across pairs; 1 trade per pair; 1 per pair per session window | `max_open_trades` |
| Rollover | No new entries 21:50–22:15 (optional flatten) | `rollover_*`, `flatten_at_rollover` |
| Spread | No entry if spread > 2 pips | `max_spread_pips` |

### Choices where the spec was ambiguous
- **ATR timeframe = D1.** A 6-hour Asian range is always wider than 2 × an M5 ATR, so
  an M5 ATR would skip every day.
- **Z-score timing.** At the displacement bar price has already bounced back inside, so its
  Z is usually near 0 (seen in replays). The spec's "oversold manipulation" is measured
  at the sweep. Set `z_measure="displacement"` for the stricter, literal reading.
- **Two legs instead of a partial close.** TP1/TP2 live on the broker as real orders, so
  positions stay protected if the bot or connection dies.
- **Kalman filter in numpy** instead of `pykalman` (unmaintained) — no extra dependency.

### ⚠️ Reward-to-risk warning
With TP1 at the Asian midpoint and TP2 at the far boundary, the targets are often closer
than the stop. In the textbook test case (20-pip range, 12-pip sweep) a **full win is only
+0.53R**, and a full loss is −1R. The strategy then needs a win rate well above 65% to
break even after costs. Measure this on real data before trading it.

## Setup

```bash
pip install -r bots/amd_fx/requirements.txt
pytest -q bots/amd_fx/tests
```

### Replay (any OS)
CSV columns: a time column (`datetime`/`time`/`timestamp`/`date`, UTC or with an offset,
or Unix seconds) plus `open, high, low, close`. Give ≥ 15 days so D1 ATR(14) exists.

```bash
python -m bots.amd_fx.backtest EURUSD=EURUSD_M5.csv GBPUSD=GBPUSD_M5.csv \
    --spread 0.8 --commission 7 --out trades.csv --log-level INFO
# or through the main entry point:
python -m bots.amd_fx.main --paper --replay EURUSD=EURUSD_M5.csv
```
`--log-level INFO` logs every stage (armed, sweep, breakout, expired, filter rejection,
signal), so you can see where setups drop out.

### Live / demo (Windows + MetaTrader 5)
1. Install MT5, log in to a **demo** account, enable *Algo Trading*.
2. Copy `.env.example` → `.env`, fill it in, and load it into the environment.
3. `python -m bots.amd_fx.main --live`
- Bar and tick times are converted from broker server time to UTC (auto-detected, or set
  `MT5_SERVER_UTC_OFFSET`). Check the "Detected broker server time" log line.
- Open trades are saved to `data/amd_fx/trades_state.json` and recovered on restart.
- Stop with Ctrl+C; positions keep their broker-side SL/TP.

## Not done / limits
- **No results on real market data yet** — the replay has only been run on synthetic data.
- Replays use M5 bars: if a bar touches both SL and TP, SL is assumed first; spread is fixed.
- No news filter (NFP/CPI/FOMC days behave very differently).
- Interactive Brokers isn't implemented; add a `Broker` subclass in `execution.py`.
- `default_symbol_info` (paper broker) is exact only for XXXUSD pairs on a USD account.
