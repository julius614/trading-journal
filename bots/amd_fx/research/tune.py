"""Pre-declared parameter grid for the AMD strategy, with realistic raw-account costs.

    python -m bots.amd_fx.research.tune --start 2014 --end 2017 --out tune_2014_2017.csv

Signal parameters (54 combos) x target structures (4) x windows (3) x pairs (EUR, GBP, both).
Every configuration is written to the CSV, so the number of tries is on record.
"""
from __future__ import annotations

import argparse
import dataclasses
import itertools
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

from ..config import AppConfig, FilterConfig, StrategyConfig
from .fast_backtest import (RAW_ACCOUNT, daily_atr_by_day, generate_signals, simulate,
                            stats, trades_frame)
from .load_data import load_cached

OUT_DIR = Path(__file__).resolve().parent / "data"

SWEEPS = [(5.0, 15.0), (8.0, 20.0), (10.0, 30.0)]
DISP_BARS = [1, 2, 3]
Z_GATES = [None, 1.0, 1.5]
VOL = [True, False]
TARGETS = {   # name -> (tp1_fraction, tp2_extension)
    "split_mid+edge": (0.5, 0.0),      # current default
    "single_edge": (0.0, 0.0),
    "split_mid+ext0.5": (0.5, 0.5),
    "single_ext0.5": (0.0, 0.5),
}
WINDOWS = {"london": {"07:00-10:00"}, "ny": {"12:00-15:00"}, "both": {"07:00-10:00", "12:00-15:00"}}


def signal_config(sweep: Tuple[float, float], disp: int, z, vol: bool) -> AppConfig:
    return AppConfig(
        strategy=StrategyConfig(sweep_min_pips=sweep[0], sweep_max_pips=sweep[1],
                                displacement_max_bars=disp),
        filters=FilterConfig(use_zscore=z is not None, z_threshold=z or 1.5, use_vol_spike=vol),
    )


def _bars(symbol: str, start: int, end: int) -> pd.DataFrame:
    b = load_cached(symbol)
    return b[(b.index.year >= start) & (b.index.year <= end)]


def _signals_job(args):
    symbol, start, end, key = args
    sweep, disp, z, vol = key
    bars = _bars(symbol, start, end)
    atr_map = daily_atr_by_day(bars, 14)
    return symbol, key, generate_signals(bars, symbol, signal_config(sweep, disp, z, vol), atr_map)


def run_grid(start: int, end: int, cost_mult: float = 1.0, workers: int = 4) -> pd.DataFrame:
    keys = list(itertools.product(SWEEPS, DISP_BARS, Z_GATES, VOL))
    jobs = [(s, start, end, k) for s in ("EURUSD", "GBPUSD") for k in keys]
    with ProcessPoolExecutor(workers) as pool:
        results = list(pool.map(_signals_job, jobs))
    bars = {s: _bars(s, start, end) for s in ("EURUSD", "GBPUSD")}
    sigs: Dict[Tuple[str, tuple], list] = {(s, k): v for s, k, v in results}
    rows = []
    for k in keys:
        sweep, disp, z, vol = k
        for tname, (frac, ext) in TARGETS.items():
            cfg = dataclasses.replace(
                signal_config(sweep, disp, z, vol),
                strategy=StrategyConfig(sweep_min_pips=sweep[0], sweep_max_pips=sweep[1],
                                        displacement_max_bars=disp, tp1_fraction=frac,
                                        tp2_extension=ext))
            for wname, wset in WINDOWS.items():
                frames = []
                for s in ("EURUSD", "GBPUSD"):
                    chosen = [x for x in sigs[(s, k)] if x.window in wset]
                    # target geometry depends on the config; rebuild tp2 for the extension
                    if ext:
                        chosen = [dataclasses.replace(
                            x, tp2=x.tp2 + x.side * ext * (x.asian_high - x.asian_low))
                            for x in chosen]
                    tr = simulate(bars[s], chosen, s, cfg, RAW_ACCOUNT[s].scaled(cost_mult))
                    frames.append(trades_frame(tr))
                df = pd.concat(frames, ignore_index=True)
                for pair, sub in (("EURUSD", df[df.symbol == "EURUSD"] if len(df) else df),
                                  ("GBPUSD", df[df.symbol == "GBPUSD"] if len(df) else df),
                                  ("both", df)):
                    st = stats(sub["r"] if len(sub) else pd.Series(dtype=float))
                    yearly = sub.groupby("year")["r"].sum() if len(sub) else pd.Series(dtype=float)
                    rows.append({
                        "sweep": f"{sweep[0]:g}-{sweep[1]:g}", "disp": disp,
                        "z": "off" if z is None else z, "vol": "on" if vol else "off",
                        "target": tname, "window": wname, "pair": pair, **st,
                        "years_pos": int((yearly > 0).sum()), "years": int(len(yearly)),
                    })
    return pd.DataFrame(rows)


def neighbour_score(grid: pd.DataFrame) -> pd.DataFrame:
    """Median exp_r of configs that differ by one step in one signal parameter."""
    order = {"sweep": [f"{a:g}-{b:g}" for a, b in SWEEPS], "disp": DISP_BARS,
             "z": ["off", 1.0, 1.5], "vol": ["on", "off"]}
    idx = grid.set_index(["sweep", "disp", "z", "vol", "target", "window", "pair"])["exp_r"]
    scores = []
    for _, row in grid.iterrows():
        vals = []
        for p, levels in order.items():
            i = levels.index(row[p])
            for j in (i - 1, i + 1):
                if 0 <= j < len(levels):
                    key = {**row[["sweep", "disp", "z", "vol", "target", "window", "pair"]].to_dict(),
                           p: levels[j]}
                    vals.append(idx.get(tuple(key[c] for c in
                                              ["sweep", "disp", "z", "vol", "target", "window", "pair"])))
        vals = [v for v in vals if v is not None and pd.notna(v)]
        scores.append(float(pd.Series(vals).median()) if vals else float("nan"))
    out = grid.copy()
    out["neighbour_exp_r"] = scores
    return out


def main(argv=None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--start", type=int, default=2014)
    p.add_argument("--end", type=int, default=2017)
    p.add_argument("--cost-mult", type=float, default=1.0)
    p.add_argument("--out", default="tune.csv")
    a = p.parse_args(argv)
    grid = neighbour_score(run_grid(a.start, a.end, a.cost_mult))
    OUT_DIR.mkdir(exist_ok=True)
    grid.to_csv(OUT_DIR / a.out, index=False)
    print(f"{len(grid)} configurations written to {OUT_DIR / a.out}")


if __name__ == "__main__":
    main()
