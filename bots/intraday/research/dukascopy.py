"""Download long M5 history from Dukascopy's free data feed (your broker keeps only ~1.5
years of M5), priced in UTC, and attach YOUR broker's spreads so costs stay realistic.

    python -m bots.intraday.research.dukascopy --check            # 10-second test first
    python -m bots.intraday.research.dukascopy --from 2019-01-01

Reads the broker files already in data/intraday (<SYMBOL>_M5.csv.gz + _spec.json, from
bots.amd_fx.download_history) and writes data/intraday_duka/<SYMBOL>_M5.csv.gz + spec.

- Prices: Dukascopy 1-minute BID candles (one LZMA .bi5 file per day, UTC), resampled
  to 5 minutes. The price scale (a power of 10) is matched to the broker's prices.
- Spread: the broker's median spread for each UTC hour of the week, taken from the
  broker's own M5 data (Dukascopy's spreads are not what you would pay).
- Volume: Dukascopy volume (used only for the noise-area VWAP).
Days already downloaded are cached in <out>/_cache, so an interrupted run resumes.
"""
from __future__ import annotations

import argparse
import json
import lzma
import random
import shutil
import time as _time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .data import load_symbol

URL = "https://datafeed.dukascopy.com/datafeed/{inst}/{y}/{m:02d}/{d:02d}/BID_candles_min_1.bi5"
# look like a browser; the feed may refuse Python's default user agent
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
           "Accept": "*/*", "Referer": "https://www.dukascopy.com/"}

# one record per minute: seconds from day start, open, close, low, high (ints), volume
RECORD = np.dtype([("t", ">i4"), ("o", ">i4"), ("c", ">i4"), ("l", ">i4"), ("h", ">i4"),
                   ("v", ">f4")])

# broker symbol -> Dukascopy instrument
DEFAULT_MAP: Dict[str, str] = {
    "US500": "USA500IDXUSD", "USTECH100M": "USATECHIDXUSD", "US30": "USA30IDXUSD",
    "DAX": "DEUIDXEUR", "UK100": "GBRIDXGBP", "XAUUSD": "XAUUSD", "WTI": "LIGHTCMDUSD",
    "EURUSD": "EURUSD", "GBPUSD": "GBPUSD", "USDJPY": "USDJPY", "AUDUSD": "AUDUSD",
    "USDCAD": "USDCAD",
}


def decode_bi5(raw: bytes, day: date) -> pd.DataFrame:
    """1-minute candles of one UTC day (raw integer prices, not yet scaled)."""
    cols = ["open", "high", "low", "close", "volume"]
    if not raw:
        return pd.DataFrame(columns=cols, index=pd.DatetimeIndex([], tz="UTC"))
    data = lzma.decompress(raw)
    rec = np.frombuffer(data[: len(data) // RECORD.itemsize * RECORD.itemsize], dtype=RECORD)
    t0 = pd.Timestamp(day, tz="UTC")
    idx = t0 + pd.to_timedelta(rec["t"].astype(np.int64), unit="s")
    df = pd.DataFrame({"open": rec["o"].astype(float), "high": rec["h"].astype(float),
                       "low": rec["l"].astype(float), "close": rec["c"].astype(float),
                       "volume": rec["v"].astype(float)}, index=idx)
    return df[df["volume"] > 0]          # Dukascopy pads closed minutes with flat zero-volume bars


class DownloadError(RuntimeError):
    pass


RETRY_CODES = {429, 500, 502, 503, 504}
PAUSE = 0.2                  # seconds after each live request, to stay under the rate limit
TIMEOUT = 12                 # seconds; a stalled connection is retried sooner
_sleep = _time.sleep         # replaced in tests


def download(url: str, retries: int = 8) -> bytes:
    """The raw file, b"" if it doesn't exist (404). Backs off on rate limiting (503 etc.)."""
    req = urllib.request.Request(url, headers=HEADERS)
    last = ""
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                raw = r.read()
            _sleep(PAUSE)
            return raw
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return b""
            last = f"HTTP {e.code} {e.reason}"
            if e.code not in RETRY_CODES:
                break
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            last = f"{type(e).__name__}: {getattr(e, 'reason', e)}"
        _sleep(min(60.0, 2.0 ** (attempt + 1)) + random.uniform(0, 1))
    raise DownloadError(f"could not download {url} ({last})")


def day_url(inst: str, day: date) -> str:
    return URL.format(inst=inst, y=day.year, m=day.month - 1, d=day.day)   # month is 0-based


def fetch_day(inst: str, day: date, cache: Path, retries: int = 8) -> pd.DataFrame:
    f = cache / inst / f"{day:%Y%m%d}.bi5"
    if f.exists():
        return decode_bi5(f.read_bytes(), day)
    raw = download(day_url(inst, day), retries)      # failures are not cached
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(raw)
    return decode_bi5(raw, day)


def fetch_days(inst: str, days: List[date], cache: Path, workers: int,
               max_missing: float = 0.02) -> List[pd.DataFrame]:
    """All days; failed days are retried once more at the end, one at a time."""
    def safe(d: date) -> Optional[pd.DataFrame]:
        try:
            return fetch_day(inst, d, cache)
        except DownloadError:
            return None

    parts: List[Optional[pd.DataFrame]] = []
    with ThreadPoolExecutor(workers) as pool:
        for i, part in enumerate(pool.map(safe, days), 1):
            parts.append(part)
            if i % 100 == 0 or i == len(days):
                bad = sum(p is None for p in parts)
                print(f"    {inst}: {i}/{len(days)} days ({days[i - 1]})"
                      + (f", {bad} failed so far" if bad else ""), flush=True)
    failed = [i for i, p in enumerate(parts) if p is None]
    for i in failed:
        parts[i] = safe(days[i])
    still = [days[i] for i in failed if parts[i] is None]
    if len(still) > max_missing * len(days):
        raise DownloadError(f"{len(still)} of {len(days)} days could not be downloaded "
                            f"(e.g. {day_url(inst, still[0])}); run again later to fill them")
    if still:
        print(f"  warning: {len(still)} day(s) missing, e.g. {still[0]} - run again to fill",
              flush=True)
    return [p for p in parts if p is not None]


CHECK_DAY = date(2024, 1, 17)    # a normal Wednesday


def check(symbols: List[str]) -> None:
    """Download one known trading day per symbol and show what came back."""
    for sym in symbols:
        inst = DEFAULT_MAP.get(sym, sym)
        url = day_url(inst, CHECK_DAY)
        try:
            raw = download(url, retries=3)
        except DownloadError as e:
            print(f"{sym:<11} {inst:<14} FAILED  {e}", flush=True)
            continue
        if not raw:
            print(f"{sym:<11} {inst:<14} 404 - no such file (wrong instrument name?)", flush=True)
            continue
        df = decode_bi5(raw, CHECK_DAY)
        first = f"{df['close'].iloc[0]:.0f}" if len(df) else "-"
        print(f"{sym:<11} {inst:<14} OK  {len(raw)} bytes, {len(df)} minutes, "
              f"first raw close {first}", flush=True)


def to_m5(m1: pd.DataFrame) -> pd.DataFrame:
    return m1.resample("5min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna(subset=["close"])


def price_scale(raw_close: pd.Series, broker_close: pd.Series) -> float:
    """Power of 10 that maps raw integer prices onto the broker's price level."""
    ratio = float(np.median(broker_close)) / float(np.median(raw_close))
    return 10.0 ** round(np.log10(ratio))


def spread_profile(broker: pd.DataFrame, point: float) -> pd.Series:
    """Median broker spread in POINTS for each UTC hour of the week (0..167)."""
    pts = broker["spread_price"] / point
    how = broker.index.dayofweek * 24 + broker.index.hour
    prof = pts.groupby(how).median()
    return prof.reindex(range(168)).fillna(float(pts.median()))


def build_symbol(symbol: str, inst: str, start: date, end: date, broker_dir: Path,
                 out_dir: Path, workers: int = 2) -> str:
    broker, spec = load_symbol(broker_dir, symbol)
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    days = [d for d in days if d.weekday() != 5]          # no Saturday sessions
    parts = fetch_days(inst, days, out_dir / "_cache", workers)
    if not parts:
        raise DownloadError(f"{symbol}: no data downloaded")
    m1 = pd.concat([p for p in parts if len(p)]).sort_index()
    m5 = to_m5(m1)
    overlap = broker.index.intersection(m5.index)
    if len(overlap) < 500:
        raise RuntimeError(f"{symbol}: too little overlap with broker data to set the price scale")
    scale = price_scale(m5.loc[overlap, "close"], broker.loc[overlap, "close"])
    for c in ("open", "high", "low", "close"):
        m5[c] = m5[c] * scale
    gap = float(np.median(np.abs(m5.loc[overlap, "close"] / broker.loc[overlap, "close"] - 1)))
    prof = spread_profile(broker, float(spec["point"]))
    m5["spread"] = prof.to_numpy()[m5.index.dayofweek * 24 + m5.index.hour]
    out_dir.mkdir(parents=True, exist_ok=True)
    m5.to_csv(out_dir / f"{symbol}_M5.csv.gz", index_label="datetime", compression="gzip")
    meta = dict(spec, source=f"dukascopy:{inst}", price_scale=scale,
                median_gap_vs_broker=round(gap, 5))
    (out_dir / f"{symbol}_spec.json").write_text(json.dumps(meta, indent=2))
    return (f"{symbol} ({inst}): {len(m5)} bars {m5.index[0]} -> {m5.index[-1]}, "
            f"median price gap vs broker {gap:.3%}")


def main(argv: Optional[List[str]] = None) -> None:
    p = argparse.ArgumentParser(description="Long M5 history from Dukascopy + broker spreads")
    p.add_argument("--from", dest="start", default="2019-01-01")
    p.add_argument("--to", dest="end", default=None, help="default: yesterday")
    p.add_argument("--broker-dir", default="data/intraday")
    p.add_argument("--out-dir", default="data/intraday_duka")
    p.add_argument("--symbols", nargs="+", default=list(DEFAULT_MAP))
    p.add_argument("--workers", type=int, default=2, help="parallel downloads (keep low)")
    p.add_argument("--check", action="store_true",
                   help="only test one day per symbol (about 10 seconds)")
    p.add_argument("--clear-cache", action="store_true", help="delete the raw day files at the end")
    a = p.parse_args(argv)
    if a.check:
        check(a.symbols)
        return
    start = date.fromisoformat(a.start)
    end = date.fromisoformat(a.end) if a.end else date.today() - timedelta(days=1)
    out = Path(a.out_dir)
    for sym in a.symbols:
        inst = DEFAULT_MAP.get(sym, sym)
        print(f"{sym}: downloading {inst} {start} -> {end} ...", flush=True)
        try:
            print("  " + build_symbol(sym, inst, start, end, Path(a.broker_dir), out, a.workers),
                  flush=True)
        except Exception as exc:   # keep going with the other symbols
            print(f"  {sym}: FAILED - {exc}", flush=True)
    if a.clear_cache:
        shutil.rmtree(out / "_cache", ignore_errors=True)


if __name__ == "__main__":
    main()
