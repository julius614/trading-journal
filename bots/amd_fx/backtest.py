"""Replay historical bars through the live Bot on a PaperBroker.

Uses exactly the same Bot.step(), strategy, risk manager and trade manager as live
trading, so a replay tests the real code path.

    python -m bots.amd_fx.backtest EURUSD=data/EURUSD_M5.csv GBPUSD=data/GBPUSD_M5.csv \
        --balance 10000 --spread 0.8 --commission 7 --out trades.csv
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .config import AppConfig, load_config
from .data_fetcher import load_ohlcv_csv
from .execution import PaperBroker, Trade, _TF_MINUTES
from .main import Bot, setup_logging

log = logging.getLogger("amd_fx.backtest")


def summarize_trades(trades: List[Trade]) -> Dict[str, float]:
    """Headline stats in R multiples (pnl / planned risk)."""
    if not trades:
        return {"trades": 0}
    r = pd.Series([t.r_multiple for t in trades])
    wins, losses = r[r > 0], r[r <= 0]
    equity = r.cumsum()
    max_dd = float((equity - equity.cummax().clip(lower=0)).min())
    return {
        "trades": int(len(r)),
        "win_rate": round(len(wins) / len(r), 4),
        "expectancy_r": round(float(r.mean()), 4),
        "total_r": round(float(r.sum()), 4),
        "profit_factor": round(float(wins.sum() / -losses.sum()), 4) if losses.sum() < 0 else float("inf"),
        "max_drawdown_r": round(max_dd, 4),
        "total_pnl": round(float(sum(t.pnl for t in trades)), 2),
    }


async def run_replay(
    cfg: AppConfig,
    csv_paths: Dict[str, str],
    balance: float = 10_000.0,
    spread_pips: float = 0.8,
    commission_per_lot: float = 0.0,
    out: Optional[str] = None,
    frames: Optional[Dict[str, pd.DataFrame]] = None,
) -> Dict[str, object]:
    """Replay bars (from CSV paths, or already-loaded `frames`) and return results."""
    data = dict(frames or {})
    for symbol, path in csv_paths.items():
        data[symbol] = load_ohlcv_csv(path)
    if not data:
        raise ValueError("no data to replay")
    cfg = dataclasses.replace(cfg, strategy=dataclasses.replace(cfg.strategy, symbols=tuple(data)))
    broker = PaperBroker(balance, spread_pips, commission_per_lot, cfg.strategy.timeframe)
    for symbol, df in data.items():
        broker.load_bars(symbol, df)
    bot = Bot(cfg, broker, state_path=None)
    await broker.connect()

    bar_len = pd.Timedelta(minutes=_TF_MINUTES[cfg.strategy.timeframe])
    timeline = sorted(set().union(*(df.index for df in broker.data.values())))
    for ts in timeline:
        broker.advance(ts)
        await bot.step((ts + bar_len).to_pydatetime())

    # flatten whatever is still open at the end of the data
    await bot.trades.close_all("end of replay")
    bot.closed_trades += await bot.trades.manage((timeline[-1] + bar_len).to_pydatetime())

    stats = summarize_trades(bot.closed_trades)
    stats["start_balance"] = balance
    stats["end_balance"] = round(broker.balance, 2)
    stats["signals"] = len(bot.signals)
    if out:
        rows = [dict(dataclasses.asdict(t), r_multiple=t.r_multiple) for t in bot.closed_trades]
        pd.DataFrame(rows).to_csv(out, index=False)
    print("\n== AMD replay results ==")
    for k, v in stats.items():
        print(f"  {k:>15}: {v}")
    if bot.closed_trades:
        by_sym = pd.DataFrame([{"symbol": t.symbol, "r": t.r_multiple} for t in bot.closed_trades])
        print("\n== By symbol (R) ==")
        print(by_sym.groupby("symbol")["r"].agg(["count", "mean", "sum"]).round(3))
    return {"stats": stats, "trades": bot.closed_trades, "signals": bot.signals,
            "deals": broker.deals}


def main(argv: Optional[List[str]] = None) -> None:
    p = argparse.ArgumentParser(description="Replay the AMD bot on historical bars")
    p.add_argument("data", nargs="+", metavar="SYMBOL=CSV")
    p.add_argument("--balance", type=float, default=10_000.0)
    p.add_argument("--spread", type=float, default=0.8, help="spread in pips")
    p.add_argument("--commission", type=float, default=0.0, help="per lot, round trip")
    p.add_argument("--out", help="write closed trades to CSV")
    p.add_argument("--log-level", default="WARNING")
    a = p.parse_args(argv)
    cfg = load_config()
    setup_logging(cfg.log_dir, a.log_level)
    paths = dict(item.split("=", 1) for item in a.data)
    asyncio.run(run_replay(cfg, paths, a.balance, a.spread, a.commission, a.out))


if __name__ == "__main__":
    np.seterr(all="ignore")
    main()
