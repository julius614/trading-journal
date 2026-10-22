"""The BACKTEST_SPEC.md setups that our data can test (S1B, S2-S9).

Every function takes ``markets`` ({symbol: M5 DataFrame, UTC bar-open index, columns open,
high, low, close, volume, spread_price}) plus one parameter combination and returns a list
of engine.Trade. Signals use only bars that have closed; fills are at the next bar's open
or later (engine rule 1). Interpretations of loose spec wording are marked "interpretation".
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from datetime import time, timedelta
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .engine import Trade, pip_size, walk_exit

NY, LDN, TKY, BER = "America/New_York", "Europe/London", "Asia/Tokyo", "Europe/Berlin"
BAR = pd.Timedelta(minutes=5)


def grid(**axes) -> List[Dict[str, object]]:
    keys = list(axes)
    return [dict(zip(keys, vals)) for vals in itertools.product(*axes.values())]


# ----------------------------------------------------------------------- US cash session
@dataclass
class Session:
    """Complete 09:30-16:00 ET sessions as (days x 78) matrices. Half-days, holidays and
    days with any missing 5-minute bar (a gap > 5 min) are dropped."""
    dates: List[pd.Timestamp]
    t: np.ndarray       # bar open times, int64 ns UTC
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    v: np.ndarray
    s: np.ndarray       # bar spread in price units (0 = unknown)


N_US = 78


def us_session(df: pd.DataFrame) -> Session:
    local = df.index.tz_convert(NY)
    slot = (local.hour * 60 + local.minute - 570) // 5
    keep = (slot >= 0) & (slot < N_US) & (local.minute % 5 == 0)
    d = df[keep]
    day = pd.DatetimeIndex(local[keep].date)
    frame = pd.DataFrame({"day": day, "slot": slot[keep], "t": d.index.as_unit("ns").asi8,
                          "o": d["open"].to_numpy(), "h": d["high"].to_numpy(),
                          "l": d["low"].to_numpy(), "c": d["close"].to_numpy(),
                          "v": d["volume"].to_numpy(), "s": d["spread_price"].to_numpy()})
    counts = frame.groupby("day")["slot"].nunique()
    full = counts[counts == N_US].index
    frame = frame[frame["day"].isin(full)].sort_values(["day", "slot"])
    n = len(full)
    m = {k: frame[k].to_numpy().reshape(n, N_US) for k in ("t", "o", "h", "l", "c", "v", "s")}
    return Session(list(full), **m)


def _ts(ns: int) -> pd.Timestamp:
    return pd.Timestamp(int(ns), tz="UTC")


# ----------------------------------------------------------------------- S1B ORB (QQQ proxy)
def s1b(markets: Dict[str, pd.DataFrame], or_min: int, sessions: Dict[str, Session] = None,
        **_) -> List[Trade]:
    """Variant 1B: OR = first or_min minutes; market entry at the next bar open in the OR
    candle's direction; stop on the other side of the OR; target 10R; else exit at 16:00."""
    out = []
    k = or_min // 5
    for sym in markets:
        ss = sessions[sym]
        for i, day in enumerate(ss.dates):
            o, h, l, c = ss.o[i], ss.h[i], ss.l[i], ss.c[i]
            ro, rc = o[0], c[k - 1]
            if rc == ro:
                continue
            side = 1 if rc > ro else -1
            hi, lo = h[:k].max(), l[:k].min()
            entry = o[k]
            stop = lo if side == 1 else hi
            if (entry - stop) * side <= 0:
                continue
            target = entry + side * 10 * abs(entry - stop)
            j, px, kind = walk_exit(o, h, l, c, k, N_US - 1, side, stop, target, 0.0)
            out.append(Trade(sym, side, _ts(ss.t[i, k]), entry, "market",
                             _ts(ss.t[i, j]) + BAR, px, kind, stop, ss.s[i, k], ss.s[i, j]))
    return out


# ----------------------------------------------------------------------- S2/S3 momentum
def _momentum_signals(ss: Session):
    """r1: previous 16:00 close -> 10:00 (close of the 09:55 bar); r12: 15:00 -> 15:30."""
    prev_ok = np.zeros(len(ss.dates), bool)
    prev_close = np.full(len(ss.dates), np.nan)
    for i in range(1, len(ss.dates)):
        if (ss.dates[i] - ss.dates[i - 1]).days <= 4:
            prev_ok[i] = True
            prev_close[i] = ss.c[i - 1, -1]
    r1 = ss.c[:, 5] / prev_close - 1
    r12 = ss.c[:, 71] / ss.c[:, 65] - 1
    return r1, r12, prev_ok


def _small_r1(r1: np.ndarray) -> np.ndarray:
    """True where |r1| is below the 20th percentile of the previous 250 days (no look-ahead)."""
    a = pd.Series(np.abs(r1))
    q = a.shift(1).rolling(250, min_periods=100).quantile(0.2)
    return (a < q).to_numpy()


def s2(markets: Dict[str, pd.DataFrame], variant: str, skip_small: bool,
       sessions: Dict[str, Session] = None, only_dates: Optional[set] = None, **_) -> List[Trade]:
    """At 15:30 (open of the 15:30 bar) trade the sign of r1; exit at 16:00 (close of the
    15:55 bar). Variant 2B: only if r1 and r12 share a sign. 1x notional, no stop."""
    out = []
    for sym in markets:
        ss = sessions[sym]
        r1, r12, ok = _momentum_signals(ss)
        small = _small_r1(r1) if skip_small else np.zeros(len(r1), bool)
        for i, day in enumerate(ss.dates):
            if not ok[i] or not np.isfinite(r1[i]) or r1[i] == 0 or small[i]:
                continue
            if only_dates is not None and day not in only_dates:
                continue
            side = 1 if r1[i] > 0 else -1
            if variant == "2B" and np.sign(r12[i]) != side:
                continue
            out.append(Trade(sym, side, _ts(ss.t[i, 72]), ss.o[i, 72], "market",
                             _ts(ss.t[i, 77]) + BAR, ss.c[i, 77], "close",
                             spread_in=ss.s[i, 72], spread_out=ss.s[i, 77]))
    return out


def s3(markets, event: str, variant: str, sessions=None, events: pd.DataFrame = None,
       **_) -> List[Trade]:
    """Strategy 2 on macro event days only (data/events.csv)."""
    ev = events if event == "all" else events[events["event"] == event]
    days = set(pd.DatetimeIndex(pd.to_datetime(ev["date"])))
    return s2(markets, variant=variant, skip_small=False, sessions=sessions, only_dates=days)


# ----------------------------------------------------------------------- S4 VWAP
def s4(markets, check_every: int, buffer: float, sessions=None, **_) -> List[Trade]:
    """Session VWAP of typical price from 09:30 (tick volume; equal weights on days without
    volume). From the 09:35 check, every check_every minutes: close above VWAP*(1+buffer)
    and not long -> long; below VWAP*(1-buffer) and not short -> short. Orders fill at the
    next bar open. Flat at 16:00. 1x notional, no stop."""
    out = []
    for sym in markets:
        ss = sessions[sym]
        tp = (ss.h + ss.l + ss.c) / 3
        for i in range(len(ss.dates)):
            v = ss.v[i] if ss.v[i].sum() > 0 else np.ones(N_US)
            vwap = np.cumsum(tp[i] * v) / np.maximum(np.cumsum(v), 1e-12)
            pos, entry_j = 0, None
            for j in range(N_US - 1):            # signal at the close of bar j
                if (5 * (j + 1)) % check_every:
                    continue
                want = 1 if ss.c[i, j] > vwap[j] * (1 + buffer) else (
                    -1 if ss.c[i, j] < vwap[j] * (1 - buffer) else pos)
                if want != pos:
                    f = j + 1
                    if pos != 0:
                        out.append(Trade(sym, pos, _ts(ss.t[i, entry_j]), ss.o[i, entry_j],
                                         "market", _ts(ss.t[i, f]), ss.o[i, f], "market",
                                         spread_in=ss.s[i, entry_j], spread_out=ss.s[i, f]))
                    pos, entry_j = want, f
            if pos != 0:
                out.append(Trade(sym, pos, _ts(ss.t[i, entry_j]), ss.o[i, entry_j], "market",
                                 _ts(ss.t[i, -1]) + BAR, ss.c[i, -1], "close",
                                 spread_in=ss.s[i, entry_j], spread_out=ss.s[i, -1]))
    return out


# ----------------------------------------------------------------------- FX clock helpers
def weekdays(df: pd.DataFrame) -> pd.DatetimeIndex:
    d = pd.date_range(df.index[0].date(), df.index[-1].date(), freq="D")
    return d[d.dayofweek < 5]


def bars_at(df: pd.DataFrame, days: pd.DatetimeIndex, tz: str, at: time,
            shift: timedelta = timedelta(0)) -> pd.DataFrame:
    """The M5 bar whose OPEN is at local wall time `at` (+shift) on each day (NaN if missing).
    DST is handled by the time-zone library."""
    wall = (days + pd.Timedelta(hours=at.hour, minutes=at.minute) + shift)
    utc = wall.tz_localize(tz, ambiguous="NaT", nonexistent="NaT").tz_convert("UTC")
    got = df.reindex(utc)
    got.index = days
    got["t"] = utc
    return got


# ----------------------------------------------------------------------- S5 London fix
def s5(markets, exit_time: str, min_move: float, days: str, **_) -> List[Trade]:
    """pre_move = 15:30 -> 15:59 London (open of 15:30 bar -> close of 15:55 bar). At 16:05
    enter opposite (open of the 16:05 bar); exit at exit_time (open of that bar)."""
    out = []
    eh, em = map(int, exit_time.split(":"))
    for sym, df in markets.items():
        d = weekdays(df)
        a = bars_at(df, d, LDN, time(15, 30))
        b = bars_at(df, d, LDN, time(15, 55))
        e = bars_at(df, d, LDN, time(16, 5))
        x = bars_at(df, d, LDN, time(eh, em))
        ok = a["open"].notna() & b["close"].notna() & e["open"].notna() & x["open"].notna()
        traded = d[ok.to_numpy()]
        if days != "all":
            per_month = pd.Series(traded, index=traded).groupby(traded.to_period("M"))
            n = 1 if days == "last1" else 3
            keep = set(itertools.chain.from_iterable(g.iloc[-n:] for _, g in per_month))
        pip = pip_size(sym)
        for day in traded:
            if days != "all" and day not in keep:
                continue
            pre = b.at[day, "close"] - a.at[day, "open"]
            if pre == 0 or abs(pre) < min_move * pip:
                continue
            side = -1 if pre > 0 else 1
            out.append(Trade(sym, side, e.at[day, "t"], e.at[day, "open"], "market",
                             x.at[day, "t"], x.at[day, "open"], "time"))
    return out


# ----------------------------------------------------------------------- S6 Tokyo/ECB fix
FIXES = {"Tokyo": (TKY, time(9, 55)), "ECB": (BER, time(14, 15))}
USD_SIGN = {"EURUSD": -1, "GBPUSD": -1, "AUDUSD": -1, "USDJPY": 1}   # +1 = pair up means USD up


def s6(markets, window: int, fix: str, basket: bool = False, **_) -> List[Trade]:
    """pre_move = USD return over the `window` hours before the fix (open of the bar at
    fix-window -> open of the bar at the fix). At fix+5 min enter opposite (USD up -> sell
    USD); exit `window` hours later. Single pairs, or the equal-weight 4-pair USD basket
    (0.25 notional per leg, all legs needed). Tokyo and ECB trades never overlap in time."""
    out = []
    fixes = ["Tokyo", "ECB"] if fix == "both" else [fix]
    w = timedelta(hours=window)
    for f in fixes:
        tz, at = FIXES[f]
        legs = {}
        for sym, df in markets.items():
            d = weekdays(df)
            pre0 = bars_at(df, d, tz, at, -w)["open"]
            pre1 = bars_at(df, d, tz, at)["open"]
            ent = bars_at(df, d, tz, at, timedelta(minutes=5))
            ext = bars_at(df, d, tz, at, timedelta(minutes=5) + w)
            legs[sym] = pd.DataFrame({"ret": pre1 / pre0 - 1, "et": ent["t"], "eo": ent["open"],
                                      "xt": ext["t"], "xo": ext["open"]}).dropna()
        if basket:
            common = sorted(set.intersection(*(set(v.index) for v in legs.values())))
            for day in common:
                usd = np.mean([USD_SIGN[s] * legs[s].at[day, "ret"] for s in legs])
                if usd == 0:
                    continue
                for s, lg in legs.items():
                    side = -int(np.sign(usd)) * USD_SIGN[s]
                    out.append(Trade(s, side, lg.at[day, "et"], lg.at[day, "eo"], "market",
                                     lg.at[day, "xt"], lg.at[day, "xo"], "time",
                                     tag=f"{f} basket", weight=0.25))
        else:
            for s, lg in legs.items():
                for day, r in lg.iterrows():
                    if r["ret"] == 0:
                        continue
                    out.append(Trade(s, -int(np.sign(r["ret"])), r["et"], r["eo"], "market",
                                     r["xt"], r["xo"], "time", tag=f))
    return sorted(out, key=lambda t: t.entry_time)


# ----------------------------------------------------------------------- shared FX bar arrays
@dataclass
class Bars:
    t: pd.DatetimeIndex
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    atr: np.ndarray
    day: np.ndarray          # London date as int (days since epoch)
    in_window: np.ndarray    # 07:00 <= London time < 17:00
    run_end: np.ndarray      # last bar index before the next gap > 6h (weekend / holiday)
    step: pd.Timedelta = BAR


def atr14(h, l, c) -> np.ndarray:
    pc = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.vstack([h - l, np.abs(h - pc), np.abs(l - pc)]), axis=0)
    return pd.Series(tr).rolling(14, min_periods=14).mean().to_numpy()


def make_bars(df: pd.DataFrame, step: pd.Timedelta = BAR, gap_hours: float = 6) -> Bars:
    o, h, l, c = (df[k].to_numpy(dtype=float, copy=True) for k in ("open", "high", "low", "close"))
    local = df.index.tz_convert(LDN)
    mins = local.hour * 60 + local.minute
    gap = np.diff(df.index.as_unit("ns").asi8) > gap_hours * 3600 * 10**9
    run_end = np.empty(len(df), np.int64)
    end = len(df) - 1
    for i in range(len(df) - 1, -1, -1):
        if i < len(df) - 1 and gap[i]:
            end = i
        run_end[i] = end
    day = pd.DatetimeIndex(local.date).as_unit("ns").asi8 // (86400 * 10**9)
    return Bars(df.index, o, h, l, c, np.array(atr14(h, l, c)), day,
                np.asarray((mins >= 420) & (mins < 1020)), run_end, step)


def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    r = df.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"})
    return r.dropna()


def round_step(sym: str) -> float:
    return 1.0 if sym.endswith("JPY") else 0.01


# ----------------------------------------------------------------------- S7 round-number fade
APPROACH_ZONE_PIPS = 15     # interpretation: an "approach" = first close within 15 pips of the
LOOKBACK = 12               # level today (07:00-17:00 London); trend over the last 12 bars


def approaches(sym: str, b: Bars) -> List[tuple]:
    """First approach per (London day, round level): (bar, level, side_from) where
    side_from = -1 approached from below, +1 from above. Independent of the sweep."""
    step, pip = round_step(sym), pip_size(sym)
    zone = APPROACH_ZONE_PIPS * pip
    up = np.ceil(b.c / step - 1e-9) * step
    dn = np.floor(b.c / step + 1e-9) * step
    seen, out = set(), []
    for i in np.flatnonzero(b.in_window):
        for lvl, frm in ((up[i], -1), (dn[i], 1)):
            dist = abs(lvl - b.c[i])
            if dist == 0 or dist > zone:
                continue
            key = (b.day[i], round(lvl / step))
            if key in seen:
                continue
            seen.add(key)
            out.append((i, lvl, frm))
    return out


def s7(markets, entry_buffer: float, stop_pips: float, target_R: float, approach_atr: float,
       bars: Dict[str, Bars] = None, appr: Dict[str, list] = None, **_) -> List[Trade]:
    """Fade the first approach of a round level after a trend into it: limit order
    entry_buffer pips before the level (valid 12 bars, needs a 1-tick trade-through),
    stop stop_pips beyond the level, target target_R x risk, 4h time stop. One position per
    pair at a time."""
    out = []
    for sym in markets:
        b, pip = bars[sym], pip_size(sym)
        tick = pip / 10
        busy_until = -1
        for i, lvl, frm in appr[sym]:
            if i <= busy_until or i < LOOKBACK or not np.isfinite(b.atr[i]):
                continue
            move = b.c[i] - b.c[i - LOOKBACK]
            if -frm * move < approach_atr * b.atr[i]:      # must trend toward the level
                continue
            side = frm                                      # from below -> sell (-1)
            limit = lvl + frm * entry_buffer * pip
            if (limit - b.c[i]) * -frm <= 0:                # already through the limit
                continue
            stop = lvl - frm * stop_pips * pip
            last = min(i + 12, b.run_end[i])
            fill = None
            for k in range(i + 1, last + 1):
                if (side == -1 and b.h[k] >= limit + 0.999 * tick) or (side == 1 and b.l[k] <= limit - 0.999 * tick):
                    fill = k
                    break
            if fill is None:
                busy_until = last
                continue
            risk = abs(limit - stop)
            target = limit + side * target_R * risk
            end = min(fill + 47, b.run_end[fill])
            if (side == -1 and b.h[fill] >= stop) or (side == 1 and b.l[fill] <= stop):
                j, px, kind = fill, stop, "stop"            # stop first on the fill bar
            elif fill == end:
                j, px, kind = fill, b.c[fill], "close"
            else:
                j, px, kind = walk_exit(b.o, b.h, b.l, b.c, fill + 1, end, side, stop, target, tick)
            out.append(Trade(sym, side, b.t[fill], limit, "limit", b.t[j] + BAR, px,
                             "time" if kind == "close" else kind, stop, tag=f"{lvl:.4f}"))
            busy_until = j
    return out


# ----------------------------------------------------------------------- S8 round-number break
def breaks(sym: str, b: Bars, break_pips: float) -> List[tuple]:
    """(bar, level, side): a 5-min bar CLOSES beyond a round level by >= break_pips after the
    previous close was on the other side; first break per (day, level, direction)."""
    step, pip = round_step(sym), pip_size(sym)
    seen, out = set(), []
    pc = np.r_[np.nan, b.c[:-1]]
    for i in np.flatnonzero(b.in_window):
        if not np.isfinite(pc[i]):
            continue
        lo, hi = sorted((pc[i], b.c[i]))
        k0, k1 = math.floor(lo / step) + 1, math.floor(hi / step + 1e-9)
        for k in range(k0, k1 + 1):
            lvl = k * step
            side = 1 if b.c[i] > pc[i] else -1
            if (b.c[i] - lvl) * side < break_pips * pip or (pc[i] - lvl) * side >= 0:
                continue
            key = (b.day[i], k, side)
            if key in seen:
                continue
            seen.add(key)
            out.append((i, lvl, side))
    return out


def s8(markets, break_pips: float, stop_pips: float, target_R: float,
       bars: Dict[str, Bars] = None, **_) -> List[Trade]:
    """Market entry at the next bar open in the break direction; stop stop_pips back on the
    other side of the level; target target_R x risk; 2h time stop."""
    out = []
    for sym in markets:
        b, pip = bars[sym], pip_size(sym)
        busy_until = -1
        for i, lvl, side in breaks(sym, b, break_pips):
            k = i + 1
            if i <= busy_until or k > b.run_end[i]:
                continue
            entry, stop = b.o[k], lvl - side * stop_pips * pip
            if (entry - stop) * side <= 0:
                continue
            target = entry + side * target_R * abs(entry - stop)
            end = min(k + 23, b.run_end[k])
            j, px, kind = walk_exit(b.o, b.h, b.l, b.c, k, end, side, stop, target, pip / 10)
            out.append(Trade(sym, side, b.t[k], entry, "market", b.t[j] + BAR, px,
                             "time" if kind == "close" else kind, stop, tag=f"{lvl:.4f}"))
            busy_until = j
    return out


def level_outcomes(markets, bars: Dict[str, Bars], dist_pips: float = 20,
                   horizon_bars: int = 24) -> pd.DataFrame:
    """Model-free S7-vs-S8 check: after the first TOUCH of a round level each day
    (07:00-17:00 London), does price first go dist_pips through the level (break) or
    dist_pips back (reverse) within 2 hours? Same-bar ties count as undecided."""
    rows = []
    for sym in markets:
        b, step, pip = bars[sym], round_step(sym), pip_size(sym)
        seen = set()
        pc = np.r_[np.nan, b.c[:-1]]
        for i in np.flatnonzero(b.in_window):
            if not np.isfinite(pc[i]):
                continue
            for lvl, frm in ((math.ceil(pc[i] / step) * step, -1), (math.floor(pc[i] / step) * step, 1)):
                touched = (frm == -1 and b.h[i] >= lvl) or (frm == 1 and b.l[i] <= lvl)
                key = (b.day[i], round(lvl / step))
                if not touched or key in seen or lvl == pc[i]:
                    continue
                seen.add(key)
                thr, rev = lvl - frm * dist_pips * pip, lvl + frm * dist_pips * pip
                res = "undecided"
                for k in range(i + 1, min(i + horizon_bars, b.run_end[i]) + 1):
                    br = (b.h[k] >= thr) if frm == -1 else (b.l[k] <= thr)
                    rv = (b.l[k] <= rev) if frm == -1 else (b.h[k] >= rev)
                    if br and rv:
                        break
                    if br or rv:
                        res = "break" if br else "reverse"
                        break
                rows.append({"symbol": sym, "date": b.t[i].date(), "level": lvl, "outcome": res})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------- S9 sweep reversal
def session_of(ts: pd.Timestamp) -> str:
    h = ts.hour
    return "Asia" if (h >= 22 or h < 7) else ("London" if h < 13 else "New York")


def s9(markets, N: int, over: float, target_R: float, stop_buffer: float,
       bars: Dict[str, Bars] = None, spreads: Dict[str, float] = None, **_) -> List[Trade]:
    """Short (mirror for long): high > max(high of previous N bars) by at most over x ATR14,
    close back below it -> sell at the next open; stop = bar high + stop_buffer pips + spread;
    target target_R x risk; 24-bar time stop (and before a weekend gap). One position at a
    time per pair."""
    out = []
    for sym in markets:
        b, pip = bars[sym], pip_size(sym)
        hh = pd.Series(b.h).rolling(N).max().shift(1).to_numpy()
        ll = pd.Series(b.l).rolling(N).min().shift(1).to_numpy()
        short = (b.h > hh) & (b.h - hh <= over * b.atr) & (b.c < hh)
        long_ = (b.l < ll) & (ll - b.l <= over * b.atr) & (b.c > ll)
        busy_until = -1
        for i in np.flatnonzero(short | long_):
            k = i + 1
            if i <= busy_until or k > b.run_end[i] or (short[i] and long_[i]):
                continue
            side = -1 if short[i] else 1
            entry = b.o[k]
            ext = b.h[i] if side == -1 else b.l[i]
            stop = ext - side * (stop_buffer * pip + spreads[sym])
            if (entry - stop) * side <= 0:
                continue
            target = entry + side * target_R * abs(entry - stop)
            end = min(i + 24, b.run_end[k])
            j, px, kind = walk_exit(b.o, b.h, b.l, b.c, k, end, side, stop, target, pip / 10)
            out.append(Trade(sym, side, b.t[k], entry, "market", b.t[j] + b.step, px,
                             "time" if kind == "close" else kind, stop, tag=session_of(b.t[k])))
            busy_until = j
    return out
