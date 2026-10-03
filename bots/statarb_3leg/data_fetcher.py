"""Triangle data: aligned closed M5 bars for EURUSD/GBPUSD/EURGBP, live ticks, CSV loading."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Dict, Mapping, Optional

import pandas as pd

from ..amd_fx.data_fetcher import ensure_utc
from .config import PIP, TRIANGLE, AppConfig
from .execution import Broker, Tick
from .kalman_statarb import log_spread

POINT = 0.00001   # MT5 "spread" column is in points (5-digit pricing)


def align_closes(frames: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    """Closes of the three pairs on timestamps all three share (inner join), plus the
    log spread."""
    closes = pd.concat({s: ensure_utc(frames[s])["close"] for s in TRIANGLE}, axis=1,
                       join="inner").dropna()
    closes["spread"] = log_spread(closes["EURGBP"], closes["EURUSD"], closes["GBPUSD"])
    return closes


class TriangleFeed:
    """Pulls closed bars and live ticks for the three legs from a broker."""

    def __init__(self, broker: Broker, cfg: AppConfig) -> None:
        self.broker = broker
        self.cfg = cfg

    async def closed_bars(self, count: int) -> pd.DataFrame:
        """Aligned closes (and spread) for the last `count` closed bars of each pair."""
        frames = {}
        for s in TRIANGLE:   # sequential: the MT5 library is not thread-safe
            frames[s] = await self.broker.get_rates(self.cfg.broker_symbol(s),
                                                    self.cfg.strategy.timeframe, count)
        return align_closes(frames)

    async def ticks(self) -> Dict[str, Tick]:
        out = {}
        for s in TRIANGLE:
            out[s] = await self.broker.get_tick(self.cfg.broker_symbol(s))
        return out


def load_leg_csv(path: str | Path) -> pd.DataFrame:
    """Read one pair's M5 CSV (from download_history or any OHLC export).

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


def load_triangle(paths: Mapping[str, str]) -> Dict[str, pd.DataFrame]:
    missing = set(TRIANGLE) - set(paths)
    if missing:
        raise ValueError(f"need CSVs for {sorted(missing)}")
    return {s: load_leg_csv(paths[s]) for s in TRIANGLE}
