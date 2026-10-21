import math

import numpy as np
import pandas as pd
import pytest

from bots.spec10 import strategies as S
from bots.spec10.engine import (EQUITY, ONE_R, CostModel, Trade, choose_best, fx_costs,
                                index_costs, price_trades, random_entry_totals, stats,
                                walk_exit, SweepResult)

T0 = pd.Timestamp("2024-01-02 10:00", tz="UTC")


def _trade(**kw):
    base = dict(symbol="EURUSD", side=1, entry_time=T0, entry_price=1.1000, entry_kind="market",
                exit_time=T0 + pd.Timedelta(hours=1), exit_price=1.1010, exit_kind="time")
    base.update(kw)
    return Trade(**base)


# ----------------------------------------------------------------------- cost model
def test_costs_scale_x0_x1_x2():
    c = {"EURUSD": fx_costs("EURUSD")}
    t = [_trade()]
    p0, p1, p2 = (price_trades(t, c, m) for m in (0, 1, 2))
    assert p0["cost"].iloc[0] == 0
    assert p0["net"].iloc[0] == pytest.approx(p0["gross"].iloc[0])
    assert p2["cost"].iloc[0] == pytest.approx(2 * p1["cost"].iloc[0])


def test_fx_cost_components_no_stop_is_1x_notional():
    c = {"EURUSD": fx_costs("EURUSD")}
    p = price_trades([_trade()], c, 1)
    units = EQUITY / 1.1
    spread = 0.8 * 0.0001 * units                    # half in + half out = one full spread
    slip = 2 * 0.2 * 0.0001 * units                  # market entry + time exit
    comm = 2 * 3.5 / 100_000 * EQUITY
    assert p["notional"].iloc[0] == pytest.approx(EQUITY)
    assert p["cost"].iloc[0] == pytest.approx(spread + slip + comm)
    assert p["gross"].iloc[0] == pytest.approx(0.0010 * units)


def test_limit_entry_has_no_slippage():
    c = {"EURUSD": fx_costs("EURUSD")}
    m = price_trades([_trade(entry_kind="market", exit_kind="target")], c, 1)["cost"].iloc[0]
    l = price_trades([_trade(entry_kind="limit", exit_kind="target")], c, 1)["cost"].iloc[0]
    units = EQUITY / 1.1
    assert m - l == pytest.approx(0.2 * 0.0001 * units)


def test_risk_sizing_and_leverage_cap():
    c = {"EURUSD": fx_costs("EURUSD")}
    # 20-pip stop: 0.5% risk -> notional = 500 / (0.002/1.1)
    p = price_trades([_trade(stop=1.0980, exit_price=1.0980, exit_kind="stop")], c, 0)
    assert p["notional"].iloc[0] == pytest.approx(ONE_R / (0.0020 / 1.1))
    assert p["R"].iloc[0] == pytest.approx(-1.0)
    # 1-pip stop would need 5.5M notional -> capped at 10x equity
    p = price_trades([_trade(stop=1.0999)], c, 0)
    assert p["notional"].iloc[0] == pytest.approx(10 * EQUITY)
    ci = {"US500": index_costs(0.5, 0.01)}
    p = price_trades([_trade(symbol="US500", entry_price=5000.0, stop=4999.9,
                             exit_price=5001.0)], ci, 0)
    assert p["notional"].iloc[0] == pytest.approx(4 * EQUITY)


def test_bar_spread_used_for_index_and_fallback():
    ci = {"US500": index_costs(0.5, 0.01)}
    t1 = _trade(symbol="US500", entry_price=5000.0, exit_price=5000.0, spread_in=1.0, spread_out=1.0,
                entry_kind="limit", exit_kind="target")
    t2 = _trade(symbol="US500", entry_price=5000.0, exit_price=5000.0, spread_in=0.0, spread_out=float("nan"),
                entry_kind="limit", exit_kind="target")
    p = price_trades([t1, t2], ci, 1)
    units = EQUITY / 5000.0
    assert p["cost"].iloc[0] == pytest.approx(1.0 * units)
    assert p["cost"].iloc[1] == pytest.approx(0.5 * units)


def test_weight_scales_notional():
    c = {"EURUSD": fx_costs("EURUSD")}
    p = price_trades([_trade(weight=0.25)], c, 1)
    assert p["notional"].iloc[0] == pytest.approx(0.25 * EQUITY)


# ----------------------------------------------------------------------- fill rules
def _bars(rows):
    a = np.array(rows, float)
    return a[:, 0], a[:, 1], a[:, 2], a[:, 3]


def test_stop_before_target_same_bar():
    o, h, l, c = _bars([[100, 100.5, 99.5, 100], [100, 103, 97, 100]])
    j, px, kind = walk_exit(o, h, l, c, 0, 1, 1, stop=98, target=102, tick=0.01)
    assert (j, px, kind) == (1, 98, "stop")
    j, px, kind = walk_exit(o, h, l, c, 0, 1, -1, stop=102, target=98, tick=0.01)
    assert (j, px, kind) == (1, 102, "stop")


def test_stop_gap_fills_at_open():
    o, h, l, c = _bars([[100, 100.5, 99.5, 100], [97, 97.5, 96, 97]])
    assert walk_exit(o, h, l, c, 0, 1, 1, 98, 105, 0.01) == (1, 97, "stop")
    o, h, l, c = _bars([[100, 100.5, 99.5, 100], [103, 104, 102.5, 103]])
    assert walk_exit(o, h, l, c, 0, 1, -1, 102, 95, 0.01) == (1, 103, "stop")


def test_limit_target_needs_trade_through():
    o, h, l, c = _bars([[100, 102.0, 99.5, 101], [101, 101.5, 100.5, 101]])
    # touches 102 exactly -> no fill; exits at the last close
    assert walk_exit(o, h, l, c, 0, 1, 1, 98, 102, 0.01) == (1, 101, "close")
    o, h, l, c = _bars([[100, 102.01, 99.5, 101]])
    assert walk_exit(o, h, l, c, 0, 0, 1, 98, 102, 0.01) == (0, 102, "target")


def test_s7_limit_entry_needs_trade_through():
    # level 1.1000 approached from below; sell limit at the level touched but not traded through
    n = 40
    idx = pd.date_range("2024-03-05 07:00", periods=n, freq="5min", tz="UTC")
    c = np.linspace(1.0950, 1.0990, n)
    df = pd.DataFrame({"open": c, "high": c + 0.0002, "low": c - 0.0002, "close": c}, index=idx)
    b = S.make_bars(df)
    b.atr[:] = 0.0001
    i = 30
    appr = {"EURUSD": [(i, 1.1000, -1)]}
    b.h[i + 1] = 1.1000                      # touch only
    tr = S.s7({"EURUSD": df}, entry_buffer=0, stop_pips=10, target_R=1, approach_atr=1,
              bars={"EURUSD": b}, appr=appr)
    assert tr == []
    b.h[i + 2] = 1.10001                     # 1 tick through -> filled at the limit
    tr = S.s7({"EURUSD": df}, entry_buffer=0, stop_pips=10, target_R=1, approach_atr=1,
              bars={"EURUSD": b}, appr=appr)
    assert len(tr) == 1 and tr[0].side == -1 and tr[0].entry_price == 1.1000
    assert tr[0].entry_kind == "limit" and tr[0].entry_time == idx[i + 2]


# ----------------------------------------------------------------------- stats / baseline / selection
def test_stats_basic():
    c = {"EURUSD": fx_costs("EURUSD")}
    t = [_trade(exit_price=1.1011), _trade(exit_price=1.0990)]
    s = stats(price_trades(t, c, 0))
    assert s["trades"] == 2 and s["win_rate"] == 0.5
    assert s["longest_losing_streak"] == 1


def test_random_baseline_shape_and_cost():
    c = {"EURUSD": fx_costs("EURUSD")}
    t = [_trade() for _ in range(10)]
    r = random_entry_totals(t, c, runs=50)
    assert r.shape == (50,)
    assert r.min() < price_trades(t, c, 1)["gross"].sum()


def test_choose_best_uses_in_sample_only():
    c = {"EURUSD": fx_costs("EURUSD")}
    cut = T0 + pd.Timedelta(days=100)
    good_is = [_trade(entry_time=T0 + pd.Timedelta(days=i), exit_price=1.1050) for i in range(40)]
    bad_oos = [_trade(entry_time=cut + pd.Timedelta(days=i), exit_price=1.0900) for i in range(40)]
    flat_is = [_trade(entry_time=T0 + pd.Timedelta(days=i), exit_price=1.1000) for i in range(40)]
    great_oos = [_trade(entry_time=cut + pd.Timedelta(days=i), exit_price=1.1200) for i in range(40)]
    res = [SweepResult({"k": 0}, good_is + bad_oos), SweepResult({"k": 1}, flat_is + great_oos)]
    best, table = choose_best(res, c, cut)
    assert best == 0 and len(table) == 2


# ----------------------------------------------------------------------- strategies on synthetic data
def _us_day(date: str, path: np.ndarray) -> pd.DataFrame:
    idx = pd.date_range(pd.Timestamp(f"{date} 09:30", tz="America/New_York"), periods=78,
                        freq="5min").tz_convert("UTC")
    o = path[:-1]
    c = path[1:]
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + 0.1, "low": np.minimum(o, c) - 0.1,
                         "close": c, "volume": 1.0, "spread_price": 0.5}, index=idx)


def test_us_session_handles_dst_and_drops_incomplete_days():
    a = _us_day("2024-03-08", np.linspace(100, 101, 79))     # EST
    b = _us_day("2024-03-11", np.linspace(101, 102, 79))     # EDT (DST started 10 March)
    c = _us_day("2024-03-12", np.linspace(102, 103, 79)).drop(index=[pd.Timestamp("2024-03-12 15:00", tz="UTC")])
    ss = S.us_session(pd.concat([a, b, c]))
    assert [d.date().isoformat() for d in ss.dates] == ["2024-03-08", "2024-03-11"]
    assert pd.Timestamp(ss.t[0, 0]).tz_localize("UTC").hour == 14
    assert pd.Timestamp(ss.t[1, 0]).tz_localize("UTC").hour == 13


def test_s2_trades_sign_of_r1_from_1530_to_1600():
    a = _us_day("2024-03-11", np.full(79, 100.0))
    b = _us_day("2024-03-12", np.linspace(101, 103, 79))      # r1 > 0 -> long
    df = pd.concat([a, b])
    ss = {"X": S.us_session(df)}
    tr = S.s2({"X": df}, variant="base", skip_small=False, sessions=ss)
    assert len(tr) == 1 and tr[0].side == 1
    assert tr[0].entry_time.tz_convert("America/New_York").strftime("%H:%M") == "15:30"
    assert tr[0].exit_time.tz_convert("America/New_York").strftime("%H:%M") == "16:00"


def test_s1b_long_or_stop_at_or_low():
    path = np.r_[np.linspace(100, 101, 4), np.linspace(101, 102, 75)]
    df = _us_day("2024-03-12", path)
    tr = S.s1b({"X": df}, or_min=15, sessions={"X": S.us_session(df)})
    assert len(tr) == 1 and tr[0].side == 1
    assert tr[0].stop == pytest.approx(df["low"].iloc[:3].min())
    assert tr[0].entry_price == df["open"].iloc[3]


def test_s5_fades_move_into_london_fix_with_dst():
    idx = pd.date_range("2024-07-01 12:00", "2024-07-01 17:55", freq="5min", tz="UTC")
    px = np.full(len(idx), 1.1000)
    loc = idx.tz_convert("Europe/London")
    px[(loc.hour == 15) & (loc.minute >= 35)] = 1.1020       # rose into the fix
    df = pd.DataFrame({"open": px, "high": px, "low": px, "close": px}, index=idx)
    tr = S.s5({"EURUSD": df}, exit_time="16:30", min_move=5, days="all")
    assert len(tr) == 1 and tr[0].side == -1
    assert tr[0].entry_time == pd.Timestamp("2024-07-01 15:05", tz="UTC")     # 16:05 BST


def test_s9_short_sweep_entry_next_open():
    n = 60
    idx = pd.date_range("2024-03-05", periods=n, freq="15min", tz="UTC")
    c = np.full(n, 1.1000)
    df = pd.DataFrame({"open": c, "high": c + 0.0005, "low": c - 0.0005, "close": c}, index=idx)
    df.iloc[40, df.columns.get_loc("high")] = 1.1007          # pokes 2 pips above the swing
    b = S.make_bars(df, pd.Timedelta(minutes=15))
    tr = S.s9({"EURUSD": df}, N=20, over=0.5, target_R=1, stop_buffer=1,
              bars={"EURUSD": b}, spreads={"EURUSD": 0.00008})
    shorts = [t for t in tr if t.side == -1]
    assert shorts and shorts[0].entry_time == idx[41]
    assert shorts[0].stop == pytest.approx(1.1007 + 0.0001 + 0.00008)
