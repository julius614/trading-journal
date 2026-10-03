"""Replay two H1 CSVs through the live PairsBot on a PaperBroker.

    python -m bots.statarb_3leg.backtest AUDUSD=data/amd_fx/AUDUSD_H1.csv \
        NZDUSD=data/amd_fx/NZDUSD_H1.csv --commission 7 --out baskets.csv

The first SYMBOL=CSV is the y leg, the second the x leg.

Spreads: taken per bar from the CSV's MT5 `spread` column when present, else --spreads.
Besides P&L, it reports how big spread swings are compared with 2-leg costs, why signals
were rejected, and how the hedge ratio moved.
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
from typing import Dict, List, Mapping, Optional

import numpy as np
import pandas as pd

from .config import DEFAULT_SPREADS, AppConfig, load_config
from .data_fetcher import load_pair
from .execution import Basket, PaperBroker
from .main import PairsBot, load_news, setup_logging
from .risk_manager import NewsCalendar

TIMEFRAME_DELTA = {"M5": pd.Timedelta(minutes=5), "M15": pd.Timedelta(minutes=15),
                   "H1": pd.Timedelta(hours=1), "H4": pd.Timedelta(hours=4)}


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
        "avg_win": round(float(wins.mean()), 2) if len(wins) else 0.0,
        "avg_loss": round(float(losses.mean()), 2) if len(losses) else 0.0,
        "profit_factor": round(float(wins.sum() / -losses.sum()), 3) if losses.sum() < 0 else float("inf"),
        "max_drawdown_pct": round(float(((equity - peak) / peak).min() * 100), 2),
        "avg_bars_held": round(float(np.mean([b.bars_held for b in baskets])), 1),
    }


def emergency_stop_hits(baskets: List[Basket], data: Mapping[str, pd.DataFrame],
                        sl_pips: float) -> int:
    """How many legs' bar highs/lows went sl_pips against the entry price while open."""
    from .config import PIP
    hits = 0
    for b in baskets:
        t0, t1 = pd.Timestamp(b.opened_at), pd.Timestamp(b.closed_at)
        for leg in b.legs:
            bars = data[leg.symbol].loc[t0:t1]
            if bars.empty:
                continue
            worst = (leg.price - bars["low"].min() if leg.side == 1
                     else bars["high"].max() - leg.price)
            hits += int(worst >= sl_pips * PIP)
    return hits


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
    data = dict(frames) if frames else load_pair(csv_paths, cfg.pair)
    commission = cfg.filters.commission_per_lot if commission_per_lot is None else commission_per_lot
    cfg = dataclasses.replace(cfg, filters=dataclasses.replace(cfg.filters,
                                                               commission_per_lot=commission))
    spreads = dict(spread_pips or {s: DEFAULT_SPREADS.get(s, 0.5) for s in cfg.pair})
    broker = PaperBroker(balance, cfg.risk.account_currency, spreads, commission,
                         cfg.strategy.timeframe)
    for s in cfg.pair:
        broker.load_bars(s, data[s])
    bot = PairsBot(cfg, broker, news, state_path=None)
    await broker.connect()

    bar = TIMEFRAME_DELTA[cfg.strategy.timeframe]
    timeline = data[cfg.y].index.intersection(data[cfg.x].index)
    for ts in timeline:
        broker.advance(ts)
        await bot.step((ts + bar).to_pydatetime())
    if bot.executor.basket is not None:
        await bot.executor.close_basket("end of replay", (timeline[-1] + bar).to_pydatetime())

    stats = basket_stats(bot.executor.history, balance)
    stats["end_balance"] = round(broker.balance, 2)
    gates = pd.DataFrame([dataclasses.asdict(g) for g in bot.gate_log])
    swings = pd.Series(bot.spread_pips, dtype=float)
    betas = pd.Series(bot.betas, dtype=float)
    if verbose:
        print(f"\n== Pairs replay: {cfg.y} vs {cfg.x} ({cfg.strategy.timeframe}) ==")
        print(f"  bars: {len(timeline)}  ({timeline[0]} -> {timeline[-1]})")
        for k, v in stats.items():
            print(f"  {k:>18}: {v}")
        if len(swings):
            q = swings.quantile([0.5, 0.9, 0.99]).round(1)
            print(f"\n== Spread vs fair value ({cfg.y} pips) ==")
            print(f"  median {q[0.5]}  p90 {q[0.9]}  p99 {q[0.99]}  max {swings.max():.1f}")
        if len(betas):
            print(f"  hedge ratio beta: start {betas.iloc[0]:.3f}  min {betas.min():.3f}  "
                  f"max {betas.max():.3f}  end {betas.iloc[-1]:.3f}")
        print("\n== Signals (|Z| > entry) ==")
        print(f"  signals that reached the fee gate: {len(gates)}")
        if bot.blocked:
            print(f"  blocked before the fee gate: {dict(bot.blocked)}")
        if bot.coint_checks:
            cc = pd.DataFrame(bot.coint_checks, columns=["time", "passed", "pvalue", "half_life"])
            print(f"  stationarity gate: {int(cc.passed.sum())}/{len(cc)} passed; median ADF p "
                  f"{cc.pvalue.median():.3f}, median half-life {cc.half_life.median():.0f} bars")
        if len(gates):
            print(f"  passed the gate: {int(gates.passed.sum())}")
            print(f"  median edge {gates.expected_pips.median():.1f} pips vs median cost "
                  f"{gates.cost_pips.median():.2f} pips (ratio {gates.ratio.median():.1f}, "
                  f"needed {cfg.filters.min_edge_to_cost})")
        if bot.executor.history:
            reasons = pd.Series([b.exit_reason for b in bot.executor.history]).value_counts()
            print(f"  exits: {reasons.to_dict()}")
            by_year = pd.Series({b.opened_at[:4]: 0.0 for b in bot.executor.history})
            for b in bot.executor.history:
                by_year[b.opened_at[:4]] += b.pnl
            print(f"  P&L by year: {by_year.round(2).to_dict()}")
            sl = cfg.risk.emergency_sl_pips
            if sl:
                hits = emergency_stop_hits(bot.executor.history, data, sl)
                print(f"  legs that moved >= {sl:g} pips against the bot while open (a live "
                      f"emergency stop would have closed them): {hits}")
    if out:
        pd.DataFrame([{**dataclasses.asdict(b), "legs": len(b.legs)} for b in bot.executor.history]
                     ).to_csv(out, index=False)
    return {"stats": stats, "baskets": bot.executor.history, "gates": gates,
            "coint_checks": bot.coint_checks,
            "spread_pips": swings, "betas": betas, "broker": broker, "bot": bot}


def main(argv: Optional[List[str]] = None) -> None:
    p = argparse.ArgumentParser(description="Replay the 2-leg pairs bot")
    p.add_argument("data", nargs=2, metavar="SYMBOL=CSV")
    p.add_argument("--balance", type=float, default=10_000.0)
    p.add_argument("--commission", type=float, help="per lot per leg, round trip")
    p.add_argument("--spreads", help="fallback spreads in pips when the CSV has no spread "
                   "column, e.g. AUDUSD=0.3,NZDUSD=0.7 (defaults: typical raw-account spreads)")
    p.add_argument("--max-hold", type=int, help="time stop in bars (default 48)")
    p.add_argument("--no-coint-gate", action="store_true", help="disable the ADF/half-life gate")
    p.add_argument("--flat-weekend", action="store_true",
                   help="close before Friday 16:00 New York, no entries from Friday 12:00")
    p.add_argument("--notional-mult", type=float, help="y-leg notional / equity (default 1)")
    p.add_argument("--risk-per-trade", type=float,
                   help="fixed-risk sizing, e.g. 0.005 = lose ~0.5%% at the Z stop")
    p.add_argument("--out", help="write closed baskets to CSV")
    p.add_argument("--log-level", default="WARNING")
    a = p.parse_args(argv)
    paths = dict(x.split("=", 1) for x in a.data)
    cfg = with_overrides(load_config(), tuple(paths), a.max_hold, a.no_coint_gate)
    if a.flat_weekend:
        cfg = dataclasses.replace(cfg, strategy=dataclasses.replace(cfg.strategy,
                                                                    flat_before_weekend=True))
    if a.notional_mult is not None or a.risk_per_trade is not None:
        risk = cfg.risk
        if a.notional_mult is not None:
            risk = dataclasses.replace(risk, notional_equity_mult=a.notional_mult)
        if a.risk_per_trade is not None:
            risk = dataclasses.replace(risk, risk_per_trade=a.risk_per_trade)
        cfg = dataclasses.replace(cfg, risk=risk)
    setup_logging(cfg.log_dir, a.log_level)
    spreads = ({k: float(v) for k, v in (x.split("=") for x in a.spreads.split(","))}
               if a.spreads else None)
    asyncio.run(run_replay(cfg, paths, a.balance, spreads, a.commission,
                           load_news(cfg, live=False), out=a.out))


def with_overrides(cfg: AppConfig, pair: tuple, max_hold: Optional[int] = None,
                   no_coint_gate: bool = False) -> AppConfig:
    """Set the pair from the command line (y first) and optional strategy overrides."""
    strat = cfg.strategy
    if max_hold is not None:
        strat = dataclasses.replace(strat, max_hold_bars=max_hold)
    if no_coint_gate:
        strat = dataclasses.replace(strat, use_coint_gate=False)
    suffix = next((v[len(k):] for k, v in cfg.symbol_map.items()), "")
    return dataclasses.replace(cfg, pair=pair, strategy=strat,
                               symbol_map={s: s + suffix for s in pair} if suffix else {})


if __name__ == "__main__":
    main()
