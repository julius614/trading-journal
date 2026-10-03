"""Synthetic cointegrated pair data (H1)."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # repo root

BETA, Y0, X0 = 0.6, 1.10, 1.27


def make_pair(n_bars: int = 3000, swing_pips: float = 40.0, half_life: float = 15.0,
              x_vol: float = 0.0015, seed: int = 7, start: str = "2024-01-01 00:00",
              y: str = "EURUSD", x: str = "GBPUSD") -> Dict[str, pd.DataFrame]:
    """ln(y) = BETA * ln(x) + alpha + s, with s a mean-reverting (OU) spread whose standard
    deviation is about `swing_pips` y-pips. Hourly bars."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=n_bars, freq="1h", tz="UTC")
    lx = np.log(X0) + np.cumsum(rng.normal(0, x_vol, n_bars))
    phi = 0.5 ** (1 / half_life)
    sd = swing_pips * 1e-4 / Y0
    shocks = rng.normal(0, sd * np.sqrt(1 - phi ** 2), n_bars)
    s = np.zeros(n_bars)
    for t in range(1, n_bars):
        s[t] = phi * s[t - 1] + shocks[t]
    ly = BETA * lx + (np.log(Y0) - BETA * np.log(X0)) + s

    def frame(log_close: np.ndarray) -> pd.DataFrame:
        c = np.exp(log_close)
        return pd.DataFrame({"open": c, "high": c, "low": c, "close": c}, index=idx)

    return {y: frame(ly), x: frame(lx)}


@pytest.fixture
def pair() -> Dict[str, pd.DataFrame]:
    return make_pair()
