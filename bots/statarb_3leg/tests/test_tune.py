import pandas as pd

from bots.statarb_3leg.tune import accept, neighbours, period_stats, select, split_by_period


def test_split_by_entry_period():
    t = pd.DataFrame({"opened_at": ["2019-05-01T10:00:00+00:00", "2023-06-01T10:00:00+00:00",
                                    "2025-02-01T10:00:00+00:00"], "pnl": [1.0, 2.0, 3.0]})
    parts = split_by_period(t)
    assert [len(parts[p]) for p in ("tune", "validate", "holdout")] == [1, 1, 1]


def test_period_stats():
    s = period_stats(pd.DataFrame({"pnl": [10.0, -5.0, 5.0]}))
    assert s["trades"] == 3 and s["pnl"] == 10.0 and s["pf"] == 3.0


def test_neighbours_on_grid_edges():
    assert set(neighbours((1.75, 24))) == {(1.75, 24), (2.0, 24), (1.75, 48)}
    assert len(neighbours((2.0, 48))) == 5


def _table(per_trade, trades=100, pf=1.2, val_pnl=50.0, val_pf=1.2):
    rows = []
    for (z, h), v in per_trade.items():
        rows.append({"entry_z": z, "max_hold": h, "tune_trades": trades, "tune_pf": pf,
                     "tune_per_trade": v, "validate_pnl": val_pnl, "validate_pf": val_pf})
    return pd.DataFrame(rows)


def test_select_prefers_robust_region_over_lone_spike():
    grid = {(z, h): 1.0 for z in (1.75, 2.0, 2.5) for h in (24, 48, 96)}
    grid[(2.5, 96)] = 50.0                      # lone spike in a corner
    for k in [(1.75, 24), (2.0, 24), (1.75, 48)]:
        grid[k] = 5.0                           # a consistently good region
    assert select(_table(grid)) == (1.75, 24)


def test_select_respects_minimum_trades_and_pf():
    grid = {(z, h): 1.0 for z in (1.75, 2.0, 2.5) for h in (24, 48, 96)}
    assert select(_table(grid, trades=10)) is None
    assert select(_table(grid, pf=0.9)) is None


def test_accept_keeps_default_when_validation_fails():
    grid = {(z, h): 1.0 for z in (1.75, 2.0, 2.5) for h in (24, 48, 96)}
    t = _table(grid, val_pnl=-10.0)
    assert accept(t, (2.5, 96))[0] == (2.0, 48)
    assert accept(_table(grid), (2.5, 96))[0] == (2.5, 96)
    assert accept(t, None)[0] == (2.0, 48)
