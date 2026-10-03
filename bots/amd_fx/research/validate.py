"""Pick candidates from the tuning grid with a fixed rule, then test them on unseen years.

    python -m bots.amd_fx.research.validate --tune tune_2014_2017.csv --start 2018 --end 2020

Selection rule (decided before seeing results): pair = both, trades >= 150, positive in at
least 3 of 4 tuning years, neighbour median exp_r > 0; rank by neighbour exp_r, then exp_r;
take the top 3. Validation runs at 1x and 2x raw-account costs.
"""
from __future__ import annotations

import argparse
import dataclasses
import math

import pandas as pd

from ..config import StrategyConfig
from .fast_backtest import (RAW_ACCOUNT, daily_atr_by_day, generate_signals, simulate,
                            stats, trades_frame)
from .load_data import load_cached
from .tune import OUT_DIR, TARGETS, WINDOWS, signal_config


def select(grid: pd.DataFrame, n: int = 3) -> pd.DataFrame:
    c = grid[(grid.pair == "both") & (grid.trades >= 150) & (grid.years_pos >= 3)
             & (grid.neighbour_exp_r > 0)]
    return c.sort_values(["neighbour_exp_r", "exp_r"], ascending=False).head(n)


def summary(grid: pd.DataFrame) -> str:
    both = grid[grid.pair == "both"]
    n = len(both)
    lucky_t = math.sqrt(2 * math.log(n)) if n > 1 else float("nan")
    lines = [
        f"configurations (pair=both): {n}; with >=150 trades: {(both.trades >= 150).sum()}",
        f"exp_r > 0: {(both.exp_r > 0).sum()}  |  exp_r > +0.1R: {(both.exp_r > 0.1).sum()}",
        f"median exp_r {both.exp_r.median():+.3f}R; best {both.exp_r.max():+.3f}R",
        f"best t-stat {both.t.max():.2f} vs ~{lucky_t:.2f} expected from luck alone across {n} tries",
    ]
    return "\n".join(lines)


def run_config(row: pd.Series, start: int, end: int, cost_mult: float) -> pd.DataFrame:
    sweep = tuple(float(x) for x in row.sweep.split("-"))
    z = None if row.z == "off" else float(row.z)
    frac, ext = TARGETS[row.target]
    base = signal_config(sweep, int(row.disp), z, row.vol == "on")
    cfg = dataclasses.replace(base, strategy=StrategyConfig(
        sweep_min_pips=sweep[0], sweep_max_pips=sweep[1], displacement_max_bars=int(row.disp),
        tp1_fraction=frac, tp2_extension=ext))
    frames = []
    for s in ("EURUSD", "GBPUSD"):
        b = load_cached(s)
        b = b[(b.index.year >= start) & (b.index.year <= end)]
        sigs = [x for x in generate_signals(b, s, cfg, daily_atr_by_day(b, 14))
                if x.window in WINDOWS[row.window]]
        frames.append(trades_frame(simulate(b, sigs, s, cfg, RAW_ACCOUNT[s].scaled(cost_mult))))
    return pd.concat(frames, ignore_index=True)


def main(argv=None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--tune", default="tune_2014_2017.csv")
    p.add_argument("--start", type=int, default=2018)
    p.add_argument("--end", type=int, default=2020)
    a = p.parse_args(argv)
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 30)
    grid = pd.read_csv(OUT_DIR / a.tune)
    print("== Tuning grid summary ==")
    print(summary(grid))
    cols = ["sweep", "disp", "z", "vol", "target", "window", "trades", "exp_r", "pf", "win",
            "t", "years_pos", "neighbour_exp_r"]
    both = grid[grid.pair == "both"].sort_values("exp_r", ascending=False)
    print("\n== Top 10 by raw exp_r (pair=both) - for reference, NOT the selection ==")
    print(both[cols].head(10).round(3).to_string(index=False))
    chosen = select(grid)
    print("\n== Selected by the pre-declared rule ==")
    if chosen.empty:
        print("No configuration meets the selection rule. Nothing goes to validation.")
        return
    print(chosen[cols].round(3).to_string(index=False))
    print(f"\n== Validation {a.start}-{a.end} (unseen) ==")
    for _, row in chosen.iterrows():
        label = f"{row.sweep} disp{row.disp} z{row.z} vol{row.vol} {row.target} {row.window}"
        for k in (1.0, 2.0):
            st = stats(run_config(row, a.start, a.end, k)["r"])
            print(f"{label:<55} costs x{k:g}: trades {st['trades']:>4}  exp {st['exp_r']:+.3f}R  "
                  f"PF {st['pf']:.2f}  win {st['win']:.1%}  t {st['t']:+.2f}")


if __name__ == "__main__":
    main()
