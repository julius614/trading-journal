"""Replay three M5 CSVs through the live StatArbBot on a PaperBroker.

    python -m bots.statarb_3leg.backtest EURUSD=data/amd_fx/EURUSD_M5.csv \
        GBPUSD=data/amd_fx/GBPUSD_M5.csv EURGBP=data/amd_fx/EURGBP_M5.csv \
        --commission 7 --out baskets.csv

Spreads: taken per bar from the CSV's MT5 `spread` column when present, else --spreads.
Besides P&L, it reports how big triangle deviations actually are compared with 3-leg
costs, and why signals were rejected.
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
from typing import Dict, List, Mapping, Optional

import numpy as np
import pandas as pd

from .config import TRIANGLE, AppConfig, load_config
from .data_fetcher import load_triangle
from .execution import Basket, PaperBroker
from .main import StatArbBot, load_news, setup_logging
from .risk_manager import NewsCalendar

BAR = pd.Timedelta(minutes=5)


def basket_stats(baskets: List[Basket], start_balance: float) -> Dict[str, float]:
    if not baskets:
        return {"baskets": 0}
    pnl = pd.Series([b.pnl for b in baskets])
    wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
    equity = start_balance + pnl.cumsum()
    peak = equity.cummax().clip(lower=start_balance)
    return {
        "baskets": int(len(pnl)),
        "win_rate": round(len(wins) / len(pnl), 4),
        "total_pnl": round(float(pnl.sum()), 2),
        "avg_pnl": round(float(pnl.mean()), 2),
        "profit_factor": round(float(wins.sum() / -losses.sum()), 3) if losses.sum() < 0 else float("inf"),
        "max_drawdown_pct": round(float(((equity - peak) / peak).min() * 100), 2),
        "avg_bars_held": round(float(np.mean([b.bars_held for b in baskets])), 1),
    }


async def run_replay(
    cfg: AppConfig,
    csv_paths: Mapping[str, str],
    balance: float = 10_000.0,
    spread_pips: Optional[Mapping[str, float]] = None,
    commission_per_lot: Optional[float] = None,
    news: Optional[NewsCalendar] = None,
    frames: Optional[Mapping[str, pd.DataFrame]] = None,
    out: Optional[str] = None,
    verbose: bool = True,
) -> Dict[str, object]:
    data = dict(frames) if frames else load_triangle(csv_paths)
    commission = cfg.filters.commission_per_lot if commission_per_lot is None else commission_per_lot
    cfg = dataclasses.replace(cfg, filters=dataclasses.replace(cfg.filters,
                                                               commission_per_lot=commission))
    spreads = dict(spread_pips or {"EURUSD": 0.2, "GBPUSD": 0.5, "EURGBP": 0.6})
    broker = PaperBroker(balance, cfg.risk.account_currency, spreads, commission,
                         cfg.strategy.timeframe)
    for s in TRIANGLE:
        broker.load_bars(s, data[s])
    bot = StatArbBot(cfg, broker, news, state_path=None)
    await broker.connect()

    timeline = data["EURUSD"].index
    for s in ("GBPUSD", "EURGBP"):
        timeline = timeline.intersection(data[s].index)
    for ts in timeline:
        broker.advance(ts)
        await bot.step((ts + BAR).to_pydatetime())
    if bot.executor.basket is not None:
        await bot.executor.close_basket("end of replay", (timeline[-1] + BAR).to_pydatetime())

    stats = basket_stats(bot.executor.history, balance)
    stats["end_balance"] = round(broker.balance, 2)
    gates = pd.DataFrame([dataclasses.asdict(g) for g in bot.gate_log])
    devs = pd.Series(bot.deviation_pips, dtype=float)
    if verbose:
        print("\n== Stat-arb replay ==")
        print(f"  bars: {len(timeline)}  ({timeline[0]} -> {timeline[-1]})")
        for k, v in stats.items():
            print(f"  {k:>18}: {v}")
        if len(devs):
            q = devs.quantile([0.5, 0.9, 0.99, 0.999]).round(2)
            print("\n== How big are triangle deviations? (|spread - Kalman mean|, EURGBP pips) ==")
            print(f"  median {q[0.5]}  p90 {q[0.9]}  p99 {q[0.99]}  p99.9 {q[0.999]}  max {devs.max():.2f}")
        print("\n== Signals (|Z| > entry) ==")
        print(f"  signals that reached the fee gate: {len(gates)}")
        if bot.blocked:
            print(f"  blocked before the gate: {dict(bot.blocked)}")
        if len(gates):
            print(f"  passed the gate: {int(gates.passed.sum())}")
            print(f"  median edge {gates.expected_pips.median():.2f} pips vs median cost "
                  f"{gates.cost_pips.median():.2f} pips (ratio {gates.ratio.median():.2f}, "
                  f"needed {cfg.filters.min_edge_to_cost})")
        if bot.executor.history:
            reasons = pd.Series([b.exit_reason for b in bot.executor.history]).value_counts()
            print(f"  exits: {reasons.to_dict()}")
    if out:
        pd.DataFrame([{**dataclasses.asdict(b), "legs": len(b.legs)} for b in bot.executor.history]
                     ).to_csv(out, index=False)
    return {"stats": stats, "baskets": bot.executor.history, "gates": gates,
            "deviation_pips": devs, "broker": broker, "bot": bot}


def main(argv: Optional[List[str]] = None) -> None:
    p = argparse.ArgumentParser(description="Replay the triangle stat-arb bot")
    p.add_argument("data", nargs=3, metavar="SYMBOL=CSV")
    p.add_argument("--balance", type=float, default=10_000.0)
    p.add_argument("--commission", type=float, help="per lot per leg, round trip")
    p.add_argument("--spreads", default="EURUSD=0.2,GBPUSD=0.5,EURGBP=0.6",
                   help="fallback spreads in pips when the CSV has no spread column")
    p.add_argument("--out", help="write closed baskets to CSV")
    p.add_argument("--log-level", default="WARNING")
    a = p.parse_args(argv)
    cfg = load_config()
    setup_logging(cfg.log_dir, a.log_level)
    spreads = {k: float(v) for k, v in (x.split("=") for x in a.spreads.split(","))}
    asyncio.run(run_replay(cfg, dict(x.split("=", 1) for x in a.data), a.balance, spreads,
                           a.commission, load_news(cfg, live=False), out=a.out))


if __name__ == "__main__":
    main()
