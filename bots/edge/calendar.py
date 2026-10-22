"""Calendar sleeve (protocol C1): turn-of-the-month and pre-FOMC drift, long only.

D1 bars come from bots.trend.research.trend.load_markets (index = server trading date,
00:00 UTC). A D1 "close" is stamped at 20:59 UTC of the trading date, so a position
bought at a close pays the 21:00 UTC rollover that night (see engine.rollover_nights).
"""
from __future__ import annotations

from datetime import time, timedelta
from typing import Dict, Iterable, List

import numpy as np
import pandas as pd

from bots.spec10.engine import Trade
from bots.spec10.strategies import NY, bars_at

CLOSE = pd.Timedelta(hours=20, minutes=59)


def _trade(sym: str, df: pd.DataFrame, i: int, j: int, weight: float, tag: str) -> Trade:
    d = df.index
    return Trade(sym, 1, d[i] + CLOSE, float(df["close"].iloc[i]), "market",
                 d[j] + CLOSE, float(df["close"].iloc[j]), "close", tag=tag, weight=weight)


def tom_trades(markets: Dict[str, pd.DataFrame], entry_from_end: int = 2, exit_day: int = 3,
               weight: float = 0.25) -> List[Trade]:
    """Buy at the close of the entry_from_end-th last trading day of each month (2 = the
    2nd-to-last), sell at the close of the exit_day-th trading day of the next month."""
    out = []
    for sym, df in markets.items():
        months = df.index.tz_localize(None).to_period("M")
        pos = pd.Series(np.arange(len(df)), index=months)
        groups = [g.to_numpy() for _, g in pos.groupby(level=0)]
        for cur, nxt in zip(groups[:-1], groups[1:]):
            if len(cur) < entry_from_end or len(nxt) < exit_day:
                continue
            out.append(_trade(sym, df, cur[-entry_from_end], nxt[exit_day - 1], weight, "TOM"))
    return out


def fomc_trades(markets: Dict[str, pd.DataFrame], dates: Iterable, weight: float = 0.5
                ) -> List[Trade]:
    """Buy at the close of the trading day before each FOMC statement day, sell at the
    statement day's close."""
    want = {pd.Timestamp(d).date() for d in dates}
    out = []
    for sym, df in markets.items():
        days = [d.date() for d in df.index]
        for j in range(1, len(days)):
            if days[j] in want:
                out.append(_trade(sym, df, j - 1, j, weight, "FOMC"))
    return out


def fomc_m5_trades(markets_m5: Dict[str, pd.DataFrame], dates: Iterable, weight: float = 0.5
                   ) -> List[Trade]:
    """Information only: 14:00 ET the weekday before -> 13:55 ET on the statement day
    (open prices of those M5 bars)."""
    days = pd.DatetimeIndex(sorted({pd.Timestamp(d) for d in dates}))
    prev = days - pd.offsets.BDay(1)
    out = []
    for sym, df in markets_m5.items():
        a = bars_at(df, prev, NY, time(14, 0))
        b = bars_at(df, days, NY, time(13, 55))
        for k in range(len(days)):
            if np.isfinite(a["open"].iloc[k]) and np.isfinite(b["open"].iloc[k]):
                out.append(Trade(sym, 1, a["t"].iloc[k], float(a["open"].iloc[k]), "market",
                                 b["t"].iloc[k], float(b["open"].iloc[k]), "time",
                                 tag="FOMC-M5", weight=weight))
    return out


def random_dates_totals(trades: List[Trade], markets: Dict[str, pd.DataFrame], price_fn,
                        start: pd.Timestamp, end: pd.Timestamp, runs: int = 100,
                        seed: int = 7) -> np.ndarray:
    """Null for a long-only calendar rule: the same number of trades per market, the same
    holding lengths (in trading days) and sizes, entered on random days in [start, end).
    Returns each run's total net P&L (price_fn = priced DataFrame from a Trade list)."""
    rng = np.random.default_rng(seed)
    specs = []
    for t in trades:
        idx = markets[t.symbol].index
        i = idx.get_loc(t.entry_time - CLOSE)
        j = idx.get_loc(t.exit_time - CLOSE)
        specs.append((t.symbol, j - i, t.weight))
    pools = {}
    for sym, df in markets.items():
        ok = np.flatnonzero((df.index >= start) & (df.index < end))
        pools[sym] = ok
    out = np.empty(runs)
    for r in range(runs):
        sample = []
        for sym, hold, w in specs:
            df = markets[sym]
            pool = pools[sym][pools[sym] + hold < len(df)]
            i = int(rng.choice(pool))
            sample.append(_trade(sym, df, i, i + hold, w, "random"))
        out[r] = float(price_fn(sample)["net"].sum())
    return out
