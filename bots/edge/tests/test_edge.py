import numpy as np
import pandas as pd
import pytest

from bots.edge import calendar as C
from bots.spec10.engine import CostModel, Trade, price_trades, rollover_nights


def _d1(start, end, holidays=()):
    idx = pd.bdate_range(start, end, tz="UTC")
    idx = idx[~idx.isin(pd.DatetimeIndex(holidays, tz="UTC"))]
    px = np.linspace(100, 110, len(idx))
    return pd.DataFrame({"open": px, "high": px, "low": px, "close": px, "spread_price": 0.1}, index=idx)


def test_tom_entry_2nd_last_exit_3rd_day_with_holiday():
    df = _d1("2024-12-02", "2025-01-31", holidays=["2024-12-25", "2025-01-01"])
    tr = C.tom_trades({"X": df})
    assert len(tr) == 1
    t = tr[0]
    assert t.entry_time.date().isoformat() == "2024-12-30"     # 31st is last, 30th 2nd-to-last
    assert t.exit_time.date().isoformat() == "2025-01-06"      # 2nd, 3rd, 6th (1st holiday)
    assert t.side == 1 and t.weight == 0.25


def test_tom_shifts():
    df = _d1("2024-12-02", "2025-01-31")
    t = C.tom_trades({"X": df}, entry_from_end=1, exit_day=4)[0]
    assert t.entry_time.date().isoformat() == "2024-12-31"
    assert t.exit_time.date().isoformat() == "2025-01-06"


def test_fomc_day_before_to_day():
    df = _d1("2024-01-22", "2024-02-09")
    tr = C.fomc_trades({"X": df}, [pd.Timestamp("2024-01-31")])
    assert len(tr) == 1
    assert tr[0].entry_time.date().isoformat() == "2024-01-30"
    assert tr[0].exit_time.date().isoformat() == "2024-01-31"


def test_fomc_m5_timing_dst():
    idx = pd.date_range("2024-03-18", "2024-03-21", freq="5min", tz="UTC")
    df = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0}, index=idx)
    tr = C.fomc_m5_trades({"X": df}, [pd.Timestamp("2024-03-20")])
    assert tr[0].entry_time == pd.Timestamp("2024-03-19 18:00", tz="UTC")    # 14:00 EDT
    assert tr[0].exit_time == pd.Timestamp("2024-03-20 17:55", tz="UTC")


def test_rollover_nights_wednesday_triple():
    mon = pd.Timestamp("2024-01-08 20:59", tz="UTC")
    assert rollover_nights(mon, mon + pd.Timedelta(days=1)) == 1           # Mon night
    assert rollover_nights(mon, mon + pd.Timedelta(days=3)) == 1 + 1 + 3   # Mon, Tue, Wed x3
    fri = pd.Timestamp("2024-01-12 20:59", tz="UTC")
    assert rollover_nights(fri, fri + pd.Timedelta(days=3)) == 1           # Fri only, no weekend
    assert rollover_nights(mon, mon) == 0


def test_financing_cost_and_zero_default():
    t = Trade("X", 1, pd.Timestamp("2024-01-08 20:59", tz="UTC"), 100.0, "market",
              pd.Timestamp("2024-01-11 20:59", tz="UTC"), 100.0, "close")
    base = CostModel(spread=0.0, slippage=0.0)
    fin = CostModel(spread=0.0, slippage=0.0, financing_per_year=0.036)
    assert price_trades([t], {"X": base})["cost"].iloc[0] == 0
    c = price_trades([t], {"X": fin})["cost"].iloc[0]
    assert c == pytest.approx(100_000 * 0.036 / 360 * 5)                  # Mon, Tue, Wed x3


def test_random_dates_same_count_and_hold():
    df = _d1("2023-01-02", "2024-12-31")
    tr = C.tom_trades({"X": df})
    seen = []
    def fn(sample):
        seen.append(sample)
        return price_trades(sample, {"X": CostModel(spread=0.0, slippage=0.0)})
    r = C.random_dates_totals(tr, {"X": df}, fn, df.index[0], df.index[-1], runs=3)
    assert r.shape == (3,)
    assert all(len(s) == len(tr) for s in seen)
