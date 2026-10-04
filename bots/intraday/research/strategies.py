"""Three published intraday strategies with their parameters fixed from the papers.

Every strategy is flat at the session close. Decisions use only closed bars; orders fill
at the NEXT bar's open (or at the stop/target price for OR).

NA  Noise-area momentum - Zarattini, Aziz & Barbon (2024), "Beat the Market: An Effective
    Intraday Momentum Strategy for S&P500 ETF (SPY)".
LH  Market intraday momentum - Gao, Han, Li & Zhou (2018, JFE); across futures:
    Baltussen, Da, Lammers & Martens (2021, JFE).
OR  5-minute opening-range breakout - Zarattini, Barbon & Aziz (2023), "Can Day Trading
    Really Be Profitable?".

Sizing (applied by the engine): NA and LH target 1% daily volatility from the last 14
sessions' close-to-close returns, leverage capped at 4x. OR risks 1% of equity at the stop,
also capped at 4x.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import numpy as np

from .sessions import SessionData

VOL_TARGET = 0.01
MAX_LEVERAGE = 4.0
OR_RISK = 0.01


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


STRATEGIES = {"NA": noise_area, "LH": late_half_hour, "OR": opening_range}

# Phase-2 plateau check: each fixed parameter moved about +-25%, one at a time.
PERTURBATIONS: Dict[str, List[Params]] = {
    "NA": [Params(lookback=10), Params(lookback=18), Params(check_minutes=20),
           Params(check_minutes=40)],
    "LH": [Params(first_minutes=20), Params(first_minutes=40), Params(last_minutes=20),
           Params(last_minutes=40)],
    "OR": [Params(or_stop_atr=0.075), Params(or_stop_atr=0.125), Params(or_target_r=7.5),
           Params(or_target_r=12.5)],
}
