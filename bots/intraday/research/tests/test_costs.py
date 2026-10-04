import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from bots.intraday.research.costs import breakeven_row
from bots.intraday.research.engine import trades_frame
from bots.intraday.research.protocol import other_broker_spread
from bots.intraday.research.sessions import SessionData, hour_of_week_utc
from bots.intraday.research.strategies import Trade


def _sd(n_days=2, n=78, spread=0.5, market="US"):
    c = np.full((n_days, n), 100.0)
    dates = [date(2024, 7, 1 + i) for i in range(n_days)]          # Mon, Tue (summer time)
    return SessionData("US500", market, dates, c, c, c, c, np.ones_like(c),
                       np.full_like(c, spread), 5)


def test_cost_mult_scales_cost_not_gross():
    sd = _sd()
    trades = [Trade(0, 1, 1, 10, 100.0, 101.0, 2.0, "close"),
              Trade(1, -1, 1, 10, 100.0, 100.5, 1.0, "close")]
    full = trades_frame(sd, trades)
    half = trades_frame(sd, trades, cost_mult=0.5)
    assert np.allclose(half["gross"], full["gross"])
    assert np.allclose(half["cost"], 0.5 * full["cost"])
    assert np.allclose(half["ret"], half["gross"] - half["cost"])


def test_breakeven_multiplier_is_gross_over_cost():
    sd = _sd()
    t = trades_frame(sd, [Trade(0, 1, 1, 10, 100.0, 101.0, 1.0, "close")])
    row = breakeven_row("NA", sd, t, point=0.01)
    assert row["breakeven_k"] == pytest.approx(t["gross"].sum() / t["cost"].sum(), rel=1e-2)
    # today's round trip: 0.5 spread + 0.5 slippage = 1.0 price = 100 bp at price 100
    assert row["cost_rt_bp"] == pytest.approx(100.0)
    assert row["breakeven_rt_bp"] == pytest.approx(row["breakeven_k"] * 100.0, rel=1e-2)


def test_hour_of_week_follows_new_york_dst():
    sd = _sd()
    how = hour_of_week_utc(sd)
    assert how[0, 0] == 13                     # Monday 09:30 EDT = 13:30 UTC, Monday = 0
    assert how[1, 0] == 24 + 13                # Tuesday
    winter = SessionData("US500", "US", [date(2024, 1, 8)], *([np.full((1, 78), 1.0)] * 6), 5)
    assert hour_of_week_utc(winter)[0, 0] == 14   # 09:30 EST = 14:30 UTC


def test_other_broker_spread_profile(tmp_path):
    idx = pd.date_range("2024-07-01", periods=24 * 12 * 7, freq="5min", tz="UTC")
    spread_pts = np.where(idx.hour == 13, 300, 100)                 # wider at 13:00 UTC
    pd.DataFrame({"datetime": idx, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0,
                  "volume": 1, "spread": spread_pts}).to_csv(tmp_path / "US500.cash_M5.csv.gz",
                                                             index=False)
    (tmp_path / "US500.cash_spec.json").write_text(json.dumps({"point": 0.01}))
    sd = _sd()
    sp = other_broker_spread(sd, str(tmp_path), "US500.cash")
    assert sp.shape == sd.close.shape
    assert sp[0, 0] == pytest.approx(3.0)      # 13:30 UTC bar -> 300 points x 0.01
    assert sp[0, 10] == pytest.approx(1.0)     # 14:20 UTC
