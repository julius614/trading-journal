"""Load M5 CSVs written by bots.amd_fx.download_history (with --out-dir) plus their
<SYMBOL>_spec.json, and convert MT5 spreads (points) to price units."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd


def load_symbol(data_dir: str | Path, symbol: str, timeframe: str = "M5"
                ) -> Tuple[pd.DataFrame, dict]:
    data_dir = Path(data_dir)
    spec_path = data_dir / f"{symbol}_spec.json"
    if not spec_path.exists():
        raise FileNotFoundError(f"{spec_path} missing - download with "
                                "bots.amd_fx.download_history --out-dir")
    spec = json.loads(spec_path.read_text())
    csv = data_dir / f"{symbol}_{timeframe}.csv"
    df = pd.read_csv(csv if csv.exists() else Path(f"{csv}.gz"))
    df.columns = [c.strip().lower() for c in df.columns]
    tcol = next(c for c in ("datetime", "time", "timestamp", "date") if c in df.columns)
    idx = (pd.to_datetime(df[tcol], unit="s", utc=True) if pd.api.types.is_numeric_dtype(df[tcol])
           else pd.to_datetime(df[tcol].astype(str), utc=True))
    out = df[["open", "high", "low", "close"]].astype(float)
    out["volume"] = df["volume"].astype(float) if "volume" in df else 0.0
    out["spread_price"] = (df["spread"].astype(float) * float(spec["point"])
                           if "spread" in df else 0.0)
    out.index = pd.DatetimeIndex(idx)
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out, spec


def available_symbols(data_dir: str | Path, timeframe: str = "M5") -> List[str]:
    """Symbols that have both a CSV (plain or .gz) and a spec file."""
    d = Path(data_dir)
    names = set()
    for suffix in (f"_{timeframe}.csv", f"_{timeframe}.csv.gz"):
        for p in d.glob(f"*{suffix}"):
            sym = p.name[: -len(suffix)]
            if (d / f"{sym}_spec.json").exists():
                names.add(sym)
    return sorted(names)


def load_all(data_dir: str | Path, timeframe: str = "M5") -> Dict[str, Tuple[pd.DataFrame, dict]]:
    return {s: load_symbol(data_dir, s, timeframe) for s in available_symbols(data_dir, timeframe)}
