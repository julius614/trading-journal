"""Cash-session slicing for intraday research.

Each market trades a fixed local-time session (DST handled by zoneinfo). The M5 bars of
every complete session are laid out as rows of a (days x bars) matrix so strategies can
work on whole days at once. Bar timestamps are bar OPEN times in UTC.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Dict, List, Tuple
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

# market class -> (time zone, session open, session close), local time
MARKETS: Dict[str, Tuple[str, time, time]] = {
    "US": ("America/New_York", time(9, 30), time(16, 0)),   # US indices, gold, oil
    "DE": ("Europe/Berlin", time(9, 0), time(17, 30)),      # GER40
    "UK": ("Europe/London", time(8, 0), time(16, 30)),      # UK100
    "FX": ("Europe/London", time(8, 0), time(16, 0)),       # FX majors, London session
}

_US = re.compile(r"500|SPX|NAS|NDX|US100|USTEC|US30|DJ|WS30|XAU|GOLD|OIL|WTI|XTI|BRENT|XBR")
_DE = re.compile(r"GER|DAX|DE30|DE40")
_UK = re.compile(r"UK100|FTSE|UK\.")


_CCY = {"USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF", "SEK", "NOK", "DKK", "SGD",
        "HKD", "MXN", "ZAR", "PLN", "TRY", "CNH"}


def market_of(symbol: str) -> str:
    """Market class from the broker symbol name (suffixes like .cash or .m are fine)."""
    s = symbol.upper()
    if re.match(r"[A-Z]{6}([._-].*)?$", s) and s[:3] in _CCY and s[3:6] in _CCY:
        return "FX"                       # checked first: "USDJPY" contains "DJ"
    if _DE.search(s):
        return "DE"
    if _UK.search(s):
        return "UK"
    if _US.search(s):
        return "US"
    raise ValueError(f"unknown market for {symbol!r}; add it to sessions.MARKETS rules")


@dataclass
class SessionData:
    symbol: str
    market: str
    dates: List[date]          # local session dates, ascending
    open: np.ndarray           # (n_days, n_bars)
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    spread: np.ndarray         # in price units
    bar_minutes: int

    @property
    def n_bars(self) -> int:
        return self.close.shape[1]

    def __len__(self) -> int:
        return len(self.dates)


def build_sessions(df: pd.DataFrame, symbol: str, market: str, bar_minutes: int = 5,
                   max_missing: float = 0.10) -> SessionData:
    """Slice bars (UTC index; open/high/low/close/volume/spread_price) into complete sessions.

    A session is kept if its first bar is present and at most `max_missing` of its bars
    are missing (half days and broken days are dropped). Missing bars are filled flat from
    the previous close with zero volume.
    """
    tz, t_open, t_close = MARKETS[market]
    local = df.index.tz_convert(ZoneInfo(tz))
    mins = local.hour * 60 + local.minute
    open_m = t_open.hour * 60 + t_open.minute
    close_m = t_close.hour * 60 + t_close.minute
    n_bars = (close_m - open_m) // bar_minutes
    in_sess = (mins >= open_m) & (mins < close_m) & ((mins - open_m) % bar_minutes == 0)
    sub = df[in_sess]
    slot = ((mins[in_sess] - open_m) // bar_minutes).astype(int)
    day = pd.Index(local[in_sess].date, name="day")
    fields = {}
    for col in ("open", "high", "low", "close", "volume", "spread_price"):
        series = sub[col] if col in sub else pd.Series(0.0, index=sub.index)
        tbl = pd.DataFrame({"day": day, "slot": slot, "v": series.to_numpy()})
        tbl = tbl.drop_duplicates(["day", "slot"], keep="last")
        fields[col] = tbl.pivot(index="day", columns="slot", values="v").reindex(
            columns=range(n_bars))
    close = fields["close"]
    keep = close[0].notna() & (close.notna().sum(axis=1) >= (1 - max_missing) * n_bars)
    days = close.index[keep]
    c = close.loc[days].ffill(axis=1)
    missing = fields["open"].loc[days].isna()
    o = fields["open"].loc[days].where(~missing, c.shift(1, axis=1))
    o = o.fillna(c)
    h = fields["high"].loc[days].where(~missing, c)
    lo = fields["low"].loc[days].where(~missing, c)
    v = fields["volume"].loc[days].fillna(0.0)
    sp = fields["spread_price"].loc[days].ffill(axis=1).bfill(axis=1).fillna(0.0)
    return SessionData(symbol, market, list(days), o.to_numpy(float), h.to_numpy(float),
                       lo.to_numpy(float), c.to_numpy(float), v.to_numpy(float),
                       sp.to_numpy(float), bar_minutes)


def session_bounds_utc(d: date, market: str) -> Tuple[datetime, datetime]:
    """UTC open and close of one session date (for reports and tests)."""
    tz, t_open, t_close = MARKETS[market]
    z = ZoneInfo(tz)
    return (datetime.combine(d, t_open, z).astimezone(ZoneInfo("UTC")),
            datetime.combine(d, t_close, z).astimezone(ZoneInfo("UTC")))
