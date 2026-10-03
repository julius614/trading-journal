"""Synthetic triangle data with controlled dislocations."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # repo root


def make_triangle(n_bars: int = 2000, jump_pips: float = 15.0, every: int = 250,
                  noise_pips: float = 0.15, seed: int = 3,
                  start: str = "2024-03-04 00:00") -> Dict[str, pd.DataFrame]:
    """EURUSD and GBPUSD random walks; EURGBP = EURUSD/GBPUSD x exp(s).

    s is tiny noise plus, every `every` bars, a dislocation of `jump_pips` EURGBP pips
    (alternating sign) that halves for 3 bars and then vanishes.
    """
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=n_bars, freq="5min", tz="UTC")
    eu = 1.10 * np.exp(np.cumsum(rng.normal(0, 2e-4, n_bars)))
    gu = 1.27 * np.exp(np.cumsum(rng.normal(0, 2e-4, n_bars)))
    eg_fair = eu / gu
    s = rng.normal(0, noise_pips * 1e-4 / 0.866, n_bars)
    sign = 1.0
    for t in range(every, n_bars - 10, every):
        d = sign * jump_pips * 1e-4 / 0.866       # pips -> log units at EURGBP ~0.866
        for k, frac in enumerate((1.0, 0.5, 0.25, 0.125)):
            s[t + k] += d * frac
        sign = -sign
    eg = eg_fair * np.exp(s)

    def frame(close: np.ndarray) -> pd.DataFrame:
        return pd.DataFrame({"open": close, "high": close, "low": close, "close": close}, index=idx)

    return {"EURUSD": frame(eu), "GBPUSD": frame(gu), "EURGBP": frame(eg)}


@pytest.fixture
def triangle() -> Dict[str, pd.DataFrame]:
    return make_triangle()
