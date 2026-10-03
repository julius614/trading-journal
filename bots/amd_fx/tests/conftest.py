"""Shared builders for synthetic M5 data."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable, List, Tuple

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # repo root

Bar = Tuple[str, float, float, float, float]  # (HH:MM, open, high, low, close)

DAY = "2024-03-05"


def bars_frame(rows: Iterable[Bar], day: str = DAY) -> pd.DataFrame:
    rows = list(rows)
    idx = pd.DatetimeIndex([pd.Timestamp(f"{day} {r[0]}", tz="UTC") for r in rows])
    return pd.DataFrame([r[1:] for r in rows], columns=["open", "high", "low", "close"], index=idx)


def sweep_day(day: str = DAY, side: str = "long") -> pd.DataFrame:
    """A day with a clean Asian range (1.0990-1.1010) and one textbook sweep.

    long : 07:30 sweeps the Asian low by 12 pips (to 1.0978), 07:40 closes back inside
           at 1.0994, then price rallies through TP1 (1.1000) and TP2 (1.1010).
    short: the mirror image around 1.1000.
    """
    rows: List[Bar] = []
    for t in pd.date_range(f"{day} 00:00", f"{day} 07:25", freq="5min"):
        hhmm = t.strftime("%H:%M")
        hi, lo = 1.1005, 1.0995
        if hhmm == "02:00":
            hi = 1.1010
        if hhmm == "04:00":
            lo = 1.0990
        if t.hour >= 6:
            hi, lo = 1.1003, 1.0997
        # +-0.5 pip alternating closes: a realistic, non-zero volatility baseline
        close = 1.10005 if len(rows) % 2 else 1.09995
        rows.append((hhmm, 1.1000, hi, lo, close))
    rows += [
        ("07:30", 1.0995, 1.0996, 1.0978, 1.0980),   # sweep: 12 pips below the low
        ("07:35", 1.0980, 1.0986, 1.0979, 1.0984),   # still outside
        ("07:40", 1.0984, 1.0996, 1.0983, 1.0994),   # displacement: closes back inside
        ("07:45", 1.0994, 1.0999, 1.0991, 1.0998),
        ("07:50", 1.0998, 1.1003, 1.0996, 1.1002),   # TP1 1.1000
        ("07:55", 1.1002, 1.1008, 1.1001, 1.1007),
        ("08:00", 1.1007, 1.1013, 1.1006, 1.1012),   # TP2 1.1010
        ("08:05", 1.1012, 1.1014, 1.1009, 1.1011),
    ]
    df = bars_frame(rows, day)
    if side == "short":   # mirror prices around 1.1000
        m = 2 * 1.1000
        df = pd.DataFrame({"open": m - df["open"], "high": m - df["low"],
                           "low": m - df["high"], "close": m - df["close"]}, index=df.index)
    return df


def filler_days(start: str, n: int) -> pd.DataFrame:
    """Smooth sine-wave days (~60-pip daily range) that never form a sweep setup."""
    frames = []
    for d in pd.bdate_range(start, periods=n):
        idx = pd.date_range(d, periods=288, freq="5min", tz="UTC")
        phase = np.linspace(0, 2 * np.pi, 288, endpoint=False)
        close = 1.1000 + 0.0030 * np.sin(phase)
        open_ = np.concatenate([[close[0]], close[:-1]])
        frames.append(pd.DataFrame({
            "open": open_, "close": close,
            "high": np.maximum(open_, close) + 0.00005,
            "low": np.minimum(open_, close) - 0.00005,
        }, index=idx))
    return pd.concat(frames)


@pytest.fixture
def long_day() -> pd.DataFrame:
    return sweep_day(side="long")


@pytest.fixture
def short_day() -> pd.DataFrame:
    return sweep_day(side="short")
