"""Market data ingestion: closed OHLCV bars, ticks, ATR, and on-disk history."""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd

from .config import AppConfig
from .execution import Broker, BrokerError, Tick
from .quantitative_filters import atr

log = logging.getLogger(__name__)


def ensure_utc(df: pd.DataFrame) -> pd.DataFrame:
    """Return df with a sorted, de-duplicated, tz-aware UTC DatetimeIndex."""
    out = df.copy()
    if not isinstance(out.index, pd.DatetimeIndex):
        out.index = pd.to_datetime(out.index, utc=True)
    elif out.index.tz is None:
        out.index = out.index.tz_localize("UTC")
    else:
        out.index = out.index.tz_convert("UTC")
    out = out[~out.index.duplicated(keep="last")]
    return out.sort_index()


def load_ohlcv_csv(path: str | Path) -> pd.DataFrame:
    """Read an OHLCV CSV with a time column (datetime/time/timestamp/date).

    Unix-second timestamps and ISO strings with offsets are converted to UTC; naive
    timestamps are assumed to be UTC already.
    """
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    tcol = next((c for c in ("datetime", "time", "timestamp", "date") if c in df.columns), None)
    if tcol is None:
        raise ValueError(f"{path}: no time column")
    missing = {"open", "high", "low", "close"} - set(df.columns)
    if missing:
        raise ValueError(f"{path}: missing columns {sorted(missing)}")
    if pd.api.types.is_numeric_dtype(df[tcol]):
        idx = pd.to_datetime(df[tcol], unit="s", utc=True)
    else:
        idx = pd.to_datetime(df[tcol].astype(str), utc=True)
    cols = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
    out = df[cols].astype(float)
    out.index = pd.DatetimeIndex(idx)
    return ensure_utc(out)


class DataFetcher:
    """Pulls closed bars from the broker, caches them, and stores history to disk."""

    def __init__(self, broker: Broker, cfg: AppConfig) -> None:
        self.broker = broker
        self.cfg = cfg
        self.data_dir = Path(cfg.data_dir)
        self._bars: Dict[str, pd.DataFrame] = {}
        self._atr_cache: Dict[str, Tuple[date, Optional[float]]] = {}

    async def closed_bars(self, symbol: str, timeframe: Optional[str] = None,
                          count: Optional[int] = None) -> pd.DataFrame:
        """Latest closed bars on the execution timeframe (or `timeframe`)."""
        tf = timeframe or self.cfg.strategy.timeframe
        n = count or self.cfg.strategy.history_bars
        bars = ensure_utc(await self.broker.get_rates(symbol, tf, n))
        if tf == self.cfg.strategy.timeframe:
            self._bars[symbol] = bars
        return bars

    def last_bar_time(self, symbol: str) -> Optional[pd.Timestamp]:
        bars = self._bars.get(symbol)
        return None if bars is None or bars.empty else bars.index[-1]

    async def latest_tick(self, symbol: str) -> Tick:
        return await self.broker.get_tick(symbol)

    async def current_atr(self, symbol: str, today: date) -> Optional[float]:
        """ATR on the configured ATR timeframe, cached once per day per symbol."""
        cached = self._atr_cache.get(symbol)
        if cached and cached[0] == today:
            return cached[1]
        s = self.cfg.strategy
        value: Optional[float] = None
        try:
            higher = ensure_utc(await self.broker.get_rates(symbol, s.atr_timeframe,
                                                             s.atr_period * 3 + 1))
            series = atr(higher, s.atr_period).dropna()
            value = float(series.iloc[-1]) if len(series) else None
        except BrokerError as exc:
            log.error("%s: ATR unavailable (%s)", symbol, exc)
        if value is None:
            log.warning("%s: not enough %s bars for ATR(%d)", symbol, s.atr_timeframe, s.atr_period)
        self._atr_cache[symbol] = (today, value)
        return value

    # ---- history storage
    def history_path(self, symbol: str, timeframe: str) -> Path:
        return self.data_dir / f"{symbol}_{timeframe}.csv"

    def save_history(self, symbol: str, bars: pd.DataFrame, timeframe: Optional[str] = None) -> Path:
        """Append bars to the symbol's CSV, keeping one row per timestamp."""
        tf = timeframe or self.cfg.strategy.timeframe
        path = self.history_path(symbol, tf)
        path.parent.mkdir(parents=True, exist_ok=True)
        merged = ensure_utc(bars)
        if path.exists():
            merged = ensure_utc(pd.concat([load_ohlcv_csv(path), merged]))
        merged.to_csv(path, index_label="datetime")
        return path

    def load_history(self, symbol: str, timeframe: Optional[str] = None) -> pd.DataFrame:
        path = self.history_path(symbol, timeframe or self.cfg.strategy.timeframe)
        return load_ohlcv_csv(path) if path.exists() else pd.DataFrame()
