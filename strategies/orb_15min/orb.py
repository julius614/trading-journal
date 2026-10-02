"""15-minute Opening Range Breakout (ORB), "Max way" rules.

Rules (see knowledge-base/strategies/orb-15min-max/README.md for sources/assumptions):
- Opening range (OR) = high/low of the first 15-minute candle, wicks included.
- A breakout only counts on a 15-minute candle CLOSE outside the OR (wick pokes don't).
- Entry modes:
    breakout : enter at the close of the first candle that closes outside the OR.
    bnr      : break-and-retest - after a breakout close, wait for a candle that comes
               back to the broken level (within tolerance), holds it, and closes back
               in the breakout direction; enter at that close.
- Failed breakout ("X"): a candle closing back inside the OR. Before entry it cancels the
  setup; after entry it exits the trade (if exit_on_failed).
- Stop: OR midline ("mid") or opposite side of the OR ("opposite").
- Target: a multiple of risk (R) or None = hold to the end of the session.
- One trade per day. If stop and target are both touched in the same bar, the stop is
  assumed to hit first (conservative, since bar data can't show the order).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class ORBConfig:
    session_start: str = "09:30"
    session_end: str = "16:00"
    mode: str = "breakout"            # "breakout" | "bnr"
    stop: str = "mid"                 # "mid" | "opposite"
    target_r: Optional[float] = 2.0   # None = hold to the end of the session
    exit_on_failed: bool = True       # exit when a bar closes back inside the OR
    allow_long: bool = True
    allow_short: bool = True
    use_bias: bool = False            # trade only in the direction of the bias (see below)
    max_or_width_pct: Optional[float] = None  # skip days with a wider OR (choppy filter)
    min_or_width_pct: Optional[float] = None  # skip days with a narrower OR
    retest_tolerance: float = 0.10    # BNR: retest counts within this fraction of OR width
    bnr_max_bars: int = 8             # BNR: retest must come within N bars of the break
    slippage: float = 0.0             # price units per share, charged on entry and exit
    commission: float = 0.0           # price units per share, round trip


# ---------------------------------------------------------------- data loading

_TIME_COLS = ("datetime", "timestamp", "time", "date")


def load_csv(path: str, tz: Optional[str] = "America/New_York") -> pd.DataFrame:
    """Load an intraday OHLCV CSV. Needs a datetime column plus open/high/low/close.

    Timezone-aware timestamps (or Unix seconds, as TradingView exports) are converted to
    `tz`; naive timestamps are assumed to be in exchange time already.
    """
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    tcol = next((c for c in _TIME_COLS if c in df.columns), None)
    if tcol is None:
        raise ValueError(f"No datetime column found; expected one of {_TIME_COLS}")
    missing = {"open", "high", "low", "close"} - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")
    if pd.api.types.is_numeric_dtype(df[tcol]):
        idx = pd.to_datetime(df[tcol], unit="s", utc=True)
    else:
        raw = df[tcol].astype(str).str.strip()
        has_tz = raw.str.contains(r"(?:Z|[+-]\d{2}:?\d{2})$").any()
        idx = pd.to_datetime(raw, utc=has_tz)
    if idx.dt.tz is not None:
        idx = (idx.dt.tz_convert(tz) if tz else idx).dt.tz_localize(None)
    out = df[["open", "high", "low", "close"]].astype(float)
    out.index = pd.DatetimeIndex(idx)
    return out.sort_index()


def to_15min(df: pd.DataFrame, cfg: ORBConfig = ORBConfig()) -> pd.DataFrame:
    """Keep regular-session bars and resample to 15-minute candles."""
    sess = df.between_time(cfg.session_start, cfg.session_end, inclusive="left")
    bars = sess.resample("15min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    )
    return bars.dropna()


# ---------------------------------------------------------------- backtest

def _bias(or_mid: float, prev_or_mid: Optional[float]) -> int:
    """+1 if today's OR formed above yesterday's (by midline), -1 if below, 0 if unknown."""
    if prev_or_mid is None:
        return 0
    return 1 if or_mid > prev_or_mid else -1 if or_mid < prev_or_mid else 0


def _find_entry(day: pd.DataFrame, orh: float, orl: float, cfg: ORBConfig):
    """Return (bar position, direction, entry type) of the first valid entry, or None."""
    width = orh - orl
    tol = cfg.retest_tolerance * width
    pending = None  # (direction, bar position of the breakout) for BNR
    for i in range(1, len(day)):
        c, h, l = day["close"].iat[i], day["high"].iat[i], day["low"].iat[i]
        if cfg.mode == "breakout":
            if c > orh and cfg.allow_long:
                return i, 1, "breakout"
            if c < orl and cfg.allow_short:
                return i, -1, "breakout"
            continue
        # break-and-retest
        if pending is None:
            if c > orh and cfg.allow_long:
                pending = (1, i)
            elif c < orl and cfg.allow_short:
                pending = (-1, i)
            continue
        d, brk = pending
        if (d == 1 and c <= orh) or (d == -1 and c >= orl):
            pending = None  # failed breakout: closed back inside the range
            # the same bar may break the other side
            if c < orl and cfg.allow_short:
                pending = (-1, i)
            elif c > orh and cfg.allow_long:
                pending = (1, i)
            continue
        if i - brk > cfg.bnr_max_bars:
            pending = None
            continue
        if d == 1 and l <= orh + tol:
            return i, 1, "bnr"
        if d == -1 and h >= orl - tol:
            return i, -1, "bnr"
    return None


def backtest(bars: pd.DataFrame, cfg: ORBConfig = ORBConfig()) -> pd.DataFrame:
    """Run the ORB rules over 15-minute bars. Returns one row per trade."""
    trades = []
    prev_or_mid = None
    for date, day in bars.groupby(bars.index.date):
        if len(day) < 2:
            continue
        orh, orl = day["high"].iat[0], day["low"].iat[0]
        mid = (orh + orl) / 2
        width_pct = (orh - orl) / mid * 100 if mid else 0.0
        bias = _bias(mid, prev_or_mid)
        prev_or_mid = mid

        if cfg.max_or_width_pct is not None and width_pct > cfg.max_or_width_pct:
            continue
        if cfg.min_or_width_pct is not None and width_pct < cfg.min_or_width_pct:
            continue
        found = _find_entry(day, orh, orl, cfg)
        if found is None:
            continue
        i, d, etype = found
        if cfg.use_bias and bias != d:
            continue

        entry = day["close"].iat[i] + d * cfg.slippage
        stop = mid if cfg.stop == "mid" else (orl if d == 1 else orh)
        risk = (entry - stop) * d
        if risk <= 0:
            continue
        target = entry + d * cfg.target_r * risk if cfg.target_r else None

        exit_px, reason = None, None
        for j in range(i + 1, len(day)):
            o, h, l, c = (day[k].iat[j] for k in ("open", "high", "low", "close"))
            stop_hit = l <= stop if d == 1 else h >= stop
            tgt_hit = target is not None and (h >= target if d == 1 else l <= target)
            if stop_hit:  # checked first: conservative when both touch in one bar
                gap = o < stop if d == 1 else o > stop
                exit_px, reason = (o if gap else stop), "stop"
                break
            if tgt_hit:
                gap = o > target if d == 1 else o < target
                exit_px, reason = (o if gap else target), "target"
                break
            if cfg.exit_on_failed and ((d == 1 and c <= orh) or (d == -1 and c >= orl)):
                exit_px, reason = c, "failed"
                break
        if exit_px is None:  # no exit triggered: close at the end of the session
            j = len(day) - 1
            exit_px, reason = day["close"].iat[j], "eod"
        exit_px -= d * cfg.slippage
        pnl = (exit_px - entry) * d - cfg.commission

        trades.append({
            "date": pd.Timestamp(date),
            "side": "long" if d == 1 else "short",
            "entry_type": etype,
            "bias": {1: "bull", -1: "bear", 0: "none"}[bias],
            "or_high": orh, "or_low": orl, "or_width_pct": round(width_pct, 4),
            "entry_time": day.index[i], "entry_price": entry,
            "stop": stop, "target": target,
            "exit_time": day.index[j], "exit_price": exit_px, "exit_reason": reason,
            "pnl_per_share": pnl, "r_multiple": pnl / risk,
        })
    return pd.DataFrame(trades)


# ---------------------------------------------------------------- statistics

def summarize(trades: pd.DataFrame) -> dict:
    """Headline stats in R multiples."""
    if trades.empty:
        return {"trades": 0}
    r = trades["r_multiple"]
    wins, losses = r[r > 0], r[r <= 0]
    equity = r.cumsum()
    max_dd = (equity - equity.cummax().clip(lower=0)).min()
    return {
        "trades": int(len(r)),
        "win_rate": round(len(wins) / len(r), 4),
        "expectancy_r": round(r.mean(), 4),
        "total_r": round(r.sum(), 4),
        "profit_factor": round(wins.sum() / -losses.sum(), 4) if losses.sum() < 0 else float("inf"),
        "max_drawdown_r": round(float(max_dd), 4),
        "avg_win_r": round(wins.mean(), 4) if len(wins) else 0.0,
        "avg_loss_r": round(losses.mean(), 4) if len(losses) else 0.0,
    }


def breakdown(trades: pd.DataFrame, by: str) -> pd.DataFrame:
    """Stats per group, e.g. by='year' or by='side'."""
    if trades.empty:
        return pd.DataFrame()
    key = trades["date"].dt.year if by == "year" else trades[by]
    return pd.DataFrame({k: summarize(g) for k, g in trades.groupby(key)}).T
