"""Generate a synthetic 5-minute OHLCV CSV (random walk) to try the backtester.

The data is random, so any "edge" it shows is noise - use it only to check the pipeline.
    python make_sample_data.py --days 250 --out sample_5min.csv
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd


def make(days: int = 250, start_price: float = 400.0, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows, price = [], start_price
    for day in pd.bdate_range("2024-01-02", periods=days):
        price *= np.exp(rng.normal(0, 0.006))  # overnight gap
        for t in pd.date_range(day + pd.Timedelta("9h30min"), periods=78, freq="5min"):
            ret = rng.normal(0, 0.0015)
            o, c = price, price * np.exp(ret)
            h = max(o, c) * (1 + abs(rng.normal(0, 0.0006)))
            l = min(o, c) * (1 - abs(rng.normal(0, 0.0006)))
            rows.append((t, o, h, l, c, int(rng.integers(1e4, 1e5))))
            price = c
    return pd.DataFrame(rows, columns=["datetime", "open", "high", "low", "close", "volume"])


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=250)
    p.add_argument("--out", default="sample_5min.csv")
    a = p.parse_args()
    make(a.days).to_csv(a.out, index=False)
    print(f"Wrote {a.out}")
