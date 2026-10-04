"""Download bar history from your MetaTrader 5 terminal into backtest-ready CSVs (UTC).

    python -m bots.amd_fx.download_history --symbols EURUSD GBPUSD --timeframe M5 --bars 300000
    python -m bots.amd_fx.download_history --list "*500*"        # find your broker's names
    python -m bots.amd_fx.download_history --symbols US500 XAUUSD --timeframe M5 \
        --from 2019-01-01 --out-dir data/intraday --gzip            # + <SYMBOL>_spec.json

Files go to data/amd_fx/<SYMBOL>_<TF>.csv (or --out-dir), replaced on each download, with
<SYMBOL>_spec.json beside them (point size, contract size, currency). How far back you get depends on the terminal's
history and on Tools > Options > Charts > "Max bars in chart" (set it to Unlimited).
Needs Windows, the MT5 terminal running and logged in, and the MetaTrader5 package.
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

import pandas as pd

from .config import load_config
from .data_fetcher import DataFetcher
from .execution import BrokerError, MT5Broker


INTRADAY = {"M1", "M5", "M15", "M30", "H1", "H4"}


def check_utc_sanity(symbol: str, df: pd.DataFrame) -> None:
    """FX has no Saturday bars in UTC. If there are some, the server-time setting is wrong."""
    saturday = int((df.index.dayofweek == 5).sum())
    if saturday:
        raise ValueError(
            f"{symbol}: {saturday} bars land on a Saturday in UTC, so the broker server-time "
            "setting is wrong. Nothing was saved. Set MT5_SERVER_TIMEZONE (usually ny_close) "
            "and try again.")


async def list_symbols(pattern: str) -> None:
    broker = MT5Broker(load_config().broker)
    await broker.connect()
    try:
        names = await broker.list_symbols(pattern)
        print(f"{len(names)} symbol(s) match {pattern!r}:")
        for n in names:
            print(f"  {n}")
    finally:
        await broker.shutdown()


async def download_range(broker, symbol: str, timeframe: str, start: datetime, end: datetime,
                         chunk_days: int = 60, echo=print) -> pd.DataFrame:
    """Fetch [start, end] in date chunks (each overlapping the previous by a day) and
    stitch them, so the history is not capped at ~100k bars per request."""
    parts = []
    t = start
    while t < end:
        t_end = min(t + timedelta(days=chunk_days), end)
        part = await broker.get_rates_range(symbol, timeframe, t - timedelta(days=1), t_end)
        echo(f"  {symbol} {t:%Y-%m-%d} -> {t_end:%Y-%m-%d}: {len(part)} bars")
        if len(part):
            parts.append(part)
        t = t_end
    if not parts:
        raise ValueError(f"{symbol}: the server has no {timeframe} history from {start:%Y-%m-%d}")
    df = pd.concat(parts).sort_index()
    return df[~df.index.duplicated(keep="last")]


async def download(symbols: List[str], timeframe: str, bars: int,
                   out_dir: Optional[str] = None, gzip: bool = False,
                   start: Optional[datetime] = None) -> None:
    cfg = load_config()
    if out_dir:
        cfg = dataclasses.replace(cfg, data_dir=out_dir)
    broker = MT5Broker(cfg.broker)
    await broker.connect()
    print(f"Broker server time setting: {broker.timezone_mode}")
    try:
        fetcher = DataFetcher(broker, cfg)
        for symbol in symbols:
            try:
                if start is not None:   # date chunks: not capped at ~100k bars
                    df = await download_range(broker, symbol, timeframe, start,
                                              datetime.now() + timedelta(days=1))
                else:
                    df = await broker.get_rates(symbol, timeframe, bars)   # closed bars, UTC
                if timeframe in INTRADAY:   # a D1 bar stamped Saturday UTC is a normal Sunday session
                    check_utc_sanity(symbol, df)
                fetcher.history_path(symbol, timeframe).unlink(missing_ok=True)   # replace, don't merge
                path = fetcher.save_history(symbol, df, timeframe)
                if gzip:   # ~5x smaller, so years of M5 data fit in git
                    gz = Path(f"{path}.gz")
                    pd.read_csv(path).to_csv(gz, index=False, compression="gzip")
                    Path(path).unlink()
                    path = gz
                spec = await broker.symbol_spec(symbol)
                spec_path = Path(path).with_name(f"{symbol}_spec.json")
                spec_path.write_text(json.dumps(spec, indent=2))
                print(f"{symbol}: {len(df)} bars {df.index[0]} -> {df.index[-1]} saved to {path}")
            except (BrokerError, ValueError) as exc:   # unknown symbol, bad data: skip, keep going
                print(f"{symbol}: skipped - {exc}")
    finally:
        await broker.shutdown()


def main(argv: Optional[List[str]] = None) -> None:
    p = argparse.ArgumentParser(description="Download MT5 history to CSV (UTC)")
    p.add_argument("--symbols", nargs="+", default=["EURUSD", "GBPUSD"])
    p.add_argument("--timeframe", default="M5", choices=["M1", "M5", "M15", "M30", "H1", "D1"])
    p.add_argument("--bars", type=int, default=300_000, help="~300k M5 bars = ~4 years")
    p.add_argument("--out-dir", help="folder for the CSVs (default data/amd_fx)")
    p.add_argument("--gzip", action="store_true", help="save as <SYMBOL>_<TF>.csv.gz")
    p.add_argument("--from", dest="start", metavar="YYYY-MM-DD",
                   help="download everything since this date in 60-day chunks (ignores --bars)")
    p.add_argument("--list", metavar="PATTERN",
                   help='only list broker symbol names matching e.g. "*500*", "XAU*", "*"')
    a = p.parse_args(argv)
    if a.list:
        asyncio.run(list_symbols(a.list))
        return
    start = datetime.fromisoformat(a.start) if a.start else None
    asyncio.run(download(a.symbols, a.timeframe, a.bars, a.out_dir, a.gzip, start))


if __name__ == "__main__":
    main()
