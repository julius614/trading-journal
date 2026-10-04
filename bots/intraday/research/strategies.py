"""Three published intraday strategies with their parameters fixed from the papers.

Every strategy is flat at the session close. Decisions use only closed bars; orders fill
at the NEXT bar's open (or at the stop/target price for OR).

NA  Noise-area momentum - Zarattini, Aziz & Barbon (2024), "Beat the Market: An Effective
    Intraday Momentum Strategy for S&P500 ETF (SPY)".
LH  Market intraday momentum - Gao, Han, Li & Zhou (2018, JFE); across futures:
    Baltussen, Da, Lammers & Martens (2021, JFE).
OR  5-minute opening-range breakout - Zarattini, Barbon & Aziz (2023), "Can Day Trading
    Really Be Profitable?".
SW  Liquidity sweep + displacement + fair-value-gap entry (ICT/SMC style; the user's
    "Option A", added 2026-10-04 before any data was seen).
BK  M15 Donchian breakout with ATR stop and chandelier trail (the user's "Option B").

Sizing (applied by the engine): NA and LH target 1% daily volatility from the last 14
sessions' close-to-close returns, leverage capped at 4x. OR risks 1% of equity at the stop,
also capped at 4x. SW and BK follow the user's "passing box": 0.5% risk at the stop
(leverage capped at 10x), at most 2 trades per day per market.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import numpy as np

from .sessions import SessionData

VOL_TARGET = 0.01
MAX_LEVERAGE = 4.0
OR_RISK = 0.01
PASS_RISK = 0.005            # SW / BK risk per trade
PASS_MAX_LEVERAGE = 10.0
MAX_TRADES_PER_DAY = 2       # = "stop after 2 losses" (a third trade never happens)
SW_WINDOW_MINUTES = {"FX": 180, "US": 90}   # 08:00-11:00 London / 09:30-11:00 New York


@dataclass(frozen=True)
class Trade:
    day: int            # row in SessionData
    side: int           # +1 long, -1 short
    entry_slot: int
    exit_slot: int
    entry: float
    exit: float
    leverage: float
    reason: str


@dataclass(frozen=True)
class Params:
    lookback: int = 14              # NA sigma, vol target and OR ATR window (days)
    check_minutes: int = 30         # NA decision interval
    first_minutes: int = 30         # LH signal window after the open
    last_minutes: int = 30          # LH trading window before the close
    or_stop_atr: float = 0.10       # OR stop as a fraction of the 14-day ATR
    or_target_r: float = 10.0       # OR target in multiples of the stop distance
    sw_displacement: float = 1.5    # SW displacement body vs 20-bar average body
    sw_target_r: float = 2.5        # SW target in R
    bk_donchian: int = 20           # BK channel length in M15 bars
    bk_stop_atr: float = 1.5        # BK initial stop in M15 ATR(14)


DEFAULT = Params()


def prev_closes(sd: SessionData) -> np.ndarray:
    """Previous session's close for each day (nan on the first)."""
    last = sd.close[:, -1]
    return np.concatenate([[np.nan], last[:-1]])


def vol_leverage(sd: SessionData, lookback: int) -> np.ndarray:
    """min(4, 1% / std of the last `lookback` close-to-close returns), known before the open."""
    last = sd.close[:, -1]
    r = np.concatenate([[np.nan], last[1:] / last[:-1] - 1.0])
    lev = np.full(len(sd), np.nan)
    for d in range(lookback + 1, len(sd)):
        s = np.nanstd(r[d - lookback:d], ddof=1)
        if s > 0:
            lev[d] = min(MAX_LEVERAGE, VOL_TARGET / s)
    return lev


def noise_area(sd: SessionData, p: Params = DEFAULT) -> List[Trade]:
    n_days, n = sd.close.shape
    step = p.check_minutes // sd.bar_minutes
    if step < 1 or p.check_minutes % sd.bar_minutes:
        raise ValueError("check_minutes must be a multiple of the bar size")
    move = np.abs(sd.close / sd.open[:, :1] - 1.0)
    prev = prev_closes(sd)
    lev = vol_leverage(sd, p.lookback)
    typical = (sd.high + sd.low + sd.close) / 3.0
    trades: List[Trade] = []
    checks = [j for j in range(step - 1, n - 1, step)]       # bar closes at open+30m, +60m...
    for d in range(p.lookback, n_days):
        if not np.isfinite(prev[d]) or not np.isfinite(lev[d]):
            continue
        sigma = move[d - p.lookback:d].mean(axis=0)
        o0 = sd.open[d, 0]
        ub = max(o0, prev[d]) * (1.0 + sigma)
        lb = min(o0, prev[d]) * (1.0 - sigma)
        vol = sd.volume[d]
        cum_v = np.cumsum(vol)
        vwap = np.where(cum_v > 0, np.cumsum(typical[d] * vol) / np.where(cum_v > 0, cum_v, 1),
                        np.cumsum(typical[d]) / np.arange(1, n + 1))
        pos, entry_slot, entry_px = 0, -1, 0.0
        for j in checks:
            c = sd.close[d, j]
            nxt = sd.open[d, j + 1]
            if pos == 1 and c < max(ub[j], vwap[j]):
                trades.append(Trade(d, 1, entry_slot, j + 1, entry_px, nxt, lev[d], "stop"))
                pos = 0
            elif pos == -1 and c > min(lb[j], vwap[j]):
                trades.append(Trade(d, -1, entry_slot, j + 1, entry_px, nxt, lev[d], "stop"))
                pos = 0
            if pos == 0:
                if c > ub[j]:
                    pos, entry_slot, entry_px = 1, j + 1, nxt
                elif c < lb[j]:
                    pos, entry_slot, entry_px = -1, j + 1, nxt
        if pos != 0:
            trades.append(Trade(d, pos, entry_slot, n - 1, entry_px, sd.close[d, n - 1],
                                lev[d], "close"))
    return trades


def late_half_hour(sd: SessionData, p: Params = DEFAULT) -> List[Trade]:
    n_days, n = sd.close.shape
    k_first = p.first_minutes // sd.bar_minutes
    k_last = p.last_minutes // sd.bar_minutes
    if k_first < 1 or k_last < 1 or k_first + k_last > n:
        raise ValueError("bad LH windows")
    prev = prev_closes(sd)
    lev = vol_leverage(sd, p.lookback)
    trades = []
    for d in range(1, n_days):
        if not np.isfinite(prev[d]) or not np.isfinite(lev[d]):
            continue
        r1 = sd.close[d, k_first - 1] / prev[d] - 1.0
        if r1 == 0:
            continue
        side = 1 if r1 > 0 else -1
        e = n - k_last
        trades.append(Trade(d, side, e, n - 1, sd.open[d, e], sd.close[d, n - 1], lev[d],
                            "close"))
    return trades


def opening_range(sd: SessionData, p: Params = DEFAULT) -> List[Trade]:
    n_days, n = sd.close.shape
    prev = prev_closes(sd)
    day_high, day_low = sd.high.max(axis=1), sd.low.min(axis=1)
    tr = np.maximum(day_high - day_low,
                    np.maximum(np.abs(day_high - prev), np.abs(day_low - prev)))
    trades = []
    for d in range(p.lookback + 1, n_days):
        atr = np.nanmean(tr[d - p.lookback:d])
        o, c = sd.open[d, 0], sd.close[d, 0]
        if not np.isfinite(atr) or atr <= 0 or c == o:
            continue
        side = 1 if c > o else -1
        entry = sd.open[d, 1]
        dist = p.or_stop_atr * atr
        stop = entry - side * dist
        target = entry + side * p.or_target_r * dist
        lev = min(MAX_LEVERAGE, OR_RISK / (dist / entry))
        exit_px, exit_slot, reason = sd.close[d, n - 1], n - 1, "close"
        for j in range(1, n):
            hit_stop = sd.low[d, j] <= stop if side == 1 else sd.high[d, j] >= stop
            hit_tgt = sd.high[d, j] >= target if side == 1 else sd.low[d, j] <= target
            if hit_stop:     # stop first if both touch in one bar (conservative)
                gap = sd.open[d, j] if (side == 1 and sd.open[d, j] < stop) or \
                    (side == -1 and sd.open[d, j] > stop) else stop
                exit_px, exit_slot, reason = gap, j, "stop"
                break
            if hit_tgt:
                exit_px, exit_slot, reason = target, j, "target"
                break
        trades.append(Trade(d, side, 1, exit_slot, entry, exit_px, lev, reason))
    return trades


def _pass_leverage(entry: float, stop: float) -> float:
    return min(PASS_MAX_LEVERAGE, PASS_RISK / (abs(entry - stop) / entry))


def _manage(sd: SessionData, d: int, side: int, start: int, entry: float, stop: float,
            target: float = float("nan"), trail_atr: float = float("nan"),
            trail_mult: float = 2.0):
    """Walk bars from `start` (the fill bar) to the close. Stop first if stop and target
    touch in one bar. With trail_atr set: once price has gone +1R, the stop trails at the
    best close since entry -/+ trail_mult x ATR (it only ever tightens).
    Returns (exit_slot, exit_price, reason)."""
    n = sd.n_bars
    risk = abs(entry - stop)
    best = entry
    armed = False
    for j in range(start, n):
        o, h, lo, c = sd.open[d, j], sd.high[d, j], sd.low[d, j], sd.close[d, j]
        if (side == 1 and lo <= stop) or (side == -1 and h >= stop):
            px = o if (j > start and ((side == 1 and o < stop) or (side == -1 and o > stop))) \
                else stop
            return j, px, "stop"
        if np.isfinite(target) and ((side == 1 and h >= target) or (side == -1 and lo <= target)):
            return j, target, "target"
        if np.isfinite(trail_atr):
            best = max(best, c) if side == 1 else min(best, c)
            if not armed and side * (best - entry) >= risk:
                armed = True
            if armed:
                new = best - side * trail_mult * trail_atr
                stop = max(stop, new) if side == 1 else min(stop, new)
    return n - 1, sd.close[d, n - 1], "close"


def _flat(a: np.ndarray) -> np.ndarray:
    return a.reshape(-1)


def liquidity_sweep(sd: SessionData, p: Params = DEFAULT) -> List[Trade]:
    """SW: the previous session's high/low is swept, price closes back inside within 3
    bars, then within 3 more bars a displacement candle (body >= 1.5x the 20-bar average)
    leaves a 3-bar fair-value gap away from the level. Limit entry at the gap midpoint,
    valid 6 bars; stop beyond the sweep extreme; target 2.5R; flat at the close."""
    if sd.market not in SW_WINDOW_MINUTES:
        return []
    n_days, n = sd.close.shape
    window = SW_WINDOW_MINUTES[sd.market] // sd.bar_minutes
    body = np.abs(_flat(sd.close) - _flat(sd.open))
    csum = np.concatenate([[0.0], np.cumsum(body)])
    trades: List[Trade] = []
    for d in range(1, n_days):
        pdh, pdl = sd.high[d - 1].max(), sd.low[d - 1].min()
        base = d * n
        count = 0
        j = 0
        while j < window and count < MAX_TRADES_PER_DAY:
            hi, lo = sd.high[d, j], sd.low[d, j]
            side = -1 if hi > pdh and not lo < pdl else (1 if lo < pdl and not hi > pdh else 0)
            if side == 0:
                j += 1
                continue
            level = pdh if side == -1 else pdl
            k = next((k for k in range(j, min(j + 4, n))
                      if (sd.close[d, k] < level if side == -1 else sd.close[d, k] > level)), None)
            if k is None:
                j += 1
                continue
            setup = None
            for i in range(max(k + 1, 2), min(k + 4, n)):
                g = base + i
                if g < 20:
                    continue
                avg = (csum[g] - csum[g - 20]) / 20.0
                b = sd.close[d, i] - sd.open[d, i]
                if side == -1 and b < 0 and -b >= p.sw_displacement * avg \
                        and sd.low[d, i - 2] > sd.high[d, i]:
                    setup = (i, (sd.low[d, i - 2] + sd.high[d, i]) / 2.0,
                             sd.high[d, j:i + 1].max())
                    break
                if side == 1 and b > 0 and b >= p.sw_displacement * avg \
                        and sd.high[d, i - 2] < sd.low[d, i]:
                    setup = (i, (sd.high[d, i - 2] + sd.low[d, i]) / 2.0,
                             sd.low[d, j:i + 1].min())
                    break
            if setup is None:
                j += 1
                continue
            i, entry, extreme = setup
            stop = extreme
            if side * (entry - stop) <= 0:
                j = i + 1
                continue
            fill = next((b for b in range(i + 1, min(i + 7, n))
                         if (sd.high[d, b] >= entry if side == -1 else sd.low[d, b] <= entry)), None)
            if fill is None:
                j = i + 1
                continue
            target = entry + side * p.sw_target_r * abs(entry - stop)
            slot, px, reason = _manage(sd, d, side, fill, entry, stop, target)
            trades.append(Trade(d, side, fill, slot, entry, px, _pass_leverage(entry, stop),
                                reason))
            count += 1
            j = slot + 1
    return trades


def donchian_breakout(sd: SessionData, p: Params = DEFAULT) -> List[Trade]:
    """BK: on M15 bars (3 x M5, session bars of consecutive days chained), a close above
    the prior 20-bar high (below the low) enters at the next M5 open. Stop 1.5 x ATR(14);
    after +1R the stop trails at the best close - 2 x ATR. Flat at the close."""
    n_days, n = sd.close.shape
    if n % 3:
        raise ValueError("session length must be a multiple of 15 minutes")
    q = n // 3
    hi = sd.high.reshape(n_days, q, 3).max(axis=2).reshape(-1)
    lo = sd.low.reshape(n_days, q, 3).min(axis=2).reshape(-1)
    cl = sd.close.reshape(n_days, q, 3)[:, :, 2].reshape(-1)
    prev_cl = np.concatenate([[np.nan], cl[:-1]])
    tr = np.nanmax(np.vstack([hi - lo, np.abs(hi - prev_cl), np.abs(lo - prev_cl)]), axis=0)
    L = p.bk_donchian
    trades: List[Trade] = []
    for d in range(n_days):
        count = 0
        free_from = 0                      # M5 slot from which a new entry may fill
        for m in range(q):
            g = d * q + m
            slot = 3 * m + 3               # fill at the open of the next M5 bar
            if count >= MAX_TRADES_PER_DAY or slot >= n or slot < free_from or g < max(L, 15):
                continue
            up = cl[g] > hi[g - L:g].max()
            dn = cl[g] < lo[g - L:g].min()
            if up == dn:
                continue
            side = 1 if up else -1
            atr = tr[g - 14:g].mean()
            if not np.isfinite(atr) or atr <= 0:
                continue
            entry = sd.open[d, slot]
            stop = entry - side * p.bk_stop_atr * atr
            ex_slot, px, reason = _manage(sd, d, side, slot, entry, stop, trail_atr=atr)
            trades.append(Trade(d, side, slot, ex_slot, entry, px, _pass_leverage(entry, stop),
                                reason))
            count += 1
            free_from = ex_slot + 1
    return trades


STRATEGIES = {"NA": noise_area, "LH": late_half_hour, "OR": opening_range,
              "SW": liquidity_sweep, "BK": donchian_breakout}

# Phase-2 plateau check: each fixed parameter moved about +-25%, one at a time.
PERTURBATIONS: Dict[str, List[Params]] = {
    "NA": [Params(lookback=10), Params(lookback=18), Params(check_minutes=20),
           Params(check_minutes=40)],
    "LH": [Params(first_minutes=20), Params(first_minutes=40), Params(last_minutes=20),
           Params(last_minutes=40)],
    "OR": [Params(or_stop_atr=0.075), Params(or_stop_atr=0.125), Params(or_target_r=7.5),
           Params(or_target_r=12.5)],
    "SW": [Params(sw_displacement=1.125), Params(sw_displacement=1.875),
           Params(sw_target_r=1.875), Params(sw_target_r=3.125)],
    "BK": [Params(bk_donchian=15), Params(bk_donchian=25), Params(bk_stop_atr=1.125),
           Params(bk_stop_atr=1.875)],
}
