from datetime import date, time

import pandas as pd
import pytest

from bots.amd_fx.strategy_amd import compute_asian_range
from bots.amd_fx.tests.conftest import bars_frame


def test_exact_high_low_inside_window(long_day):
    rng = compute_asian_range(long_day, date(2024, 3, 5))
    assert rng.high == 1.1010 and rng.low == 1.0990
    assert rng.mid == pytest.approx(1.1000)
    assert rng.pips(0.0001) == pytest.approx(20.0)
    assert rng.bars == 72   # 00:00..05:55 on M5


def test_window_boundaries_are_start_inclusive_end_exclusive():
    prev = bars_frame([("23:55", 1.1, 1.2000, 1.0, 1.1)], "2024-03-04")   # previous day
    day = bars_frame([
        ("00:00", 1.1, 1.1050, 1.0950, 1.1),   # first Asian bar: included
        ("05:55", 1.1, 1.1060, 1.0940, 1.1),   # last Asian bar: included
        ("06:00", 1.1, 1.1500, 1.0500, 1.1),   # 06:00 bar: excluded
    ])
    rng = compute_asian_range(pd.concat([prev, day]), date(2024, 3, 5))
    assert (rng.high, rng.low, rng.bars) == (1.1060, 1.0940, 2)


def test_custom_window():
    day = bars_frame([("01:00", 1.1, 1.11, 1.09, 1.1), ("03:00", 1.1, 1.12, 1.08, 1.1)])
    rng = compute_asian_range(day, date(2024, 3, 5), time(0, 0), time(2, 0))
    assert (rng.high, rng.low) == (1.11, 1.09)


def test_no_bars_returns_none():
    day = bars_frame([("08:00", 1.1, 1.11, 1.09, 1.1)])
    assert compute_asian_range(day, date(2024, 3, 5)) is None
    assert compute_asian_range(day.iloc[:0], date(2024, 3, 5)) is None
