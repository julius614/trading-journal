import dataclasses

import pandas as pd
import pytest

from bots.amd_fx.config import AppConfig, FilterConfig
from bots.amd_fx.strategy_amd import AMDStrategy, Phase
from bots.amd_fx.tests.conftest import bars_frame, sweep_day

ATR = 0.0070   # 70 pips daily ATR -> 2x = 140 pips, so a 20-pip Asian range passes
NO_FILTERS = AppConfig(filters=FilterConfig(use_zscore=False, use_vol_spike=False))


def run(df, cfg=NO_FILTERS, atr=ATR):
    strat = AMDStrategy("EURUSD", cfg)
    signals = []
    for i in range(len(df)):
        sig = strat.on_bar(df.iloc[: i + 1], atr)
        if sig:
            signals.append(sig)
    return strat, signals


def test_long_signal_geometry(long_day):
    _, sigs = run(long_day)
    assert len(sigs) == 1
    s = sigs[0]
    assert s.side == 1 and s.time == pd.Timestamp("2024-03-05 07:40", tz="UTC")
    assert s.entry == 1.0994
    assert s.sweep_extreme == 1.0978
    assert s.stop_loss == pytest.approx(1.0978 - 0.00025)   # 2.5 pips beyond the trough
    assert s.tp1 == pytest.approx(1.1000)                  # Asian midpoint
    assert s.tp2 == pytest.approx(1.1010)                  # opposite boundary
    assert s.window == "07:00-10:00"


def test_short_signal_mirrors(short_day):
    _, sigs = run(short_day)
    s = sigs[0]
    assert s.side == -1
    assert s.sweep_extreme == pytest.approx(1.1022)
    assert s.stop_loss == pytest.approx(1.1022 + 0.00025)
    assert s.tp1 == pytest.approx(1.1000) and s.tp2 == pytest.approx(1.0990)


def test_range_wider_than_2x_atr_skips_day(long_day):
    strat, sigs = run(long_day, atr=0.0009)   # 2 x 9 pips = 18 < 20-pip range
    assert sigs == [] and strat.state.phase == Phase.SKIPPED


def test_missing_atr_skips_day(long_day):
    strat, sigs = run(long_day, atr=None)
    assert sigs == [] and strat.state.phase == Phase.SKIPPED


def test_sweep_beyond_20_pips_is_a_breakout(long_day):
    df = long_day.copy()
    df.loc[pd.Timestamp("2024-03-05 07:35", tz="UTC"), "low"] = 1.0965   # 25 pips beyond
    _, sigs = run(df)
    assert sigs == []


def test_sweep_below_8_pips_is_ignored(long_day):
    df = long_day.copy()
    t = pd.Timestamp("2024-03-05 07:30", tz="UTC")
    df.loc[t, ["low", "close"]] = [1.0985, 1.0986]                        # only 5 pips
    df.loc[pd.Timestamp("2024-03-05 07:35", tz="UTC"), "low"] = 1.0986
    _, sigs = run(df)
    assert sigs == []


def test_displacement_must_come_within_3_bars(long_day):
    df = long_day.copy()
    # keep closing outside the range for 4 bars after the sweep bar
    for hhmm in ("07:35", "07:40", "07:45", "07:50"):
        t = pd.Timestamp(f"2024-03-05 {hhmm}", tz="UTC")
        df.loc[t, ["open", "high", "low", "close"]] = [1.0984, 1.0988, 1.0981, 1.0985]
    df.loc[pd.Timestamp("2024-03-05 07:55", tz="UTC"), "close"] = 1.0995   # too late
    _, sigs = run(df)
    assert sigs == []


def test_sweep_outside_trade_window_is_ignored(long_day):
    df = long_day.copy()
    df.index = df.index.map(lambda t: t - pd.Timedelta(hours=1) if t.hour >= 7 else t)
    df = df[~df.index.duplicated(keep="last")].sort_index()   # sweep now at 06:30
    _, sigs = run(df)
    assert sigs == []


def test_zscore_filter_can_block(long_day):
    strict = AppConfig(filters=FilterConfig(use_zscore=True, z_threshold=100.0,
                                            use_vol_spike=False))
    _, sigs = run(long_day, cfg=strict)
    assert sigs == []


def test_vol_filter_can_block(long_day):
    strict = AppConfig(filters=FilterConfig(use_zscore=False, use_vol_spike=True,
                                            vol_mult=1000.0))
    _, sigs = run(long_day, cfg=strict)
    assert sigs == []


def test_one_trade_per_window(long_day):
    df = long_day.copy()
    extra = bars_frame([
        ("08:30", 1.0995, 1.0996, 1.0978, 1.0980),
        ("08:35", 1.0980, 1.0986, 1.0979, 1.0984),
        ("08:40", 1.0984, 1.0996, 1.0983, 1.0994),
    ])
    _, sigs = run(pd.concat([df, extra]))
    assert len(sigs) == 1


def test_state_resets_next_day(long_day):
    nxt = sweep_day("2024-03-06")
    _, sigs = run(pd.concat([long_day, nxt]))
    assert len(sigs) == 2


def test_default_filters_pass_a_textbook_sweep(long_day):
    _, sigs = run(long_day, cfg=AppConfig())        # Z-score + volatility filters on
    assert len(sigs) == 1
    s = sigs[0]
    assert s.zscore < -1.5                         # oversold at the manipulation
    assert s.vol_ratio > 1.3                       # volatility expanded on displacement


def test_zscore_measured_at_displacement_is_stricter(long_day):
    _, sweep_sigs = run(long_day, cfg=AppConfig())
    disp_cfg = AppConfig(filters=FilterConfig(z_measure="displacement", use_vol_spike=False))
    strat = AMDStrategy("EURUSD", disp_cfg)
    z_disp = strat._latest_z(long_day.loc[:"2024-03-05 07:40"]["close"])
    assert z_disp > sweep_sigs[0].zscore            # price has bounced: less extreme


def test_tp2_extension_beyond_range(long_day):
    import dataclasses
    from bots.amd_fx.config import StrategyConfig
    cfg = dataclasses.replace(NO_FILTERS, strategy=StrategyConfig(tp2_extension=0.5))
    _, sigs = run(long_day, cfg=cfg)
    assert sigs[0].tp2 == pytest.approx(1.1010 + 0.5 * 0.0020)   # half a range beyond
