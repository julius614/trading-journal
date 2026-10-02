"""Command-line runner for the 15-minute ORB backtest.

Example:
    python run_backtest.py --csv data/SPY_5min.csv --mode bnr --stop mid --target 2 \
        --slippage 0.01 --out trades.csv
"""
from __future__ import annotations

import argparse

import pandas as pd

from orb import ORBConfig, backtest, breakdown, load_csv, summarize, to_15min


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="15-minute ORB backtest (Max way rules)")
    p.add_argument("--csv", required=True, help="intraday OHLCV CSV (1-, 5- or 15-minute bars)")
    p.add_argument("--tz", default="America/New_York", help="exchange timezone")
    p.add_argument("--session-start", default="09:30")
    p.add_argument("--session-end", default="16:00")
    p.add_argument("--mode", choices=["breakout", "bnr"], default="breakout")
    p.add_argument("--stop", choices=["mid", "opposite"], default="mid")
    p.add_argument("--target", default="2", help="target in R (e.g. 1, 2) or 'eod'")
    p.add_argument("--no-failed-exit", action="store_true",
                   help="don't exit when a bar closes back inside the range")
    p.add_argument("--long-only", action="store_true")
    p.add_argument("--short-only", action="store_true")
    p.add_argument("--bias", action="store_true",
                   help="only trade in the direction of today's OR vs yesterday's")
    p.add_argument("--max-or-width", type=float, help="skip days with OR width above this %%")
    p.add_argument("--min-or-width", type=float, help="skip days with OR width below this %%")
    p.add_argument("--slippage", type=float, default=0.0, help="per share, each side")
    p.add_argument("--commission", type=float, default=0.0, help="per share, round trip")
    p.add_argument("--out", help="write the trade list to this CSV")
    return p.parse_args(argv)


def main(argv=None):
    a = parse_args(argv)
    cfg = ORBConfig(
        session_start=a.session_start, session_end=a.session_end, mode=a.mode, stop=a.stop,
        target_r=None if a.target.lower() == "eod" else float(a.target),
        exit_on_failed=not a.no_failed_exit,
        allow_long=not a.short_only, allow_short=not a.long_only, use_bias=a.bias,
        max_or_width_pct=a.max_or_width, min_or_width_pct=a.min_or_width,
        slippage=a.slippage, commission=a.commission,
    )
    bars = to_15min(load_csv(a.csv, tz=a.tz), cfg)
    trades = backtest(bars, cfg)

    days = len(set(bars.index.date))
    print(f"Days in data: {days}   Trades: {len(trades)}")
    print(f"Config: {cfg}\n")
    print("== Summary (R multiples) ==")
    for k, v in summarize(trades).items():
        print(f"  {k:>15}: {v}")
    if not trades.empty:
        with pd.option_context("display.width", 160, "display.max_columns", None):
            print("\n== By year ==");        print(breakdown(trades, "year"))
            print("\n== By side ==");        print(breakdown(trades, "side"))
            print("\n== By exit reason ==");  print(breakdown(trades, "exit_reason"))
    if a.out:
        trades.to_csv(a.out, index=False)
        print(f"\nTrades written to {a.out}")


if __name__ == "__main__":
    main()
