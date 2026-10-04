"""Build long M5 history from HistData.com free 1-minute files, spliced onto the broker's
own recent M5 data (the broker/MT5 server keeps only ~1.5 years).

    python -m bots.intraday.research.histdata

1. Download from https://www.histdata.com/download-free-forex-data/?/ascii/1-minute-bar-quotes
   the yearly 1-minute zip of each market for 2019..2025 (Generic ASCII or MetaTrader
   format, e.g. HISTDATA_COM_ASCII_SPXUSD_M12019.zip), and put the zips (unopened) in
   data/histdata_raw/.
2. Run this. It reads the broker files in data/intraday (<SYMBOL>_M5.csv.gz + spec) and
   writes data/intraday_hd/<SYMBOL>_M5.csv.gz + spec.

Details:
- HistData times are New York standard time all year (UTC-5, no daylight saving);
  converted to UTC.
- Whole UTC days come from one source: the broker's own bars where it has the day
  (>= 80% of HistData's bars), HistData's otherwise (before the broker's history starts,
  and on days the broker is missing).
- Spread: the broker's median spread for each UTC hour of the week (HistData has none),
  as in the Dukascopy importer. Volume: none in HistData for indices (the noise-area
  VWAP then falls back to the average typical price).
- The median price gap between HistData and the broker where they overlap is printed
  and stored in the spec; a large gap means a different underlying (check before use).
"""
from __future__ import annotations

import argparse
import io
import json
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .data import load_symbol
from .dukascopy import spread_profile, to_m5

# broker symbol -> HistData code (US30 has no HistData equivalent)
DEFAULT_MAP: Dict[str, str] = {
    "US500": "SPXUSD", "USTECH100M": "NSXUSD", "DAX": "GRXEUR", "UK100": "UKXGBP",
    "XAUUSD": "XAUUSD", "WTI": "WTIUSD", "EURUSD": "EURUSD", "GBPUSD": "GBPUSD",
    "USDJPY": "USDJPY", "AUDUSD": "AUDUSD", "USDCAD": "USDCAD",
}
EST_OFFSET = pd.Timedelta(hours=5)       # HistData: fixed UTC-5


def parse_m1(text: str) -> pd.DataFrame:
    """A HistData 1-minute file -> UTC bars. Both formats are accepted:
    Generic ASCII 'YYYYMMDD HHMMSS;open;high;low;close;volume' and
    MetaTrader     'YYYY.MM.DD,HH:MM,open,high,low,close,volume'."""
    first = text.lstrip()[:40]
    if ";" in first:
        df = pd.read_csv(io.StringIO(text), sep=";", header=None,
                         names=["dt", "open", "high", "low", "close", "volume"])
        t = pd.to_datetime(df["dt"].astype(str), format="%Y%m%d %H%M%S")
    else:
        df = pd.read_csv(io.StringIO(text), sep=",", header=None,
                         names=["d", "t", "open", "high", "low", "close", "volume"])
        t = pd.to_datetime(df["d"].astype(str) + " " + df["t"].astype(str),
                           format="%Y.%m.%d %H:%M")
    df.index = pd.DatetimeIndex(t + EST_OFFSET).tz_localize("UTC")
    return df[["open", "high", "low", "close", "volume"]].astype(float)


def read_raw(raw_dir: Path, code: str) -> pd.DataFrame:
    """All zips (or extracted CSVs) for one HistData code, merged and sorted."""
    parts = []
    for z in sorted(raw_dir.glob(f"*{code}*.zip")):
        with zipfile.ZipFile(z) as zf:
            for name in zf.namelist():
                if name.lower().endswith(".csv"):
                    parts.append(parse_m1(zf.read(name).decode("utf-8", "replace")))
    for f in sorted(raw_dir.glob(f"DAT_*_{code}_M1_*.csv")):
        parts.append(parse_m1(f.read_text()))
    if not parts:
        raise FileNotFoundError(f"no HistData files for {code} in {raw_dir}")
    df = pd.concat(parts).sort_index()
    return df[~df.index.duplicated(keep="last")]


def years_covered(m1: pd.DataFrame) -> List[int]:
    return sorted(set(m1.index.year))


def build_symbol(symbol: str, code: str, raw_dir: Path, broker_dir: Path,
                 out_dir: Path) -> str:
    broker, spec = load_symbol(broker_dir, symbol)
    hist = to_m5(read_raw(raw_dir, code))
    overlap = broker.index.intersection(hist.index)
    gap = (float(np.median(np.abs(hist.loc[overlap, "close"] / broker.loc[overlap, "close"] - 1)))
           if len(overlap) else float("nan"))
    prof = spread_profile(broker, float(spec["point"]))
    hist["spread"] = prof.to_numpy()[hist.index.dayofweek * 24 + hist.index.hour]
    late = broker.copy()
    late["spread"] = late.pop("spread_price") / float(spec["point"])
    late = late[["open", "high", "low", "close", "volume", "spread"]]
    # whole UTC days from one source: the broker's day where it has at least 80% of
    # HistData's bars for that day (or HistData has none), else HistData's day
    b_days = late.groupby(late.index.normalize()).size()
    h_days = hist.groupby(hist.index.normalize()).size()
    use_broker = {d for d, n in b_days.items() if n >= 0.8 * h_days.get(d, 0)}
    from_hist = hist[~hist.index.normalize().isin(use_broker)]
    from_broker = late[late.index.normalize().isin(use_broker)]
    n_fill = int(from_hist.index.normalize()[from_hist.index >= broker.index[0]].nunique())
    out = pd.concat([from_hist, from_broker]).sort_index()
    out = out[~out.index.duplicated(keep="last")]
    out_dir.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_dir / f"{symbol}_M5.csv.gz", index_label="datetime", compression="gzip")
    meta = dict(spec, source=f"histdata:{code} until {broker.index[0]:%Y-%m-%d}, then broker",
                median_gap_vs_broker=None if np.isnan(gap) else round(gap, 5),
                broker_gap_days_filled=n_fill,
                histdata_years=years_covered(hist))
    (out_dir / f"{symbol}_spec.json").write_text(json.dumps(meta, indent=2))
    gap_txt = f"{gap:.3%}" if np.isfinite(gap) else "n/a (no overlap - add the 2025 file)"
    return (f"{symbol} ({code}): {len(out)} bars {out.index[0]:%Y-%m-%d} -> "
            f"{out.index[-1]:%Y-%m-%d}, HistData years {years_covered(hist)}, "
            f"{n_fill} thin broker days filled from HistData, median price gap vs broker {gap_txt}")


def main(argv: Optional[List[str]] = None) -> None:
    p = argparse.ArgumentParser(description="Long M5 history from HistData + broker data")
    p.add_argument("--raw-dir", default="data/histdata_raw")
    p.add_argument("--broker-dir", default="data/intraday")
    p.add_argument("--out-dir", default="data/intraday_hd")
    p.add_argument("--symbols", nargs="+", default=list(DEFAULT_MAP))
    a = p.parse_args(argv)
    for sym in a.symbols:
        code = DEFAULT_MAP.get(sym, sym)
        try:
            print(build_symbol(sym, code, Path(a.raw_dir), Path(a.broker_dir), Path(a.out_dir)),
                  flush=True)
        except Exception as exc:   # keep going with the other symbols
            print(f"{sym}: skipped - {exc}", flush=True)


if __name__ == "__main__":
    main()
