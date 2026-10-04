"""Turn strategy trades into net returns after spread, slippage and commission.

Prices are MT5 bid bars. Round-trip spread cost = half the entry bar's spread + half the
exit bar's spread (equivalent to trading at the mid and paying half the spread each way).
Slippage = slip_mult x half the median session spread per side (slip_mult 1 = base case,
2 = the "doubled slippage" robustness check). Commission is a fraction of notional per
round trip: 0.00007 for FX (about $7 per $100k), 0 for CFDs.
"""
from __future__ import annotations

from typing import Callable, List, Optional

import numpy as np
import pandas as pd

from .sessions import SessionData
from .strategies import DEFAULT, Params, Trade

FX_COMMISSION = 0.00007


def commission_for(market: str) -> float:
    return FX_COMMISSION if market == "FX" else 0.0


def trades_frame(sd: SessionData, trades: List[Trade], slip_mult: float = 1.0,
                 commission: Optional[float] = None) -> pd.DataFrame:
    """One row per trade with date, side, leverage and net return (fraction of equity)."""
    cols = ["date", "side", "entry", "exit", "leverage", "gross", "cost", "ret", "reason"]
    if not trades:
        return pd.DataFrame(columns=cols)
    comm = commission_for(sd.market) if commission is None else commission
    med = float(np.median(sd.spread[sd.spread > 0])) if (sd.spread > 0).any() else 0.0
    rows = []
    for t in trades:
        spread = 0.5 * (sd.spread[t.day, t.entry_slot] + sd.spread[t.day, t.exit_slot])
        cost = (spread + slip_mult * med) / t.entry + comm
        gross = t.side * (t.exit - t.entry) / t.entry
        rows.append((pd.Timestamp(sd.dates[t.day]), t.side, t.entry, t.exit, t.leverage,
                     gross * t.leverage, cost * t.leverage, (gross - cost) * t.leverage,
                     t.reason))
    return pd.DataFrame(rows, columns=cols)


def run(sd: SessionData, strategy: Callable[[SessionData, Params], List[Trade]],
        params: Params = DEFAULT, slip_mult: float = 1.0) -> pd.DataFrame:
    return trades_frame(sd, strategy(sd, params), slip_mult)


def daily_returns(trades: pd.DataFrame) -> pd.Series:
    """Sum of trade returns per session date (only days with trades)."""
    if trades.empty:
        return pd.Series(dtype=float)
    return trades.groupby("date")["ret"].sum()


def stats(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {"trades": 0, "ret": 0.0, "pf": float("nan"), "win": float("nan"),
                "avg_bp": float("nan")}
    r = trades["ret"]
    gains, losses = r[r > 0].sum(), -r[r <= 0].sum()
    return {"trades": int(len(r)), "ret": round(float(r.sum()), 4),
            "pf": round(float(gains / losses), 3) if losses > 0 else float("inf"),
            "win": round(float((r > 0).mean()), 3),
            "avg_bp": round(float(r.mean() * 1e4), 2)}
