"""Load research data as M5 bars with a UTC index.

Public history: OANDA 1-minute bars (UTC) for 2005 to May 2020 from the public GitHub repo
FutureSharks/financial-data (pyfinancialdata/data/currencies/oanda/<PAIR>/<YEAR>/*.csv).
Broker history: CSVs written by bots.amd_fx.download_history.

    python -m bots.amd_fx.research.load_data --oanda-root <repo>/pyfinancialdata/data/currencies/oanda
"""
from __future__ import annotations

import argparse
import glob
from pathlib import Path
from typing import Dict, Iterable, Optional

import pandas as pd

from ..data_fetcher import load_ohlcv_csv

DATA_DIR = Path(__file__).resolve().parent / "data"
OANDA_NAMES = {"EURUSD": "EUR_USD", "GBPUSD": "GBP_USD"}


def to_m5(m1: pd.DataFrame) -> pd.DataFrame:
    """Resample 1-minute OHLC to 5-minute bars (label = bar open time)."""
    out = m1.resample("5min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"})
    return out.dropna()


def validate(symbol: str, bars: pd.DataFrame) -> Dict[str, object]:
    """Basic checks: UTC index, no Saturday bars, sorted, plausible weekly opens."""
    idx = bars.index
    gaps = idx.to_series().diff()
    week_starts = idx[gaps > pd.Timedelta(hours=24)]
    report = {
        "symbol": symbol, "bars": len(bars), "first": idx[0], "last": idx[-1],
        "saturday_bars": int((idx.dayofweek == 5).sum()),
        "sorted": bool(idx.is_monotonic_increasing),
        "week_open_hours": sorted(set(int(t.hour) for t in week_starts)),
    }
    if report["saturday_bars"] or not report["sorted"]:
        raise ValueError(f"{symbol}: data failed validation: {report}")
    return report


def load_oanda(root: str, symbol: str, years: Iterable[int]) -> pd.DataFrame:
    files = []
    for y in years:
        files += sorted(glob.glob(f"{root}/{OANDA_NAMES[symbol]}/{y}/*.csv"))
    if not files:
        raise FileNotFoundError(f"no OANDA files for {symbol} under {root}")
    m1 = pd.concat(pd.read_csv(f, usecols=["time", "open", "high", "low", "close"]) for f in files)
    m1.index = pd.to_datetime(m1.pop("time"), utc=True)
    m1 = m1[~m1.index.duplicated()].sort_index().astype(float)
    return to_m5(m1)


def cache_path(symbol: str, source: str) -> Path:
    return DATA_DIR / f"{symbol}_{source}_M5.pkl"


def load_cached(symbol: str, source: str = "oanda") -> pd.DataFrame:
    path = cache_path(symbol, source)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing - run load_data first")
    return pd.read_pickle(path)


def load_broker(path: str) -> pd.DataFrame:
    return load_ohlcv_csv(path)[["open", "high", "low", "close"]]


def main(argv: Optional[list] = None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--oanda-root", required=True)
    p.add_argument("--years", default="2014-2020")   # earlier years fail the checks
    a = p.parse_args(argv)
    y0, y1 = (int(x) for x in a.years.split("-"))
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for sym in OANDA_NAMES:
        bars = load_oanda(a.oanda_root, sym, range(y0, y1 + 1))
        print(validate(sym, bars))
        bars.to_pickle(cache_path(sym, "oanda"))


if __name__ == "__main__":
    main()
