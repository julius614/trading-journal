"""Download bar history from your MetaTrader 5 terminal into backtest-ready CSVs (UTC).

    python -m bots.amd_fx.download_history --symbols EURUSD GBPUSD --timeframe M5 --bars 300000

Files go to data/amd_fx/<SYMBOL>_<TF>.csv (replaced on each download). How far back you get depends on the terminal's
history and on Tools > Options > Charts > "Max bars in chart" (set it to Unlimited).
Needs Windows, the MT5 terminal running and logged in, and the MetaTrader5 package.
"""
from __future__ import annotations

import argparse
import asyncio
from typing import List, Optional

import pandas as pd

from .config import load_config
from .data_fetcher import DataFetcher
from .execution import MT5Broker


def check_utc_sanity(symbol: str, df: pd.DataFrame) -> None:
    """FX has no Saturday bars in UTC. If there are some, the server-time setting is wrong."""
    saturday = int((df.index.dayofweek == 5).sum())
    if saturday:
        raise SystemExit(
            f"{symbol}: {saturday} bars land on a Saturday in UTC, so the broker server-time "
            "setting is wrong. Nothing was saved. Set MT5_SERVER_TIMEZONE (usually ny_close) "
            "and try again.")


async def download(symbols: List[str], timeframe: str, bars: int) -> None:
    cfg = load_config()
    broker = MT5Broker(cfg.broker)
    await broker.connect()
    print(f"Broker server time setting: {broker.timezone_mode}")
    try:
        fetcher = DataFetcher(broker, cfg)
        for symbol in symbols:
            df = await broker.get_rates(symbol, timeframe, bars)   # closed bars, UTC
            check_utc_sanity(symbol, df)
            fetcher.history_path(symbol, timeframe).unlink(missing_ok=True)   # replace, don't merge
            path = fetcher.save_history(symbol, df, timeframe)
            print(f"{symbol}: {len(df)} bars {df.index[0]} -> {df.index[-1]} saved to {path}")
    finally:
        await broker.shutdown()


def main(argv: Optional[List[str]] = None) -> None:
    p = argparse.ArgumentParser(description="Download MT5 history to CSV (UTC)")
    p.add_argument("--symbols", nargs="+", default=["EURUSD", "GBPUSD"])
    p.add_argument("--timeframe", default="M5", choices=["M1", "M5", "M15", "H1", "D1"])
    p.add_argument("--bars", type=int, default=300_000, help="~300k M5 bars = ~4 years")
    a = p.parse_args(argv)
    asyncio.run(download(a.symbols, a.timeframe, a.bars))


if __name__ == "__main__":
    main()
