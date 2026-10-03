import numpy as np
import pandas as pd
import pytest

from bots.statarb_3leg.portfolio import (CANDIDATES, bootstrap_paths, challenge_odds,
                                         daily_pnl, pair_name, recommend_scale, select_pairs)


def test_six_candidates_y_leg_first_in_order():
    names = [pair_name(p) for p in CANDIDATES]
    assert names == ["EUR/GBP", "EUR/AUD", "EUR/NZD", "GBP/AUD", "GBP/NZD", "AUD/NZD"]


def test_select_pairs_rule():
    t = pd.DataFrame({"pair": ["A", "B", "C", "D"], "tune_trades": [50, 30, 50, 50],
                      "tune_pf": [1.2, 2.0, 1.05, 1.3], "validate_pf": [1.1, 1.5, 1.5, 0.9]})
    joined, kept = select_pairs(t)
    assert joined == ["A", "D"] and kept == ["A"]


def test_daily_pnl_buckets_by_close_day_and_rolls_weekends():
    trades = {"P": pd.DataFrame({"closed_at": ["2023-01-02T15:00:00+00:00",
                                               "2023-01-02T20:00:00+00:00",
                                               "2023-01-07T01:00:00+00:00"],   # Saturday
                                 "pnl": [100.0, -50.0, 200.0]})}
    d = daily_pnl(trades, "2023-01-02", pd.Timestamp("2023-01-10", tz="UTC"), balance=1000.0)
    assert d.loc["2023-01-02", "P"] == pytest.approx(0.05)
    assert d.loc["2023-01-09", "P"] == pytest.approx(0.2)
    assert d["P"].sum() == pytest.approx(0.25)


def test_bootstrap_uses_contiguous_blocks():
    daily = np.arange(100, dtype=float)
    paths = bootstrap_paths(daily, 50, 23, 5, np.random.default_rng(0))
    assert paths.shape == (50, 23)
    blocks = paths[:, :20].reshape(50, 4, 5)
    assert np.all(np.diff(blocks, axis=2) == 1)


def test_challenge_odds_deterministic_paths():
    up = np.full((1, 100), 0.01)                  # +1%/day -> passes on day 10
    o = challenge_odds(up, 1.0)
    assert o["p_pass"] == 1 and o["p_fail"] == 0
    assert o["median_months_to_pass"] == pytest.approx(10 / 21)
    crash = np.array([[0.01, -0.03] + [0.01] * 98])
    assert challenge_odds(crash, 1.0)["p_pass"] == 1      # -3% day is fine at 1x
    o2 = challenge_odds(crash, 2.0)                          # -6% day breaches at 2x
    assert o2["p_fail"] == 1 and o2["p_daily_breach"] == 1
    flat = np.zeros((1, 100))
    o3 = challenge_odds(flat, 1.0)
    assert o3["p_pass"] == 0 and o3["p_fail"] == 0 and np.isnan(o3["median_months_to_pass"])


def test_recommend_scale():
    odds = pd.DataFrame({"scale": [1.0, 2.0, 3.0], "p_daily_breach": [0.0, 0.01, 0.05],
                         "p_fail": [0.01, 0.05, 0.2]})
    assert recommend_scale(odds) == 2.0
    assert recommend_scale(odds.assign(p_fail=0.5)) is None
