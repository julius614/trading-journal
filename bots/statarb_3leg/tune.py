"""Pre-declared tuning protocol for the pairs bot (written and committed BEFORE the data
was looked at; see git history).

    python -m bots.statarb_3leg.tune AUDUSD=data/amd_fx/AUDUSD_H1.csv NZDUSD=data/amd_fx/NZDUSD_H1.csv

Protocol
--------
Grid (9 configs): entry Z {1.75, 2.0, 2.5} x time stop {24, 48, 96} H1 bars. Everything
else stays at the defaults (exit Z 0.1, stop Z_entry +-2.0, gate off, 2.5x fee gate).

Each config is replayed once over the whole history (so the Kalman filter is warm and
continuous); trades are then split by ENTRY time into:
    tune       2018-09 .. 2022-12
    validate   2023-01 .. 2024-12
    hold-out   2025-01 .. end        (reported once, never used for choosing)

Selection (tune period only): among configs with >= 60 tune trades and PF > 1.0, take the
one with the highest median $/trade over itself and its grid neighbours (robust region,
not the single best point); ties -> higher own $/trade.
Acceptance: the chosen config replaces the default only if, on the validate period, it
is profitable with PF >= 1.1 AND it does at least as well as the current default
(entry 2.0, hold 48) there. Otherwise the default stays.
Caveat: the default (2.0, 48) was already seen on the full AUD/NZD history, so the
hold-out is fully clean only for configs other than the default.
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import itertools
from concurrent.futures import ProcessPoolExecutor
from typing import Dict, List, Mapping, Optional, Tuple

import numpy as np
import pandas as pd

from .backtest import run_replay, with_overrides
from .config import load_config
from .data_fetcher import load_pair

ENTRY_Z = (1.75, 2.0, 2.5)
MAX_HOLD = (24, 48, 96)
DEFAULT = (2.0, 48)
PERIODS = {
    "tune": ("2018-01-01", "2023-01-01"),
    "validate": ("2023-01-01", "2025-01-01"),
    "holdout": ("2025-01-01", "2100-01-01"),
}
MIN_TUNE_TRADES = 60


def period_stats(trades: pd.DataFrame) -> Dict[str, float]:
    """Stats for one period's closed baskets (columns: pnl)."""
    if trades.empty:
        return {"trades": 0, "pnl": 0.0, "per_trade": float("nan"), "pf": float("nan"),
                "win": float("nan")}
    pnl = trades["pnl"]
    gains, losses = pnl[pnl > 0].sum(), -pnl[pnl <= 0].sum()
    return {"trades": int(len(pnl)), "pnl": round(float(pnl.sum()), 2),
            "per_trade": round(float(pnl.mean()), 2),
            "pf": round(float(gains / losses), 3) if losses > 0 else float("inf"),
            "win": round(float((pnl > 0).mean()), 3)}


def split_by_period(trades: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    t = pd.to_datetime(trades["opened_at"], utc=True) if len(trades) else pd.Series(dtype="datetime64[ns, UTC]")
    out = {}
    for name, (a, b) in PERIODS.items():
        mask = (t >= pd.Timestamp(a, tz="UTC")) & (t < pd.Timestamp(b, tz="UTC"))
        out[name] = trades[mask] if len(trades) else trades
    return out


def _run_one(args) -> Tuple[Tuple[float, int], pd.DataFrame]:
    paths, entry_z, hold, commission = args
    base = load_config()
    pair = tuple(paths)
    cfg = with_overrides(base, pair, hold, no_coint_gate=True)
    cfg = dataclasses.replace(cfg, strategy=dataclasses.replace(cfg.strategy, entry_z=entry_z))
    data = load_pair(paths, pair)
    res = asyncio.run(run_replay(cfg, {}, 10_000.0, None, commission, None, frames=data,
                                 verbose=False))
    rows = [{"opened_at": b.opened_at, "pnl": b.pnl, "exit": b.exit_reason}
            for b in res["baskets"]]
    return (entry_z, hold), pd.DataFrame(rows, columns=["opened_at", "pnl", "exit"])


def neighbours(key: Tuple[float, int]) -> List[Tuple[float, int]]:
    i, j = ENTRY_Z.index(key[0]), MAX_HOLD.index(key[1])
    out = [key]
    for di, dj in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        a, b = i + di, j + dj
        if 0 <= a < len(ENTRY_Z) and 0 <= b < len(MAX_HOLD):
            out.append((ENTRY_Z[a], MAX_HOLD[b]))
    return out


def select(table: pd.DataFrame) -> Optional[Tuple[float, int]]:
    """Apply the pre-declared selection rule to the tune-period table."""
    tune = table.set_index(["entry_z", "max_hold"])
    scores = {}
    for key in tune.index:
        row = tune.loc[key]
        if row["tune_trades"] < MIN_TUNE_TRADES or not row["tune_pf"] > 1.0:
            continue
        nb = [tune.loc[k, "tune_per_trade"] for k in neighbours(key) if k in tune.index]
        scores[key] = (float(np.nanmedian(nb)), float(row["tune_per_trade"]))
    if not scores:
        return None
    return max(scores, key=lambda k: scores[k])


def accept(table: pd.DataFrame, chosen: Optional[Tuple[float, int]]) -> Tuple[Tuple[float, int], str]:
    t = table.set_index(["entry_z", "max_hold"])
    if chosen is None:
        return DEFAULT, "no config met the tune-period rule; default kept"
    if chosen == DEFAULT:
        return DEFAULT, "the rule picked the current default"
    c, d = t.loc[chosen], t.loc[DEFAULT]
    if c["validate_pnl"] > 0 and c["validate_pf"] >= 1.1 and c["validate_pnl"] >= d["validate_pnl"]:
        return chosen, "chosen config passed validation and beat the default there"
    return DEFAULT, "chosen config failed validation; default kept"


def run(paths: Mapping[str, str], commission: float, workers: int = 4) -> pd.DataFrame:
    jobs = [(dict(paths), z, h, commission) for z, h in itertools.product(ENTRY_Z, MAX_HOLD)]
    with ProcessPoolExecutor(workers) as pool:
        results = list(pool.map(_run_one, jobs))
    rows = []
    for (z, h), trades in results:
        row = {"entry_z": z, "max_hold": h}
        for name, part in split_by_period(trades).items():
            for k, v in period_stats(part).items():
                row[f"{name}_{k}"] = v
        rows.append(row)
    return pd.DataFrame(rows)


def main(argv: Optional[List[str]] = None) -> None:
    p = argparse.ArgumentParser(description="Pre-declared tuning grid for the pairs bot")
    p.add_argument("data", nargs=2, metavar="SYMBOL=CSV")
    p.add_argument("--commission", type=float, default=7.0)
    p.add_argument("--out", help="write the full table to CSV")
    a = p.parse_args(argv)
    paths = dict(x.split("=", 1) for x in a.data)
    table = run(paths, a.commission)
    chosen = select(table)
    final, why = accept(table, chosen)
    cols = ["entry_z", "max_hold"] + [f"{per}_{k}" for per in PERIODS
                                      for k in ("trades", "pnl", "per_trade", "pf")]
    with pd.option_context("display.width", 250, "display.max_columns", None):
        print(f"\n== Tuning grid: {' vs '.join(paths)} ==")
        print(table[cols].to_string(index=False))
    print(f"\nSelected on tune period: {chosen}   ->   final: {final} ({why})")
    if a.out:
        table.to_csv(a.out, index=False)


if __name__ == "__main__":
    main()
