"""Descriptive study of the AMD setup (no tuning): funnel, ranges, and post-signal travel.

    python -m bots.amd_fx.research.study --start 2014 --end 2017

For each signal it measures, in R (R = entry-to-stop distance), how far price went in
favour (MFE) and against (MAE) before the stop or the end of the day (21:00 UTC), and how
often fixed targets would have been reached before the stop. Costs are ignored here.
"""
from __future__ import annotations

import argparse
import dataclasses
import logging
from collections import Counter
from typing import Dict, List

import numpy as np
import pandas as pd

from ..config import AppConfig, FilterConfig, pip_size
from ..strategy_amd import Signal
from .fast_backtest import daily_atr_by_day, generate_signals
from .load_data import load_cached

FUNNEL_KEYS = {
    "armed": "range armed", "skipping the day": "day skipped (range/ATR/no data)",
    "sweep of Asian": "sweeps (8-20 pips)", "became a breakout": "sweep became breakout (>20)",
    "sweep expired": "no close back inside in 1-3 bars", "rejected by filters": "rejected by filters",
    "no room to TP1": "closed beyond midpoint", "SIGNAL": "signals",
}


class _Counter(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.counts: Counter = Counter()

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()
        for key in FUNNEL_KEYS:
            if key in msg:
                self.counts[key] += 1


def funnel(bars: pd.DataFrame, symbol: str, cfg: AppConfig, atr_map) -> Dict[str, int]:
    log = logging.getLogger("bots.amd_fx.strategy_amd")
    handler = _Counter()
    log.addHandler(handler)
    old = log.level
    log.setLevel(logging.INFO)
    try:
        # generate_signals silences INFO, so drive the strategy directly here
        from ..strategy_amd import AMDStrategy
        strat = AMDStrategy(symbol, cfg)
        times = bars.index.time
        s = cfg.session
        active = np.flatnonzero((times >= s.asian_end) & (times <= max(w[1] for w in s.trade_windows)))
        n = cfg.strategy.history_bars
        for i in active:
            strat.on_bar(bars.iloc[max(0, i - n + 1): i + 1], atr_map.get(bars.index[i].date()))
    finally:
        log.removeHandler(handler)
        log.setLevel(old)
    return {FUNNEL_KEYS[k]: handler.counts.get(k, 0) for k in FUNNEL_KEYS}


def travel(bars: pd.DataFrame, signals: List[Signal], symbol: str) -> pd.DataFrame:
    """MFE/MAE in R after each signal, until the stop or 21:00 UTC the same day."""
    pip = pip_size(symbol)
    pos = {t: i for i, t in enumerate(bars.index)}
    h, lo, c = (bars[k].to_numpy() for k in ("high", "low", "close"))
    rows = []
    for s in signals:
        i = pos[pd.Timestamp(s.time)]
        entry, side = c[i], s.side
        risk = abs(entry - s.stop_loss)
        end_t = pd.Timestamp(s.time).normalize() + pd.Timedelta(hours=21)
        mfe = mae = 0.0
        stopped = False
        for k in range(i + 1, len(c)):
            if bars.index[k] >= end_t:
                break
            fav = (h[k] - entry) if side == 1 else (entry - lo[k])
            adv = (entry - lo[k]) if side == 1 else (h[k] - entry)
            if adv >= risk:                      # stop first on ambiguous bars
                mae, stopped = 1.0, True
                break
            mfe, mae = max(mfe, fav / risk), max(mae, adv / risk)
        rows.append({
            "time": s.time, "year": pd.Timestamp(s.time).year, "side": side, "window": s.window,
            "risk_pips": risk / pip, "range_pips": (s.asian_high - s.asian_low) / pip,
            "tp1_r": abs(s.tp1 - entry) / risk, "tp2_r": abs(s.tp2 - entry) / risk,
            "mfe_r": mfe, "mae_r": mae, "stopped": stopped, "zscore": s.zscore,
            "vol_ratio": s.vol_ratio,
        })
    return pd.DataFrame(rows)


def hit_table(tr: pd.DataFrame, targets=(0.5, 1.0, 1.5, 2.0, 3.0)) -> pd.DataFrame:
    """Share of signals reaching each R target before the stop, and gross EV of a fixed
    target with a time exit valued at 0 (no costs)."""
    out = []
    for x in targets:
        hit = (tr["mfe_r"] >= x).mean()
        lost = (tr["stopped"] & (tr["mfe_r"] < x)).mean()
        out.append({"target_R": x, "hit_rate": hit, "stopped_first": lost,
                    "gross_EV_R": hit * x - lost})
    return pd.DataFrame(out)


def main(argv=None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--start", type=int, default=2014)
    p.add_argument("--end", type=int, default=2017)
    a = p.parse_args(argv)
    pd.set_option("display.width", 160)
    pd.set_option("display.max_columns", 30)
    variants = {
        "default filters": AppConfig(),
        "no filters": AppConfig(filters=FilterConfig(use_zscore=False, use_vol_spike=False)),
    }
    for sym in ("EURUSD", "GBPUSD"):
        bars = load_cached(sym)
        bars = bars[(bars.index.year >= a.start) & (bars.index.year <= a.end)]
        atr_map = daily_atr_by_day(bars, 14)
        pip = pip_size(sym)
        # Asian range vs ATR
        asian = bars.between_time("00:00", "05:55")
        rng = (asian.groupby(asian.index.date)["high"].max()
               - asian.groupby(asian.index.date)["low"].min()) / pip
        atr_p = pd.Series({d: v / pip for d, v in atr_map.items() if v}).reindex(rng.index)
        print(f"\n===== {sym} {a.start}-{a.end} =====")
        print(f"Asian range: median {rng.median():.1f} pips; D1 ATR median {atr_p.median():.1f} "
              f"pips; days with range > 2xATR: {(rng > 2 * atr_p).mean():.1%}")
        for name, cfg in variants.items():
            print(f"\n-- funnel ({name}) --")
            for k, v in funnel(bars, sym, cfg, atr_map).items():
                print(f"  {k:<36} {v}")
            sigs = generate_signals(bars, sym, cfg, atr_map)
            tr = travel(bars, sigs, sym)
            if tr.empty:
                continue
            print(f"\n-- post-signal travel ({name}), {len(tr)} signals --")
            print(tr[["risk_pips", "range_pips", "tp1_r", "tp2_r", "mfe_r"]].describe()
                  .loc[["mean", "25%", "50%", "75%"]].round(2))
            print(hit_table(tr).round(3).to_string(index=False))
            by_w = tr.groupby("window").agg(n=("mfe_r", "size"), mfe_med=("mfe_r", "median"),
                                            stopped=("stopped", "mean"))
            print(by_w.round(2))


if __name__ == "__main__":
    main()
