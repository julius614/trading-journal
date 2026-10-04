import json

import numpy as np
import pandas as pd
import pytest

from bots.trend.research import trend as tr


def _df(close, spread=0.0):
    idx = pd.bdate_range("2010-01-01", periods=len(close), tz="UTC")
    c = pd.Series(close, index=idx, dtype=float)
    return pd.DataFrame({"open": c, "high": c * 1.001, "low": c * 0.999, "close": c,
                         "volume": 1.0, "spread_price": spread}, index=idx)


def test_signals_on_a_steady_uptrend():
    df = _df(100 * np.exp(np.arange(400) * 0.001))
    s = tr.signals(df)
    assert s["TS"].iloc[-1] == 1 and s["MA"].iloc[-1] == 1 and s["DC"].iloc[-1] == 1
    assert s["TS"].iloc[100] == 0                       # not enough history yet
    assert s["ALL"].iloc[-1] == 1


def test_donchian_enters_and_exits():
    up = list(np.linspace(100, 130, 120))
    down = list(np.linspace(130, 100, 120))
    df = _df(up + down)
    dc = tr.signal_dc(df["high"], df["low"], df["close"])
    assert dc.iloc[110] == 1                            # long in the rise
    assert dc.iloc[-1] == -1                            # short after the fall broke the low
    assert set(dc.unique()) <= {-1.0, 0.0, 1.0}


def test_no_lookahead_and_costs():
    rng = np.random.default_rng(1)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, 600)))
    df = _df(close, spread=0.02)
    sig = tr.signals(df)["TS"]
    p = tr.market_pnl(df, sig)
    # P&L of day t uses the position decided at close t-1
    ret = df["close"].pct_change().fillna(0.0)
    assert np.allclose(p["gross"], p["position"].shift(1).fillna(0) * ret)
    # changing a future price never changes earlier positions
    df2 = df.copy()
    df2.iloc[500:, df2.columns.get_loc("close")] *= 1.5
    p2 = tr.market_pnl(df2, tr.signals(df2)["TS"])
    assert np.allclose(p["position"].iloc[:500], p2["position"].iloc[:500])
    assert (p["cost"] >= 0).all() and p["cost"].sum() > 0
    p_cheap = tr.market_pnl(df, sig, cost_mult=0.0)
    assert p_cheap["cost"].sum() == 0 and np.allclose(p_cheap["gross"], p["gross"])


def test_vol_target_and_cap():
    rng = np.random.default_rng(2)
    close = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.02, 800)))   # ~32% annual vol
    p = tr.market_pnl(_df(close), pd.Series(1.0, index=_df(close).index))
    realised = p["gross"].iloc[300:].std() * np.sqrt(252)
    assert realised == pytest.approx(0.10, rel=0.25)
    assert p["position"].max() <= tr.MAX_POSITION


def test_select_rule():
    t = pd.DataFrame({"candidate": ["TS", "MA", "DC", "ALL"],
                      "discovery_sharpe": [0.5, 0.3, 0.6, 0.45],
                      "cost2_discovery_ret": [0.02, 0.05, -0.01, 0.01],
                      "validate_sharpe": [0.25, 0.9, 0.9, 0.1]})
    joined, kept = tr.select(t)
    assert joined == ["TS", "ALL"] and kept == ["TS"]


def test_portfolio_averages_active_markets_and_concentration():
    a = _df(100 * np.exp(np.arange(600) * 0.001))
    b = _df(100 * np.exp(-np.arange(300) * 0.001))
    port, per = tr.portfolio({"A": a, "B": b}, "TS")
    assert len(port) == 600 and per.shape[1] == 2
    late = port.index[400]                              # only A trades there
    assert port.loc[late] == pytest.approx(per.loc[late, "A"])
    y, m = tr.concentration(pd.Series([1.0, 1.0], index=pd.to_datetime(["2020-01-02", "2021-01-04"])),
                            pd.DataFrame({"A": [1.0, 1.0], "B": [1.0, 1.0]},
                                         index=pd.to_datetime(["2020-01-02", "2021-01-04"])))
    assert y == pytest.approx(0.5) and m == pytest.approx(0.5)


def test_not_enough_markets(tmp_path, capsys):
    for s in ("AAA", "BBB"):
        df = _df(100 * np.exp(np.arange(2000) * 0.0003))
        df.drop(columns="spread_price").assign(spread=2).to_csv(
            tmp_path / f"{s}_D1.csv.gz", index_label="datetime")
        (tmp_path / f"{s}_spec.json").write_text(json.dumps({"point": 0.01}))
    tr.main(["--data-dir", str(tmp_path)])
    assert "not enough data" in capsys.readouterr().out


def test_d1_bars_get_server_trading_dates_and_sunday_dropped(tmp_path):
    idx = pd.DatetimeIndex(["2024-01-04 22:00", "2024-01-06 22:00", "2024-01-07 22:00"],
                           tz="UTC")                     # Fri, Sun-session, Mon (server dates)
    days = tr.trading_dates(idx)
    assert [d.day_name() for d in days] == ["Friday", "Sunday", "Monday"]
    summer = tr.trading_dates(pd.DatetimeIndex(["2024-07-04 21:00"], tz="UTC"))
    assert summer[0].day_name() == "Friday"
    # load_markets drops the Sunday bar
    n = 1400
    full = pd.bdate_range("2019-01-01", periods=n, tz="UTC") - pd.Timedelta(hours=2)
    sun = pd.DatetimeIndex(["2019-01-05 22:00"], tz="UTC")   # Sunday 2019-01-06 server
    stamps = full.append(sun).sort_values()
    c = np.linspace(100, 120, len(stamps))
    pd.DataFrame({"datetime": stamps, "open": c, "high": c, "low": c, "close": c,
                  "volume": 1, "spread": 2}).to_csv(tmp_path / "X_D1.csv.gz", index=False)
    (tmp_path / "X_spec.json").write_text(json.dumps({"point": 0.01}))
    m, _ = tr.load_markets(str(tmp_path))
    assert len(m["X"]) == n and (m["X"].index.dayofweek < 5).all()
