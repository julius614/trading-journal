"""Session liquidity sweep (Accumulation - Manipulation - Distribution) signal logic.

Accumulation : the Asian range, 00:00-06:00 UTC (bar open times inside the window).
Manipulation : inside a trade window (07:00-10:00 or 12:00-15:00 UTC), price pushes beyond
               the Asian high or low by sweep_min..sweep_max pips.
Displacement : within 1..displacement_max_bars bars after the bar that made the sweep
               extreme, a bar closes back inside the Asian range.
Distribution : trade back through the range - long after a low sweep, short after a high
               sweep. SL beyond the sweep extreme, TP1 at the Asian midpoint, TP2 at the
               opposite Asian boundary.

The strategy is pure: it takes closed bars and returns a Signal or None. Sizing, risk
checks and orders happen elsewhere.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import Enum
from typing import Optional, Set

import numpy as np
import pandas as pd

from .config import AppConfig, TimeWindow, pip_size
from .quantitative_filters import kalman_zscore, range_within_atr, volatility_spike

log = logging.getLogger(__name__)


class Phase(str, Enum):
    ACCUMULATION = "accumulation"   # Asian session still forming
    ARMED = "armed"                 # range known and valid; watching for sweeps
    SKIPPED = "skipped"             # range invalid (too wide, no data, no ATR)


@dataclass(frozen=True)
class AsianRange:
    high: float
    low: float
    bars: int

    @property
    def mid(self) -> float:
        return (self.high + self.low) / 2.0

    @property
    def width(self) -> float:
        return self.high - self.low

    def pips(self, pip: float) -> float:
        return self.width / pip


@dataclass
class Sweep:
    side: str            # "high" (swept above the Asian high) or "low"
    extreme: float       # most extreme price reached so far
    bars_since: int = 0  # closed bars since the bar that made the extreme
    peak_z: float = float("nan")   # most extreme Kalman Z-score seen during the sweep


@dataclass(frozen=True)
class Signal:
    symbol: str
    side: int            # +1 long, -1 short
    time: datetime       # open time of the displacement bar
    entry: float         # displacement bar close (reference; fill comes from the broker)
    stop_loss: float
    tp1: float
    tp2: float
    sweep_extreme: float
    asian_high: float
    asian_low: float
    zscore: float
    vol_ratio: float
    window: str

    @property
    def direction(self) -> str:
        return "long" if self.side == 1 else "short"


@dataclass
class _DayState:
    day: Optional[date] = None
    phase: Phase = Phase.ACCUMULATION
    asian: Optional[AsianRange] = None
    sweep: Optional[Sweep] = None
    sweep_window: Optional[str] = None
    traded_windows: Set[str] = field(default_factory=set)


def in_window(t: time, window: TimeWindow) -> bool:
    start, end = window
    return start <= t < end if start <= end else (t >= start or t < end)


def window_label(window: TimeWindow) -> str:
    return f"{window[0]:%H:%M}-{window[1]:%H:%M}"


def compute_asian_range(
    bars: pd.DataFrame,
    day: date,
    start: time = time(0, 0),
    end: time = time(6, 0),
) -> Optional[AsianRange]:
    """High/low of all bars of `day` whose open time is in [start, end). UTC index."""
    if bars.empty:
        return None
    idx = bars.index
    mask = (idx.date == day) & (idx.time >= start) & (idx.time < end)
    session = bars.loc[mask]
    if session.empty:
        return None
    return AsianRange(high=float(session["high"].max()), low=float(session["low"].min()),
                      bars=int(len(session)))


class AMDStrategy:
    """Per-symbol state machine. Call on_bar() once per newly closed bar."""

    def __init__(self, symbol: str, cfg: AppConfig) -> None:
        self.symbol = symbol
        self.cfg = cfg
        self.pip = pip_size(symbol)
        self.state = _DayState()

    # ------------------------------------------------------------------ helpers
    def _reset_day(self, day: date) -> None:
        self.state = _DayState(day=day)

    def _active_window(self, t: time) -> Optional[str]:
        for w in self.cfg.session.trade_windows:
            if in_window(t, w):
                return window_label(w)
        return None

    def _arm(self, bars: pd.DataFrame, day: date, atr_value: Optional[float]) -> None:
        s = self.cfg.session
        rng = compute_asian_range(bars, day, s.asian_start, s.asian_end)
        if rng is None:
            log.warning("%s %s: no Asian-session bars, skipping the day", self.symbol, day)
            self.state.phase = Phase.SKIPPED
            return
        mult = self.cfg.strategy.max_range_atr_mult
        if not range_within_atr(rng.width, atr_value, mult):
            log.info("%s %s: Asian range %.1f pips vs ATR %s x%.1f - skipping the day",
                     self.symbol, day, rng.pips(self.pip),
                     f"{atr_value / self.pip:.1f}p" if atr_value else "n/a", mult)
            self.state.phase = Phase.SKIPPED
            return
        self.state.asian = rng
        self.state.phase = Phase.ARMED
        log.info("%s %s: Asian range %.5f-%.5f (%.1f pips) armed", self.symbol, day,
                 rng.low, rng.high, rng.pips(self.pip))

    def _latest_z(self, close: pd.Series) -> float:
        f = self.cfg.filters
        zs = kalman_zscore(close, window=f.z_window, q_ratio=f.kalman_q_ratio)
        return float(zs.iloc[-1]) if len(zs) else float("nan")

    def _track_z(self, sweep: Sweep, close: pd.Series) -> None:
        """Keep the most extreme Z of the manipulation leg (lowest for a low sweep)."""
        if not self.cfg.filters.use_zscore:
            return
        z = self._latest_z(close)
        if not np.isfinite(z):
            return
        if not np.isfinite(sweep.peak_z):
            sweep.peak_z = z
        elif sweep.side == "low":
            sweep.peak_z = min(sweep.peak_z, z)
        else:
            sweep.peak_z = max(sweep.peak_z, z)

    def _filters(self, close: pd.Series, side: int, sweep: Sweep) -> tuple[bool, float, float]:
        f = self.cfg.filters
        z = float("nan")
        if f.use_zscore:
            z = sweep.peak_z if f.z_measure == "sweep" else self._latest_z(close)
            if not np.isfinite(z):
                return False, z, float("nan")
            if side == 1 and not z < -f.z_threshold:
                return False, z, float("nan")
            if side == -1 and not z > f.z_threshold:
                return False, z, float("nan")
        ratio = float("nan")
        if f.use_vol_spike:
            spike, ratio = volatility_spike(close, f.vol_short, f.vol_long, f.vol_mult)
            if not spike:
                return False, z, ratio
        return True, z, ratio

    # ------------------------------------------------------------------ main entry
    def on_bar(self, bars: pd.DataFrame, atr_value: Optional[float]) -> Optional[Signal]:
        """Process the latest closed bar (the last row of `bars`).

        `bars` must hold closed bars with a UTC DatetimeIndex of bar open times, going back
        at least to the start of today's Asian session (and z_window bars for the filters).
        `atr_value` is the current ATR on the configured ATR timeframe, in price units.
        """
        if bars.empty:
            return None
        ts: pd.Timestamp = bars.index[-1]
        bar = bars.iloc[-1]
        day, t = ts.date(), ts.time()
        st = self.state
        if st.day != day:
            self._reset_day(day)
            st = self.state

        sc = self.cfg.session
        if t < sc.asian_end and t >= sc.asian_start:
            st.phase = Phase.ACCUMULATION
            return None
        if st.phase == Phase.ACCUMULATION:
            self._arm(bars, day, atr_value)
        if st.phase != Phase.ARMED or st.asian is None:
            return None

        window = self._active_window(t)
        if window is None or window in st.traded_windows:
            st.sweep, st.sweep_window = None, None
            return None
        if st.sweep_window not in (None, window):
            st.sweep = None
        st.sweep_window = window

        a, cfg = st.asian, self.cfg.strategy
        hi, lo, close = float(bar["high"]), float(bar["low"]), float(bar["close"])
        min_x, max_x = cfg.sweep_min_pips * self.pip, cfg.sweep_max_pips * self.pip

        sw = st.sweep
        if sw is None:
            up, down = hi - a.high, a.low - lo
            if up >= min_x and up <= max_x and up >= down:
                st.sweep = Sweep("high", hi)
                self._track_z(st.sweep, bars["close"])
                log.info("%s sweep of Asian high: %.1f pips at %s", self.symbol, up / self.pip, ts)
            elif down >= min_x and down <= max_x:
                st.sweep = Sweep("low", lo)
                self._track_z(st.sweep, bars["close"])
                log.info("%s sweep of Asian low: %.1f pips at %s", self.symbol, down / self.pip, ts)
            return None

        # an active sweep: extend it, void it, or look for displacement
        if sw.side == "high" and hi > sw.extreme:
            sw.extreme, sw.bars_since = hi, 0
        elif sw.side == "low" and lo < sw.extreme:
            sw.extreme, sw.bars_since = lo, 0
        else:
            sw.bars_since += 1
        self._track_z(sw, bars["close"])
        excursion = sw.extreme - a.high if sw.side == "high" else a.low - sw.extreme
        if excursion > max_x:
            log.info("%s sweep became a breakout (%.1f pips) - setup void", self.symbol,
                     excursion / self.pip)
            st.sweep = None
            return None
        if sw.bars_since == 0:
            return None  # this bar made a new extreme; displacement must come after it
        if sw.bars_since > cfg.displacement_max_bars:
            log.info("%s no displacement within %d bars - sweep expired", self.symbol,
                     cfg.displacement_max_bars)
            st.sweep = None
            return None

        side = -1 if sw.side == "high" else 1
        back_inside = close < a.high if side == -1 else close > a.low
        if not back_inside:
            return None

        ok, z, ratio = self._filters(bars["close"], side, sw)
        if not ok:
            log.info("%s displacement at %s rejected by filters (z=%.2f, vol ratio=%.2f)",
                     self.symbol, ts, z, ratio)
            st.sweep = None
            return None

        buf = cfg.sl_buffer_pips * self.pip
        if side == 1:
            sl, tp1, tp2 = sw.extreme - buf, a.mid, a.high
            valid = tp1 > close
        else:
            sl, tp1, tp2 = sw.extreme + buf, a.mid, a.low
            valid = tp1 < close
        st.sweep = None
        if not valid:
            log.info("%s displacement closed beyond the Asian midpoint - no room to TP1", self.symbol)
            return None

        st.traded_windows.add(window)
        sig = Signal(
            symbol=self.symbol, side=side, time=ts.to_pydatetime(), entry=close,
            stop_loss=sl, tp1=tp1, tp2=tp2, sweep_extreme=sw.extreme,
            asian_high=a.high, asian_low=a.low, zscore=z, vol_ratio=ratio, window=window,
        )
        log.info("%s SIGNAL %s entry~%.5f SL %.5f TP1 %.5f TP2 %.5f (z=%.2f vol=%.2f)",
                 self.symbol, sig.direction, close, sl, tp1, tp2, z, ratio)
        return sig
