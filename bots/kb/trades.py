"""Learn from the user's own trades: export from MT5, then analyse.

Export (on the Windows PC with MT5 open and logged in):

    python -m bots.kb.trades export --days 365            # -> inbox/trades/mt5-YYYY-MM-DD.csv

Analyse (anywhere; also accepts a hand-made CSV, see GENERIC_COLUMNS):

    python -m bots.kb.trades report inbox/trades/mt5-2026-10-22.csv

The report goes to knowledge-base/my-trading/<date>-report.md: results by market, side,
session, weekday and holding time, R-multiples where a stop-loss was set, and process
flags (trades without a stop, oversized trades, trading after a losing day).
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
INBOX = ROOT / "inbox" / "trades"
OUT = ROOT / "knowledge-base" / "my-trading"

# one row per closed position; times in UTC
COLUMNS = ["position_id", "symbol", "side", "volume", "open_time", "open_price", "close_time",
           "close_price", "sl", "tp", "profit", "commission", "swap", "fee", "magic", "comment"]
GENERIC_COLUMNS = ["symbol", "side", "open_time", "close_time", "profit"]   # required minimum

DEAL_BUY, DEAL_SELL = 0, 1
ENTRY_IN, ENTRY_OUT, ENTRY_INOUT, ENTRY_OUT_BY = 0, 1, 2, 3


# ----------------------------------------------------------------------- deals -> positions
def positions_from_deals(deals: pd.DataFrame, orders: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Pair MT5 deals (history_deals_get) into closed positions. Times must already be UTC.

    Opening deals give side, volume and the volume-weighted entry; closing deals give the
    volume-weighted exit and close time; profit/commission/swap/fee are summed over all
    deals of the position. The stop-loss/take-profit come from the opening order, if given.
    Positions that are still open, and balance/credit rows, are skipped."""
    d = deals[deals["type"].isin([DEAL_BUY, DEAL_SELL]) & (deals["position_id"] > 0)]
    rows = []
    for pid, g in d.groupby("position_id"):
        ins = g[g["entry"] == ENTRY_IN]
        outs = g[g["entry"].isin([ENTRY_OUT, ENTRY_OUT_BY, ENTRY_INOUT])]
        if ins.empty or outs.empty or outs["volume"].sum() + 1e-9 < ins["volume"].sum():
            continue
        side = "buy" if ins["type"].iloc[0] == DEAL_BUY else "sell"
        vol = float(ins["volume"].sum())
        sl = tp = np.nan
        if orders is not None and len(orders):
            o = orders[orders["position_id"] == pid].sort_values("time_setup")
            if len(o):
                sl = float(o["sl"].iloc[0]) or np.nan
                tp = float(o["tp"].iloc[0]) or np.nan
        rows.append({
            "position_id": int(pid), "symbol": ins["symbol"].iloc[0], "side": side, "volume": vol,
            "open_time": ins["time"].min(),
            "open_price": float((ins["price"] * ins["volume"]).sum() / vol),
            "close_time": outs["time"].max(),
            "close_price": float((outs["price"] * outs["volume"]).sum() / outs["volume"].sum()),
            "sl": sl, "tp": tp, "profit": float(g["profit"].sum()),
            "commission": float(g["commission"].sum()), "swap": float(g["swap"].sum()),
            "fee": float(g["fee"].sum()) if "fee" in g else 0.0,
            "magic": int(ins["magic"].iloc[0]) if "magic" in ins else 0,
            "comment": str(ins["comment"].iloc[0]) if "comment" in ins else ""})
    return pd.DataFrame(rows, columns=COLUMNS).sort_values("open_time").reset_index(drop=True)


def export(days: int, out_dir: Path = INBOX) -> Path:
    """Read closed trades from the running MT5 terminal (Windows) and save a CSV."""
    try:
        import MetaTrader5 as mt5  # type: ignore[import-not-found]
    except ImportError:
        sys.exit("MetaTrader5 package missing - run: pip install MetaTrader5 (Windows only)")
    from bots.amd_fx.execution import server_to_utc

    tz = os.environ.get("MT5_SERVER_TIMEZONE", "ny_close")
    if not mt5.initialize():
        sys.exit(f"Could not connect to MT5 (is the terminal open and logged in?): {mt5.last_error()}")
    try:
        end = datetime.now(timezone.utc) + timedelta(days=2)      # server clock is ahead of UTC
        start = end - timedelta(days=days + 2)
        deals = mt5.history_deals_get(start, end)
        orders = mt5.history_orders_get(start, end)
        acct = mt5.account_info()
    finally:
        mt5.shutdown()
    if not deals:
        sys.exit("No deals found in that period.")
    dd = pd.DataFrame([x._asdict() for x in deals])
    dd["time"] = server_to_utc(pd.to_datetime(dd["time"], unit="s"), tz)
    od = pd.DataFrame([x._asdict() for x in orders]) if orders else pd.DataFrame(
        columns=["position_id", "time_setup", "sl", "tp"])
    pos = positions_from_deals(dd, od)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"mt5-{datetime.now():%Y-%m-%d}.csv"
    pos.to_csv(path, index=False)
    print(f"Saved {len(pos)} closed trades from account {acct.login if acct else '?'} to {path}")
    print("Account number, password and server are NOT in the file. Commit and push it, "
          "then ask Claude to learn from it.")
    return path


# ----------------------------------------------------------------------- loading
_ALIASES = {"type": "side", "direction": "side", "item": "symbol", "instrument": "symbol",
            "open time": "open_time", "time": "open_time", "opened": "open_time",
            "close time": "close_time", "closed": "close_time", "time.1": "close_time",
            "price.1": "close_price", "size": "volume", "lots": "volume",
            "s / l": "sl", "s/l": "sl", "stop": "sl", "stop_loss": "sl", "t / p": "tp", "t/p": "tp",
            "price": "open_price", "open price": "open_price", "close price": "close_price",
            "p&l": "profit", "pnl": "profit", "net": "profit"}


def load_trades(path: Path) -> pd.DataFrame:
    """Our export, or any CSV with at least symbol, side, open_time, close_time, profit
    (common MT5/journal column names are mapped automatically). Naive times = UTC."""
    df = pd.read_csv(path, sep=None, engine="python")
    df.columns = [_ALIASES.get(c.strip().lower(), c.strip().lower()) for c in df.columns]
    df = df.loc[:, ~df.columns.duplicated()]
    missing = [c for c in GENERIC_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name}: missing columns {missing}; found {list(df.columns)}")
    for c in ("open_time", "close_time"):
        t = pd.to_datetime(df[c].astype(str).str.replace(".", "-", regex=False), utc=True, errors="coerce")
        df[c] = t
    df = df.dropna(subset=["open_time", "close_time"])
    df["side"] = df["side"].astype(str).str.lower().str.extract(r"(buy|sell|long|short)")[0] \
        .replace({"long": "buy", "short": "sell"})
    df = df.dropna(subset=["side"])
    for c in ("volume", "open_price", "close_price", "sl", "tp", "commission", "swap", "fee"):
        df[c] = pd.to_numeric(df[c], errors="coerce") if c in df else np.nan
    df["profit"] = pd.to_numeric(df["profit"], errors="coerce")
    df[["commission", "swap", "fee"]] = df[["commission", "swap", "fee"]].fillna(0.0)
    df.loc[df["sl"] == 0, "sl"] = np.nan
    return df.sort_values("open_time").reset_index(drop=True)


# ----------------------------------------------------------------------- analysis
def session_of(ts: pd.Timestamp) -> str:
    h = ts.tz_convert("Europe/London").hour
    if 0 <= h < 7:
        return "Asia (00-07 London)"
    if h < 12:
        return "London (07-12)"
    if h < 17:
        return "London/NY overlap (12-17)"
    return "Late NY (17-24)"


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["net"] = df["profit"] + df["commission"] + df["swap"] + df["fee"]
    df["hold_min"] = (df["close_time"] - df["open_time"]).dt.total_seconds() / 60
    df["session"] = df["open_time"].map(session_of)
    df["weekday"] = df["open_time"].dt.tz_convert("Europe/London").dt.day_name()
    sign = np.where(df["side"] == "buy", 1, -1)
    risk = (df["open_price"] - df["sl"]) * sign                         # price distance at risk
    move = (df["close_price"] - df["open_price"]) * sign
    df["R"] = np.where(risk > 0, move / risk, np.nan)
    df["hold_bucket"] = pd.cut(df["hold_min"], [-1, 15, 60, 240, 1440, 1e9],
                               labels=["<15m", "15m-1h", "1-4h", "4h-1d", ">1d"])
    return df


def group_stats(df: pd.DataFrame, by: str) -> pd.DataFrame:
    g = df.groupby(by, observed=True)
    out = pd.DataFrame({
        "trades": g.size(),
        "win_rate": g["net"].apply(lambda s: (s > 0).mean()).round(2),
        "net": g["net"].sum().round(2),
        "avg_trade": g["net"].mean().round(2),
        "profit_factor": g["net"].apply(
            lambda s: round(s[s > 0].sum() / -s[s < 0].sum(), 2) if (s < 0).any() else np.inf),
        "avg_R": g["R"].mean().round(2)})
    return out.sort_values("net").reset_index()


def flags(df: pd.DataFrame) -> List[str]:
    out = []
    n = len(df)
    no_sl = df["sl"].isna().sum()
    if no_sl:
        out.append(f"{no_sl} of {n} trades ({no_sl / n:.0%}) had no stop-loss at entry.")
    if df["volume"].notna().any():
        med = df.groupby("symbol")["volume"].transform("median")
        big = df[df["volume"] > 3 * med]
        if len(big):
            out.append(f"{len(big)} trades used more than 3x your usual size for that market; "
                       f"their net result: {big['net'].sum():,.2f}.")
    day = df.groupby(df["close_time"].dt.tz_convert("Europe/London").dt.date)["net"].sum()
    after_loss = [d for d, prev in zip(day.index[1:], day.values[:-1]) if prev < 0]
    if len(after_loss):
        nxt = day.loc[after_loss]
        out.append(f"Days that followed a losing day: {len(nxt)}, net {nxt.sum():,.2f} "
                   f"(other days: {day.drop(after_loss).sum():,.2f}).")
    quick = df[df["hold_min"] < 2]
    if len(quick):
        out.append(f"{len(quick)} trades were closed within 2 minutes (net {quick['net'].sum():,.2f}) - "
                   "check for impulsive entries.")
    worst = df.nsmallest(1, "net")
    if len(worst) and df["net"].sum() != 0:
        w = worst.iloc[0]
        out.append(f"Largest single loss: {w['net']:,.2f} on {w['symbol']} "
                   f"({w['open_time']:%Y-%m-%d}).")
    return out


def md(df: pd.DataFrame) -> str:
    if df.empty:
        return "_(none)_\n"
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join("" if (isinstance(v, float) and np.isnan(v)) else str(v)
                                       for v in r.values) + " |")
    return "\n".join(lines) + "\n"


def report(path: Path, out_dir: Path = OUT) -> Path:
    df = enrich(load_trades(path))
    if df.empty:
        raise ValueError("no closed trades found")
    net = df["net"]
    streak = cur = 0
    for v in net:
        cur = cur + 1 if v < 0 else 0
        streak = max(streak, cur)
    wins, losses = net[net > 0], net[net < 0]
    head = {
        "trades": len(df), "from": f"{df['open_time'].min():%Y-%m-%d}",
        "to": f"{df['close_time'].max():%Y-%m-%d}", "net": round(net.sum(), 2),
        "win_rate": round((net > 0).mean(), 2),
        "avg_win": round(wins.mean(), 2) if len(wins) else 0,
        "avg_loss": round(losses.mean(), 2) if len(losses) else 0,
        "profit_factor": round(wins.sum() / -losses.sum(), 2) if len(losses) else np.inf,
        "avg_R (trades with SL)": round(df["R"].mean(), 2) if df["R"].notna().any() else "n/a",
        "costs (commission+swap+fee)": round((df["commission"] + df["swap"] + df["fee"]).sum(), 2),
        "longest losing streak": streak}
    lines = [f"# My trading - report from `{path.name}`\n",
             "Generated by `python -m bots.kb.trades report`. Facts only; the lessons drawn "
             "from it go to `knowledge-base/LESSONS.md`.\n",
             "\n## Overall\n\n" + md(pd.DataFrame([head]).T.reset_index().rename(columns={"index": "metric", 0: "value"})),
             "\n## Process flags\n\n" + ("\n".join(f"- {f}" for f in flags(df)) or "- none") + "\n"]
    for by, title in (("symbol", "By market"), ("side", "Buy vs sell"), ("session", "By session (entry time)"),
                      ("weekday", "By weekday"), ("hold_bucket", "By holding time")):
        lines.append(f"\n## {title}\n\n" + md(group_stats(df, by)))
    if len(df) < 30:
        lines.append(f"\n**Small sample ({len(df)} trades):** treat every pattern above as a "
                     "question to watch, not a conclusion.\n")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{datetime.now():%Y-%m-%d}-{path.stem}-report.md"
    out.write_text("\n".join(lines))
    print(f"Report written to {out}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Export and analyse your own trades")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export", help="save closed trades from the running MT5 terminal")
    e.add_argument("--days", type=int, default=365)
    r = sub.add_parser("report", help="analyse a trades CSV")
    r.add_argument("csv", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "export":
        export(a.days)
    else:
        report(a.csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
