import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from bots.intraday.research.engine import FX_COMMISSION, stats, trades_frame  # noqa: E402
from bots.intraday.research.protocol import (candidates, concentration, period_of,  # noqa: E402
                                             select, split_dates)
from bots.intraday.research.sessions import (SessionData, build_sessions, market_of,  # noqa: E402
                                             session_bounds_utc)
from bots.intraday.research.strategies import (Trade, late_half_hour, noise_area,  # noqa: E402
                                               opening_range, vol_leverage)

NY = ZoneInfo("America/New_York")


# ---------------------------------------------------------------- helpers
def sd_from(close: np.ndarray, open_: np.ndarray = None, high=None, low=None, spread=0.0,
            market="US") -> SessionData:
    close = np.asarray(close, float)
    o = close.copy() if open_ is None else np.asarray(open_, float)
    h = np.maximum(o, close) if high is None else np.asarray(high, float)
    lo = np.minimum(o, close) if low is None else np.asarray(low, float)
    n_days = close.shape[0]
    dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(n_days)]
    return SessionData("TEST", market, dates, o, h, lo, close, np.ones_like(close),
                       np.full_like(close, spread), 5)


def noisy_days(n_days=40, n=78, seed=1, vol=0.001):
    rng = np.random.default_rng(seed)
    base = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n_days)))
    paths = base[:, None] * np.exp(np.cumsum(rng.normal(0, vol, (n_days, n)), axis=1))
    return paths


# ---------------------------------------------------------------- sessions
def test_market_classes():
    assert market_of("US500.cash") == "US" and market_of("NAS100") == "US"
    assert market_of("XAUUSD") == "US" and market_of("USOIL") == "US"
    assert market_of("GER40") == "DE" and market_of("UK100") == "UK"
    assert market_of("EURUSD") == "FX" and market_of("USDJPY.m") == "FX"
    assert market_of("XAUUSD") == "US"                         # gold is not a currency pair
    with pytest.raises(ValueError):
        market_of("BTC")


def test_session_bounds_follow_dst():
    assert session_bounds_utc(date(2025, 1, 10), "US")[0].hour == 14   # 09:30 EST = 14:30 UTC
    assert session_bounds_utc(date(2025, 7, 10), "US")[0].hour == 13   # 09:30 EDT = 13:30 UTC


def _bars(day: date, start=time(9, 0), end=time(17, 0), drop=()):
    t0 = datetime.combine(day, start, NY)
    idx = []
    t = t0
    while t.time() < end:
        if t.time() not in drop:
            idx.append(t.astimezone(ZoneInfo("UTC")))
        t += timedelta(minutes=5)
    idx = pd.DatetimeIndex(idx)
    px = np.arange(len(idx), dtype=float) + 100
    return pd.DataFrame({"open": px, "high": px + 1, "low": px - 1, "close": px + 0.5,
                         "volume": 1.0, "spread_price": 0.1}, index=idx)


def test_build_sessions_cuts_cash_session_in_both_dst_regimes():
    df = pd.concat([_bars(date(2025, 1, 10)), _bars(date(2025, 7, 10))])
    sd = build_sessions(df, "US500", "US")
    assert sd.dates == [date(2025, 1, 10), date(2025, 7, 10)]
    assert sd.n_bars == 78                                    # 6.5 h of M5
    first = _bars(date(2025, 1, 10))
    t930 = datetime.combine(date(2025, 1, 10), time(9, 30), NY)
    assert sd.open[0, 0] == first.loc[t930.astimezone(ZoneInfo("UTC")), "open"]


def test_build_sessions_drops_broken_days_and_fills_small_gaps():
    gappy = _bars(date(2025, 3, 3), drop={time(10, 0)})
    no_open = _bars(date(2025, 3, 4), drop={time(9, 30)})
    half_day = _bars(date(2025, 3, 5), end=time(13, 0))
    sd = build_sessions(pd.concat([gappy, no_open, half_day]), "US500", "US")
    assert sd.dates == [date(2025, 3, 3)]
    j = 6                                                      # the 10:00 slot
    assert sd.close[0, j] == sd.close[0, j - 1] and sd.volume[0, j] == 0


# ---------------------------------------------------------------- strategies
def test_vol_leverage_uses_only_past_days():
    c = noisy_days(30)
    sd = sd_from(c)
    lev = vol_leverage(sd, 14)
    c2 = c.copy()
    c2[20:] *= 1.5                                             # change the future
    lev2 = vol_leverage(sd_from(c2), 14)
    assert np.allclose(lev[:21], lev2[:21], equal_nan=True)
    assert np.nanmax(lev) <= 4.0


def test_late_half_hour_direction_and_window():
    c = noisy_days(30)
    sd = sd_from(c)
    tr = late_half_hour(sd)
    assert tr
    for t in tr:
        r1 = sd.close[t.day, 5] / sd.close[t.day - 1, -1] - 1
        assert t.side == np.sign(r1)
        assert t.entry_slot == 72 and t.exit_slot == 77       # last 30 minutes of 78 bars


def test_opening_range_stop_and_target():
    n_days, n = 20, 78
    c = np.full((n_days, n), 100.0)
    h, lo, o = c + 0.5, c - 0.5, c.copy()                      # ATR ~ 1 -> stop 0.1
    o[-1, 0], c[-1, 0] = 100.0, 100.2                         # green first bar -> long
    o[-1, 1:] = c[-1, 1:] = h[-1, 1:] = lo[-1, 1:] = 100.2     # quiet after the entry
    h[-1, 5] = 101.3                                           # +1.1 = 11R > 10R target
    sd = sd_from(c, o, h, lo)
    t = opening_range(sd)[-1]
    assert t.side == 1 and t.reason == "target"
    assert t.exit == pytest.approx(t.entry + 10 * (t.entry - (t.entry - 0.1 * 1.0)), rel=1e-6)
    lo[-1, 3] = 99.0                                           # stop hit before the target
    t2 = opening_range(sd_from(c, o, h, lo))[-1]
    assert t2.reason == "stop" and t2.exit_slot == 3


def test_noise_area_long_breakout_then_flat_at_close():
    n_days, n = 20, 78
    rng = np.random.default_rng(3)
    c = 100 * (1 + rng.normal(0, 0.0005, (n_days, n)))
    o = c.copy()
    o[:, 0] = 100.0
    c[-1, :] = np.linspace(100, 103, n)                        # strong trend day
    o[-1, 1:] = c[-1, :-1]
    o[-1, 0] = 100.0
    sd = sd_from(c, o)
    tr = [t for t in noise_area(sd) if t.day == n_days - 1]
    assert len(tr) == 1 and tr[0].side == 1 and tr[0].reason == "close"
    assert tr[0].entry_slot % 6 == 0                           # filled right after a 30-min check
    assert tr[0].exit == pytest.approx(103.0)


def test_noise_area_decisions_ignore_later_bars():
    c = noisy_days(30, vol=0.003)
    sd = sd_from(c)
    base = noise_area(sd)
    d = 25
    c2 = c.copy()
    c2[d, 40:] *= 1.05                                         # change the afternoon only
    after = [t for t in noise_area(sd_from(c2)) if t.day == d and t.entry_slot <= 40]
    before = [t for t in base if t.day == d and t.entry_slot <= 40]
    assert [(t.side, t.entry_slot) for t in after] == [(t.side, t.entry_slot) for t in before]


# ---------------------------------------------------------------- costs
def test_costs_subtract_spread_slippage_and_commission():
    c = np.full((2, 4), 100.0)
    sd = sd_from(c, spread=0.02, market="FX")
    t = Trade(1, 1, 1, 3, 100.0, 101.0, 2.0, "close")
    f = trades_frame(sd, [t])
    cost = (0.02 + 0.02) / 100 + FX_COMMISSION                 # spread + 1x median slippage
    assert f["ret"].iloc[0] == pytest.approx(2.0 * (0.01 - cost))
    f2 = trades_frame(sd, [t], slip_mult=2.0)
    assert f2["ret"].iloc[0] == pytest.approx(2.0 * (0.01 - cost - 0.0002))


def test_stats():
    s = stats(pd.DataFrame({"ret": [0.02, -0.01, 0.01]}))
    assert s["trades"] == 3 and s["pf"] == 3.0


# ---------------------------------------------------------------- protocol
def test_candidates_by_market():
    assert candidates("US500") == ["NA", "LH", "OR", "SW", "BK"]
    assert candidates("GER40") == ["NA", "OR", "BK"]
    assert candidates("EURUSD") == ["NA", "SW", "BK"]
    assert candidates("WTI") == ["NA", "LH", "OR", "BK"]


def test_split_and_periods():
    d = [pd.Timestamp("2020-01-01"), pd.Timestamp("2030-01-01")]
    c1, c2 = split_dates(d)
    assert pd.Timestamp("2025-12-01") < c1 < pd.Timestamp("2026-02-01")
    assert pd.Timestamp("2027-12-01") < c2 < pd.Timestamp("2028-02-01")
    s = pd.Series(pd.to_datetime(["2021-01-01", "2027-01-01", "2029-01-01"]))
    assert list(period_of(s, c1, c2)) == ["discovery", "validate", "holdout"]


def test_select_rule():
    t = pd.DataFrame({"combo": ["a", "b", "c", "d"], "discovery_trades": [200, 100, 200, 200],
                      "discovery_pf": [1.2, 2.0, 1.2, 1.3], "slip2_discovery_ret": [0.1, 0.1, -0.1, 0.1],
                      "validate_pf": [1.1, 1.1, 1.1, 1.0]})
    joined, kept = select(t)
    assert joined == ["a", "d"] and kept == ["a"]


def test_concentration():
    idx = pd.to_datetime(["2023-01-02", "2024-01-02"])
    df = pd.DataFrame({"NA:US500": [0.01, 0.01], "OR:GER40": [0.0, 0.02]}, index=idx)
    year, sym = concentration(df)
    assert year == pytest.approx(0.75) and sym == pytest.approx(0.5)


def test_loader_reads_gzip_and_converts_spread(tmp_path):
    import json
    from bots.intraday.research.data import available_symbols, load_symbol
    idx = pd.date_range("2024-01-02 14:30", periods=3, freq="5min", tz="UTC")
    pd.DataFrame({"datetime": idx, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0,
                  "volume": 5, "spread": 25}).to_csv(tmp_path / "US500_M5.csv.gz", index=False)
    (tmp_path / "US500_spec.json").write_text(json.dumps({"point": 0.01}))
    (tmp_path / "NOSPEC_M5.csv").write_text("datetime,open,high,low,close\n")
    assert available_symbols(tmp_path) == ["US500"]
    df, spec = load_symbol(tmp_path, "US500")
    assert len(df) == 3 and df["spread_price"].iloc[0] == pytest.approx(0.25)


# ---------------------------------------------------------------- SW / BK (user's options)
from bots.intraday.research.strategies import (_manage, donchian_breakout,  # noqa: E402
                                               liquidity_sweep)


def _sw_days():
    n = 78
    o = np.full((2, n), 100.0)
    c = np.full((2, n), 100.02)
    h = np.full((2, n), 100.1)
    lo = np.full((2, n), 99.95)
    h[0, 10], lo[0, 20] = 101.0, 99.0                         # previous day's high / low
    o[1, 2], h[1, 2], lo[1, 2], c[1, 2] = 100.9, 101.5, 100.6, 100.8   # sweep + reclaim
    o[1, 4], h[1, 4], lo[1, 4], c[1, 4] = 100.5, 100.5, 99.7, 99.8     # displacement, FVG
    return o, h, lo, c


def test_sweep_fvg_short_hits_target():
    o, h, lo, c = _sw_days()
    h[1, 6] = 100.6                                            # retrace into the gap
    lo[1, 20] = 98.0
    tr = liquidity_sweep(sd_from(c, o, h, lo))
    assert len(tr) == 1
    t = tr[0]
    assert t.side == -1 and t.entry_slot == 6 and t.entry == pytest.approx(100.55)
    assert t.reason == "target" and t.exit == pytest.approx(100.55 - 2.5 * (101.5 - 100.55))
    assert t.leverage == pytest.approx(min(10, 0.005 / (0.95 / 100.55)))


def test_sweep_needs_reclaim_and_limit_expires():
    o, h, lo, c = _sw_days()
    h[1, 12] = 100.6                                           # touches the gap too late
    assert liquidity_sweep(sd_from(c, o, h, lo)) == []
    o, h, lo, c = _sw_days()
    c[1, 2:6] = 101.3                                          # never closes back inside
    lo[1, 2:6] = 101.1
    h[1, 6] = 100.6
    assert liquidity_sweep(sd_from(c, o, h, lo)) == []


def test_sweep_not_for_dax_or_oil_markets():
    o, h, lo, c = _sw_days()
    h[1, 6] = 100.6
    assert liquidity_sweep(sd_from(c, o, h, lo, market="DE")) == []
    assert "SW" not in candidates("WTI") and "SW" in candidates("XAUUSD")
    assert "SW" in candidates("EURUSD") and "BK" in candidates("DAX")


def test_trailing_stop_only_tightens():
    c = np.array([[100.0, 100.5, 101.0, 102.0, 103.0, 102.5, 101.5, 101.0]])
    o = c.copy()
    o[0, 6] = 102.4                                            # opens above the trailed stop
    h, lo = np.maximum(o, c) + 0.05, np.minimum(o, c) - 0.05
    sd = sd_from(c, o, h, lo)
    slot, px, reason = _manage(sd, 0, 1, 1, 100.0, 99.0, trail_atr=0.5)
    assert reason == "stop" and px == pytest.approx(102.0)    # best close 103 - 2 x 0.5
    assert slot == 6


def test_breakout_long_on_trend_day_and_daily_cap():
    c = noisy_days(30, vol=0.0005)
    c[-1] = c[-1, 0] * np.linspace(1.0, 1.03, c.shape[1])    # strong up day
    tr = [t for t in donchian_breakout(sd_from(c)) if t.day == 29]
    assert tr and tr[0].side == 1
    noisy = noisy_days(40, vol=0.003)
    per_day = pd.Series([t.day for t in donchian_breakout(sd_from(noisy))]).value_counts()
    assert per_day.max() <= 2
    for t in donchian_breakout(sd_from(noisy)):
        assert t.exit_slot <= 77 and t.entry_slot % 3 == 0


def test_new_strategies_ignore_later_bars():
    c = noisy_days(30, vol=0.003)
    d = 25
    c2 = c.copy()
    c2[d, 40:] *= 1.05                                         # change one afternoon only

    def early(trades):                                         # everything decided before it
        return [(t.day, t.side, t.entry_slot) for t in trades
                if t.day < d or (t.day == d and t.entry_slot < 40)]
    for f in (donchian_breakout, liquidity_sweep):
        assert early(f(sd_from(c))) == early(f(sd_from(c2)))
