"""End-to-end: replay synthetic data through Bot + PaperBroker + TradeManager."""
import asyncio

import pandas as pd
import pytest

from bots.amd_fx.config import AppConfig, FilterConfig
from bots.amd_fx.backtest import run_replay
from bots.amd_fx.tests.conftest import filler_days, sweep_day

CFG = AppConfig(filters=FilterConfig(use_zscore=False, use_vol_spike=False))


def replay(frames, cfg=CFG, **kw):
    return asyncio.run(run_replay(cfg, {}, frames=frames, **kw))


def test_full_trade_lifecycle_long():
    # 20 filler days give the D1 ATR(14) its history; the sweep day comes after them
    data = pd.concat([filler_days("2024-02-01", 20), sweep_day("2024-03-05")])
    res = replay({"EURUSD": data}, balance=10_000, spread_pips=0.8)
    assert len(res["signals"]) == 1
    trades = res["trades"]
    assert len(trades) == 1
    t = trades[0]
    assert t.side == 1 and set(t.legs) == {"A", "B"}
    # entry at the ask: 1.0994 + 0.8 pip
    assert t.entry == pytest.approx(1.09948)
    # risk ~1% of equity: 19.3 pips -> 0.51 lots -> $98.43
    assert t.volume == pytest.approx(0.51)
    assert t.risk_amount == pytest.approx(0.51 * 193, rel=1e-3)
    # leg A closed at TP1, leg B at TP2 -> both profitable
    reasons = sorted(d.reason for d in res["deals"])
    assert reasons == ["tp", "tp"]
    # 0.25 lot x 5.2 pips + 0.26 lot x 15.2 pips = $52.52 on $98.43 risk = +0.53R:
    # with TP1 at the midpoint and TP2 at the far boundary, a FULL win is well under 1R
    assert t.pnl == pytest.approx(52.52, abs=0.01)
    assert t.r_multiple == pytest.approx(0.5336, abs=1e-3)
    assert t.be_done


def test_breakeven_protects_runner():
    day = sweep_day("2024-03-05")
    # after TP1 (07:50), drop back below entry instead of reaching TP2
    late = day.index >= pd.Timestamp("2024-03-05 07:55", tz="UTC")
    day.loc[late, ["open", "high", "low", "close"]] = [1.0999, 1.1001, 1.0985, 1.0986]
    data = pd.concat([filler_days("2024-02-01", 20), day])
    res = replay({"EURUSD": data})
    t = res["trades"][0]
    reasons = sorted(d.reason for d in res["deals"])
    assert reasons == ["sl", "tp"]        # runner stopped at break-even, not the original SL
    assert t.pnl > 0


def test_daily_loss_breaker_blocks_later_signals():
    import dataclasses
    from bots.amd_fx.config import RiskConfig
    from bots.amd_fx.tests.conftest import bars_frame

    # risk 2.5% per trade so one full loss trips the 2% daily breaker
    cfg = dataclasses.replace(CFG, risk=RiskConfig(risk_per_trade=0.025))
    day = sweep_day("2024-03-05")
    crash = day.index >= pd.Timestamp("2024-03-05 07:45", tz="UTC")
    day.loc[crash, ["open", "high", "low", "close"]] = [1.0990, 1.0991, 1.0970, 1.0972]
    flat = pd.date_range("2024-03-05 08:10", "2024-03-05 12:25", freq="5min", tz="UTC")
    recover = pd.DataFrame({"open": 1.1000, "high": 1.1003, "low": 1.0997, "close": 1.1000},
                           index=flat)
    ny = bars_frame([                              # a second, valid sweep in the NY window
        ("12:30", 1.0995, 1.0996, 1.0978, 1.0980),
        ("12:35", 1.0980, 1.0986, 1.0979, 1.0984),
        ("12:40", 1.0984, 1.0996, 1.0983, 1.0994),
        ("12:45", 1.0994, 1.0999, 1.0991, 1.0998),
    ], "2024-03-05")
    data = pd.concat([filler_days("2024-02-01", 20), day, recover, ny])
    # control: at 1% risk the first loss doesn't trip the breaker, so NY trades too
    control = replay({"EURUSD": data})
    assert len(control["trades"]) == 2

    res = replay({"EURUSD": data}, cfg=cfg)
    assert len(res["trades"]) == 1                  # Prop Shield blocks the NY setup
    t = res["trades"][0]
    assert t.r_multiple == pytest.approx(-1.0, abs=0.05)
    assert res["stats"]["end_balance"] == pytest.approx(10_000 + t.pnl)
    assert res["stats"]["end_balance"] <= 10_000 * 0.98
