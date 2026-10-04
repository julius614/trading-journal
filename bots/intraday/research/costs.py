"""Break-even trading costs for every strategy x market (POST-HOC diagnostic).

    python -m bots.intraday.research.costs --data-dir data/intraday_hd

For each combination it reports the gross result (before costs), today's cost, and the
break-even cost multiplier k* = gross / cost: the fraction of today's costs (broker
spread + slippage + FX commission) at which the strategy would net zero. k* > 1 means it
already makes money; k* = 0.5 means costs must halve. The same cost is also shown as a
round-trip spread in points and basis points at the median price, to compare with any
broker's or prop firm's quoted spread. Figures are given for the whole history and for
the discovery period only (the part the pre-declared rule judges first).

This price data has been seen, so this is a diagnostic, not a pass/fail test.
"""
from __future__ import annotations

import argparse
from typing import List, Optional

import numpy as np
import pandas as pd

from .data import available_symbols
from .engine import run
from .protocol import BASE, CostScenario, _sessions, candidates, split_dates
from .strategies import STRATEGIES


def breakeven_row(name: str, sd, trades: pd.DataFrame, point: Optional[float] = None) -> dict:
    """Gross / cost summary of one combination's trades."""
    g, c = trades["gross"], trades["cost"]
    gains, losses = g[g > 0].sum(), -g[g <= 0].sum()
    k = float(g.sum() / c.sum()) if c.sum() > 0 else float("nan")
    price = float(np.median(sd.close))
    # today's average round-trip cost per trade in price units (before leverage)
    rt = float((c / trades["leverage"]).mean() * price) if len(trades) else float("nan")
    return {"combo": f"{name}:{sd.symbol}", "trades": int(len(trades)),
            "gross_pf": round(float(gains / losses), 3) if losses > 0 else float("inf"),
            "gross": round(float(g.sum()), 4), "cost": round(float(c.sum()), 4),
            "breakeven_k": round(k, 2),
            "cost_rt_bp": round(rt / price * 1e4, 2),
            "breakeven_rt_bp": round(max(k, 0) * rt / price * 1e4, 2),
            "breakeven_rt_points": (round(max(k, 0) * rt / point, 1) if point else None)}


def table(data_dir: str, scen: CostScenario = BASE) -> pd.DataFrame:
    import json
    from pathlib import Path
    symbols = available_symbols(data_dir)
    sds = {s: _sessions(data_dir, s, scen) for s in symbols}
    cut1, _ = split_dates([pd.Timestamp(d) for sd in sds.values() for d in sd.dates])
    rows = []
    for s, sd in sds.items():
        point = json.loads((Path(data_dir) / f"{s}_spec.json").read_text()).get("point")
        for name in candidates(s):
            t = run(sd, STRATEGIES[name], cost_mult=scen.cost_mult)
            if t.empty:
                continue
            row = breakeven_row(name, sd, t, point)
            disc = t[t["date"] < cut1]
            if len(disc):
                d = breakeven_row(name, sd, disc, point)
                row["disc_gross_pf"], row["disc_breakeven_k"] = d["gross_pf"], d["breakeven_k"]
            rows.append(row)
    return pd.DataFrame(rows).sort_values("breakeven_k", ascending=False)


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description="Break-even costs per strategy x market")
    ap.add_argument("--data-dir", default="data/intraday_hd")
    ap.add_argument("--out", help="write the table to CSV")
    a = ap.parse_args(argv)
    t = table(a.data_dir)
    with pd.option_context("display.width", 250, "display.max_columns", None,
                           "display.max_rows", None):
        print("\n== Break-even costs (POST-HOC diagnostic; k* = fraction of today's costs "
              "at which the strategy nets zero) ==")
        print(t.to_string(index=False))
    if a.out:
        t.to_csv(a.out, index=False)


if __name__ == "__main__":
    main()
