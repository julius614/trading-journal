"""Pair data: aligned closed bars for the two legs, live ticks, and CSV loading."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Mapping, Sequence

import numpy as np
import pandas as pd

from ..amd_fx.data_fetcher import ensure_utc
from .config import PIP, AppConfig
from .execution import Broker, Tick

POINT = 0.00001   # MT5 "spread" column is in points (5-digit pricing)


def align_closes(frames: Mapping[str, pd.DataFrame], y: str, x: str) -> pd.DataFrame:
    """Closes of both legs on shared timestamps (inner join), plus log prices."""
    closes = pd.concat({y: ensure_utc(frames[y])["close"], x: ensure_utc(frames[x])["close"]},
                       axis=1, join="inner").dropna()
    closes["log_y"] = np.log(closes[y])
    closes["log_x"] = np.log(closes[x])
    return closes


class PairFeed:
    """Pulls closed bars and live ticks for the two legs from a broker."""

    def __init__(self, broker: Broker, cfg: AppConfig) -> None:
        self.broker = broker
        self.cfg = cfg

    async def closed_bars(self, count: int) -> pd.DataFrame:
        frames = {}
        for s in self.cfg.pair:   # sequential: the MT5 library is not thread-safe
            frames[s] = await self.broker.get_rates(self.cfg.broker_symbol(s),
                                                    self.cfg.strategy.timeframe, count)
        return align_closes(frames, self.cfg.y, self.cfg.x)

    async def ticks(self) -> Dict[str, Tick]:
        return {s: await self.broker.get_tick(self.cfg.broker_symbol(s))
                for s in self.cfg.price_symbols}


def load_leg_csv(path: str | Path) -> pd.DataFrame:
    """Read one symbol's CSV (from download_history or any OHLC export).

    Keeps open/high/low/close and, when present, converts MT5's `spread` column (points)
    to `spread_pips` so replays use the broker's real historical spreads.
    """
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    tcol = next((c for c in ("datetime", "time", "timestamp", "date") if c in df.columns), None)
    if tcol is None:
        raise ValueError(f"{path}: no time column")
    if pd.api.types.is_numeric_dtype(df[tcol]):
        idx = pd.to_datetime(df[tcol], unit="s", utc=True)
    else:
        idx = pd.to_datetime(df[tcol].astype(str), utc=True)
    out = df[["open", "high", "low", "close"]].astype(float)
    if "spread" in df.columns:
        out["spread_pips"] = df["spread"].astype(float) * POINT / PIP
    out.index = pd.DatetimeIndex(idx)
    return ensure_utc(out)


def load_pair(paths: Mapping[str, str], pair: Sequence[str]) -> Dict[str, pd.DataFrame]:
    missing = set(pair) - set(paths)
    if missing:
        raise ValueError(f"need CSVs for {sorted(missing)}")
    return {s: load_leg_csv(paths[s]) for s in pair}
