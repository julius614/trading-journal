"""Check a price-data CSV and file it where the backtest tools can read it.

    python -m bots.kb.prices inbox/prices/EURUSD_H1.csv --symbol EURUSD [--tz ny_close]

Accepts the repo format (datetime,open,high,low,close,volume,spread), MT5's own export
(Symbols -> Bars -> Export: <DATE> <TIME> <OPEN> ... <SPREAD>, tab separated) and most
OHLC CSVs. Times are converted from the broker's server time to UTC (--tz ny_close, a
fixed hour offset such as 2, or utc if already UTC). The result is written to
data/user/<SYMBOL>_<TF>.csv.gz plus <SYMBOL>_spec.json, and a check report is printed:
timeframe, date range, duplicates, gaps, weekend bars and bad prices.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "user"
TF = {60: "M1", 300: "M5", 900: "M15", 1800: "M30", 3600: "H1", 14400: "H4", 86400: "D1",
      604800: "W1"}


def read_any(path: Path) -> pd.DataFrame:
    """Return a frame with a naive datetime index and open/high/low/close/volume/spread."""
    df = pd.read_csv(path, sep=None, engine="python", dtype=str)
    df.columns = [c.strip().strip("<>").lower() for c in df.columns]
    decimals = df["close"].str.strip().str.split(".").str[1].str.len().fillna(0).max()
    if "date" in df and "time" in df:
        stamp = df["date"].astype(str) + " " + df["time"].astype(str)
    else:
        tcol = next((c for c in ("datetime", "time", "timestamp", "date", "gmt time", "local time")
                     if c in df.columns), None)
        if tcol is None:
            raise ValueError(f"no time column in {list(df.columns)}")
        stamp = df[tcol]
    if stamp.str.fullmatch(r"\d{9,11}").all():
        idx = pd.to_datetime(stamp.astype(int), unit="s")
    else:
        idx = pd.to_datetime(stamp.astype(str).str.replace(".", "-", n=2, regex=False),
                             errors="coerce", utc=True)
        idx = idx.dt.tz_localize(None) if hasattr(idx, "dt") else idx
    for want, alts in {"volume": ("tickvol", "tick_volume", "vol"), "spread": ()}.items():
        if want not in df:
            src = next((a for a in alts if a in df), None)
            df[want] = df[src] if src else 0.0
    out = df[["open", "high", "low", "close", "volume", "spread"]].apply(pd.to_numeric, errors="coerce")
    out.index = pd.DatetimeIndex(idx)
    out = out[out.index.notna()]
    out.attrs["point"] = float(10 ** -int(decimals)) if decimals else 1.0
    return out


def to_utc(index: pd.DatetimeIndex, tz: str) -> pd.DatetimeIndex:
    if tz.lower() == "utc":
        return index.tz_localize("UTC")
    from bots.amd_fx.execution import server_to_utc
    return server_to_utc(index, tz.lower())


def check(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, object]]:
    rep: Dict[str, object] = {"rows_in": len(df)}
    dup = df.index.duplicated(keep="last")
    df = df[~dup].sort_index()
    bad = (df[["open", "high", "low", "close"]].isna().any(axis=1) |
           (df[["open", "high", "low", "close"]] <= 0).any(axis=1) |
           (df["high"] < df[["open", "close", "low"]].max(axis=1)) |
           (df["low"] > df[["open", "close", "high"]].min(axis=1)))
    df = df[~bad]
    step = int(pd.Series(df.index).diff().dt.total_seconds().mode().iloc[0]) if len(df) > 2 else 0
    gaps = pd.Series(df.index).diff().dt.total_seconds()
    weekday_gaps = gaps[(gaps > step * 3) & (gaps < 2 * 86400)] if step else gaps.iloc[:0]
    rep.update(duplicates_removed=int(dup.sum()), bad_rows_removed=int(bad.sum()),
               rows_out=len(df), timeframe=TF.get(step, f"{step}s"),
               start=str(df.index.min()), end=str(df.index.max()),
               intraday_gaps=int(len(weekday_gaps)),
               saturday_bars=int((df.index.dayofweek == 5).sum()),
               has_spread=bool((df["spread"] > 0).any()))
    return df, rep


def file_prices(path: Path, symbol: str, tz: str = "ny_close", out_dir: Path = OUT) -> Dict[str, object]:
    raw = read_any(path)
    point = raw.attrs["point"]
    raw.index = to_utc(raw.index, tz)
    df, rep = check(raw)
    tf = rep["timeframe"]
    out_dir.mkdir(parents=True, exist_ok=True)
    csv = out_dir / f"{symbol}_{tf}.csv.gz"
    o = df.copy()
    o.index.name = "datetime"
    o["spread"] = o["spread"].fillna(0).round().astype(int)
    o.reset_index().to_csv(csv, index=False)
    spec_path = out_dir / f"{symbol}_spec.json"
    spec = json.loads(spec_path.read_text()) if spec_path.exists() else {}
    spec.update(symbol=symbol, point=spec.get("point", point), source=f"user upload: {path.name}",
                time_conversion=f"server tz {tz} -> UTC")
    spec_path.write_text(json.dumps(spec, indent=2))
    rep.update(saved=str(csv.relative_to(ROOT) if csv.is_relative_to(ROOT) else csv), point=spec["point"])
    if rep["saturday_bars"]:
        rep["warning"] = ("bars on Saturday after conversion - the --tz setting is probably wrong "
                          "(most MT5 brokers: ny_close)")
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Check a price CSV and save it to data/user/")
    ap.add_argument("csv", type=Path)
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--tz", default="ny_close", help="ny_close (default), utc, or hours e.g. 2")
    a = ap.parse_args(argv)
    rep = file_prices(a.csv, a.symbol.upper(), a.tz)
    for k, v in rep.items():
        print(f"{k:20s} {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
