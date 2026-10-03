"""The research engine must reproduce the full Bot replay trade for trade."""
import asyncio
import dataclasses

import pandas as pd
import pytest

from bots.amd_fx.backtest import run_replay
from bots.amd_fx.config import AppConfig, FilterConfig, StrategyConfig
from bots.amd_fx.research.fast_backtest import Costs, generate_signals, simulate, stats
from bots.amd_fx.tests.conftest import filler_days, sweep_day


def scenario_days() -> pd.DataFrame:
    win = sweep_day("2024-03-05")
    short = sweep_day("2024-03-06", side="short")
    be = sweep_day("2024-03-07")
    late = be.index >= pd.Timestamp("2024-03-07 07:55", tz="UTC")
    be.loc[late, ["open", "high", "low", "close"]] = [1.0999, 1.1001, 1.0985, 1.0986]
    loss = sweep_day("2024-03-08")
    crash = loss.index >= pd.Timestamp("2024-03-08 07:45", tz="UTC")
    loss.loc[crash, ["open", "high", "low", "close"]] = [1.0990, 1.0991, 1.0970, 1.0972]
    return pd.concat([filler_days("2024-02-01", 20), win, short, be, loss])


@pytest.mark.parametrize("strategy", [StrategyConfig(), StrategyConfig(tp1_fraction=0.0),
                                      StrategyConfig(tp2_extension=0.5)])
def test_engine_matches_bot_replay(strategy):
    cfg = AppConfig(filters=FilterConfig(use_zscore=False, use_vol_spike=False),
                    strategy=strategy)
    data = scenario_days()
    bot = asyncio.run(run_replay(cfg, {}, frames={"EURUSD": data}, spread_pips=0.8,
                                 commission_per_lot=7.0))
    sigs = generate_signals(data, "EURUSD", cfg)
    fast = simulate(data, sigs, "EURUSD", cfg, Costs(0.8, 7.0), compound=True)

    assert len(sigs) == len(bot["signals"]) == 4
    assert [s.time for s in sigs] == [s.time for s in bot["signals"]]
    assert len(fast) == len(bot["trades"])
    for f, b in zip(fast, bot["trades"]):
        assert f.side == b.side
        assert f.entry == pytest.approx(b.entry)
        assert f.lots == pytest.approx(b.volume)
        assert f.pnl == pytest.approx(b.pnl, abs=0.01)
        assert f.r == pytest.approx(b.r_multiple, abs=1e-4)


def test_stats():
    s = stats(pd.Series([1.0, -1.0, 2.0, -1.0]))
    assert s["trades"] == 4 and s["exp_r"] == 0.25 and s["pf"] == 1.5 and s["win"] == 0.5
    assert stats(pd.Series([], dtype=float))["trades"] == 0
