"""Compare rule variants on the same data in one run (ablation, not tuning).

    python -m bots.statarb_3leg.sweep AUDUSD=data/amd_fx/AUDUSD_H1.csv NZDUSD=data/amd_fx/NZDUSD_H1.csv

Variants: the old rules (240-bar time stop, no stationarity gate), each new rule alone,
and both together (the new defaults). Same costs and data for all.
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
from typing import List, Optional

import pandas as pd

from .backtest import run_replay, with_overrides
from .config import load_config
from .data_fetcher import load_pair
from .main import setup_logging

VARIANTS = [
    ("old: 240-bar stop, no gate", 240, True),
    ("48-bar stop only", 48, True),
    ("gate only (240-bar stop)", 240, False),
    ("NEW: 48-bar stop + gate", 48, False),
]


async def sweep(paths, commission: Optional[float], balance: float) -> pd.DataFrame:
    base = load_config()
    pair = tuple(paths)
    data = load_pair(paths, pair)
    rows = []
    for name, hold, no_gate in VARIANTS:
        cfg = with_overrides(base, pair, hold, no_gate)
        res = await run_replay(cfg, {}, balance, None, commission, None, frames=data,
                               verbose=False)
        st = res["stats"]
        baskets = res["baskets"]
        by_exit = pd.Series([b.exit_reason for b in baskets]).value_counts().to_dict()
        years = pd.Series([b.pnl for b in baskets],
                          index=[b.opened_at[:4] for b in baskets], dtype=float)
        yearly = years.groupby(level=0).sum() if len(years) else pd.Series(dtype=float)
        rows.append({
            "variant": name, "trades": st.get("baskets", 0), "pnl": st.get("total_pnl", 0.0),
            "win": st.get("win_rate"), "avg_win": st.get("avg_win"),
            "avg_loss": st.get("avg_loss"), "pf": st.get("profit_factor"),
            "max_dd_%": st.get("max_drawdown_pct"),
            "yrs+/yrs": f"{int((yearly > 0).sum())}/{len(yearly)}",
            "exits": by_exit,
        })
    return pd.DataFrame(rows)


def main(argv: Optional[List[str]] = None) -> None:
    p = argparse.ArgumentParser(description="Ablation sweep for the pairs bot")
    p.add_argument("data", nargs=2, metavar="SYMBOL=CSV")
    p.add_argument("--commission", type=float, help="per lot per leg, round trip")
    p.add_argument("--balance", type=float, default=10_000.0)
    a = p.parse_args(argv)
    cfg = load_config()
    setup_logging(cfg.log_dir, "ERROR")
    paths = dict(x.split("=", 1) for x in a.data)
    table = asyncio.run(sweep(paths, a.commission, a.balance))
    with pd.option_context("display.width", 220, "display.max_columns", None,
                           "display.max_colwidth", 80):
        print(f"\n== Sweep: {' vs '.join(paths)} ==")
        print(table.to_string(index=False))


if __name__ == "__main__":
    main()
