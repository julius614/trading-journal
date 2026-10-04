"""Pre-declared intraday strategy race (written and committed BEFORE the data was seen;
see git history).

    python -m bots.intraday.research.protocol --data-dir data/intraday

Candidates (parameters fixed from the papers, see strategies.py):
    NA  noise-area momentum      every downloaded symbol (indices, gold, oil, FX)
    LH  late-half-hour momentum  symbols on the US session (US indices, gold, oil)
    OR  5-min opening range      every non-FX symbol
Added 2026-10-04, before any data was seen (the user's two "passing" strategies):
    SW  liquidity sweep + FVG    FX (London open) and US indices + gold (NY AM)
    BK  M15 Donchian breakout    every symbol
All trades are flat by the session close. Costs: per-bar MT5 spread + slippage of half the
median spread per side; FX also pays 0.00007 commission per round trip.

Split (one calendar for all symbols, from the earliest to the latest session date):
    discovery  first 60%    validate  next 20%    hold-out  last 20% (reported once)

JOIN:  discovery trades >= 150, discovery PF >= 1.15, and discovery return still > 0 with
       doubled slippage.
KEEP:  validate PF >= 1.05.
PORTFOLIO: equal-weight average of the kept combinations' daily returns (each sized to a
       1% daily-vol target, or 1% risk per trade for OR; 0 on days without trades).
STRONG (all required, measured on validate + hold-out days only):
    - at the largest scale with P(any day <= -5%) < 2% and P(fail) <= 15%,
      P(reach +10% within 12 months) >= 50%  (bootstrap as in statarb_3leg.portfolio)
    - no single calendar year and no single symbol earns more than 50% of the profit.
REPORT ONLY (does not change the verdict): P(+10% within 63 trading days ~ 3 months) per
    scale, with the normal limits and with the user's -4% hard stop.
PHASE 2 (kept combinations only): each parameter moved ~25% (strategies.PERTURBATIONS);
    the plateau holds if every variant still has PF > 1 on discovery + validate. It is a
    check only - parameters are never re-chosen from it.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from ...statarb_3leg.portfolio import bootstrap_paths, challenge_odds
from .data import available_symbols, load_symbol
from .engine import run, stats
from .sessions import SessionData, build_sessions, market_of
from .strategies import PERTURBATIONS, STRATEGIES, Params

PERIODS = ("discovery", "validate", "holdout")
MIN_TRADES, MIN_PF, MIN_VAL_PF = 150, 1.15, 1.05
MAX_P_DAILY, MAX_P_FAIL, MIN_P_PASS_12M = 0.02, 0.15, 0.50
MAX_SHARE = 0.50
SCALES = tuple(np.round(np.arange(0.25, 8.01, 0.25), 2))


def is_oil(symbol: str) -> bool:
    return any(k in symbol.upper() for k in ("OIL", "WTI", "XTI", "BRENT", "XBR"))


def candidates(symbol: str) -> List[str]:
    m = market_of(symbol)
    out = ["NA"]
    if m == "US":
        out.append("LH")
    if m != "FX":
        out.append("OR")
    if m == "FX" or (m == "US" and not is_oil(symbol)):
        out.append("SW")               # FX at London open; US indices and gold at NY AM
    out.append("BK")
    return out


def split_dates(all_dates: List[pd.Timestamp]) -> Tuple[pd.Timestamp, pd.Timestamp]:
    start, end = min(all_dates), max(all_dates)
    span = end - start
    return start + 0.6 * span, start + 0.8 * span


def period_of(dates: pd.Series, cut1: pd.Timestamp, cut2: pd.Timestamp) -> pd.Series:
    return pd.Series(np.where(dates < cut1, "discovery",
                              np.where(dates < cut2, "validate", "holdout")), index=dates.index)


def _sessions(data_dir: str, symbol: str) -> SessionData:
    df, _ = load_symbol(data_dir, symbol)
    return build_sessions(df, symbol, market_of(symbol))


def _run_symbol(args) -> Dict[str, object]:
    data_dir, symbol = args
    sd = _sessions(data_dir, symbol)
    out = {"symbol": symbol, "dates": [pd.Timestamp(d) for d in sd.dates], "runs": {}}
    for name in candidates(symbol):
        f = STRATEGIES[name]
        out["runs"][name] = {"base": run(sd, f), "slip2": run(sd, f, slip_mult=2.0)}
    return out


def combo_table(results: List[Dict[str, object]], cut1, cut2) -> pd.DataFrame:
    rows = []
    for res in results:
        for name, r in res["runs"].items():
            row = {"combo": f"{name}:{res['symbol']}", "strategy": name, "symbol": res["symbol"]}
            for tag, t in (("", r["base"]), ("slip2_", r["slip2"])):
                per = period_of(t["date"], cut1, cut2) if len(t) else pd.Series(dtype=str)
                for p in PERIODS:
                    part = t[per == p] if len(t) else t
                    for k, v in stats(part).items():
                        if tag and k not in ("ret", "pf"):
                            continue
                        row[f"{tag}{p}_{k}"] = v
            rows.append(row)
    return pd.DataFrame(rows)


def select(table: pd.DataFrame) -> Tuple[List[str], List[str]]:
    joined = table[(table["discovery_trades"] >= MIN_TRADES) & (table["discovery_pf"] >= MIN_PF)
                   & (table["slip2_discovery_ret"] > 0)]
    kept = joined[joined["validate_pf"] >= MIN_VAL_PF]
    return list(joined["combo"]), list(kept["combo"])


def portfolio_daily(results: List[Dict[str, object]], kept: List[str]) -> pd.DataFrame:
    """Daily return per kept combo on every session date of its symbol (0 = no trade)."""
    cols = {}
    for res in results:
        for name, r in res["runs"].items():
            combo = f"{name}:{res['symbol']}"
            if combo not in kept:
                continue
            days = pd.DatetimeIndex(res["dates"])
            t = r["base"]
            s = t.groupby("date")["ret"].sum() if len(t) else pd.Series(dtype=float)
            cols[combo] = s.reindex(days, fill_value=0.0)
    return pd.DataFrame(cols).fillna(0.0).sort_index()


THREE_MONTHS = 63          # trading days
HARD_STOP = 0.04           # the user's "stop trading at -4% total"


def odds(daily: np.ndarray, n_paths: int = 10_000, seed: int = 11) -> pd.DataFrame:
    paths = bootstrap_paths(daily, n_paths, 3 * 252, 5, np.random.default_rng(seed))
    rows = []
    for s in SCALES:
        row = challenge_odds(paths, s)
        short = paths[:, :THREE_MONTHS]
        row["p_pass_3m"] = challenge_odds(short, s)["p_pass"]
        row["p_pass_3m_hard4"] = challenge_odds(short, s, max_loss=HARD_STOP)["p_pass"]
        rows.append(row)
    return pd.DataFrame(rows)


def best_scale(table: pd.DataFrame) -> Optional[float]:
    ok = table[(table["p_daily_breach"] < MAX_P_DAILY) & (table["p_fail"] <= MAX_P_FAIL)]
    return float(ok["scale"].max()) if len(ok) else None


def concentration(combo_daily: pd.DataFrame) -> Tuple[float, float]:
    """Largest share of total profit from one calendar year and from one symbol."""
    port = combo_daily.mean(axis=1)
    total = port.sum()
    if total <= 0:
        return float("inf"), float("inf")
    by_year = port.groupby(port.index.year).sum()
    by_symbol = (combo_daily.sum() / combo_daily.shape[1]).groupby(
        lambda c: c.split(":", 1)[1]).sum()
    return float(by_year.max() / total), float(by_symbol.max() / total)


def plateau(data_dir: str, kept: List[str], cut2: pd.Timestamp) -> pd.DataFrame:
    rows = []
    for combo in kept:
        name, symbol = combo.split(":", 1)
        sd = _sessions(data_dir, symbol)
        for p in PERTURBATIONS[name]:
            t = run(sd, STRATEGIES[name], p)
            t = t[t["date"] < cut2] if len(t) else t
            changed = {k: v for k, v in vars(p).items() if v != getattr(Params(), k)}
            rows.append({"combo": combo, "variant": str(changed), **stats(t)})
    return pd.DataFrame(rows)


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description="Pre-declared intraday strategy race")
    ap.add_argument("--data-dir", default="data/intraday")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", help="write the combination table to CSV")
    a = ap.parse_args(argv)

    symbols = available_symbols(a.data_dir)
    if not symbols:
        raise SystemExit(f"no <SYMBOL>_M5.csv + <SYMBOL>_spec.json pairs in {a.data_dir}")
    with ProcessPoolExecutor(a.workers) as pool:
        results = list(pool.map(_run_symbol, [(a.data_dir, s) for s in symbols]))
    all_dates = [d for r in results for d in r["dates"]]
    cut1, cut2 = split_dates(all_dates)
    print(f"\nSymbols: {symbols}")
    print(f"Sessions {min(all_dates):%Y-%m-%d} .. {max(all_dates):%Y-%m-%d}; "
          f"validate from {cut1:%Y-%m-%d}, hold-out from {cut2:%Y-%m-%d}")
    for r in results:
        print(f"  {r['symbol']}: {len(r['dates'])} complete sessions ({market_of(r['symbol'])})")

    table = combo_table(results, cut1, cut2)
    joined, kept = select(table)
    cols = ["combo"] + [f"{p}_{k}" for p in PERIODS for k in ("trades", "ret", "pf")] + \
        ["slip2_discovery_ret"]
    with pd.option_context("display.width", 250, "display.max_columns", None,
                           "display.max_rows", None):
        print("\n== Combinations (ret = sum of daily returns at 1% vol target / 1% risk) ==")
        print(table[cols].to_string(index=False))
    if a.out:
        table.to_csv(a.out, index=False)
    print(f"\nJoined on discovery: {joined}")
    print(f"Kept after validate: {kept}")
    if not kept:
        print("\nVERDICT: nothing survived - no strong strategy in this data. Nothing to build.")
        return

    daily = portfolio_daily(results, kept)
    oos = daily[daily.index >= cut1]
    port = oos.mean(axis=1)
    hold = daily[daily.index >= cut2].mean(axis=1)
    print(f"\n== Portfolio of {len(kept)} combination(s), validate + hold-out "
          f"({cut1:%Y-%m} .. {oos.index.max():%Y-%m}) ==")
    print(f"  return {port.sum():+.2%} (hold-out alone {hold.sum():+.2%}); worst day "
          f"{port.min():+.2%}; max drawdown {(port.cumsum() - port.cumsum().cummax()).min():+.2%}")
    year_share, symbol_share = concentration(oos)
    print(f"  largest share of profit: one year {year_share:.0%}, one symbol {symbol_share:.0%}")

    table_odds = odds(port.to_numpy())
    with pd.option_context("display.float_format", "{:.3f}".format, "display.max_rows", None):
        print("\n== Challenge odds (+10% target, -10% max loss, -5% day; no time limit) ==")
        print(table_odds.to_string(index=False))
    scale = best_scale(table_odds)
    strong = False
    if scale is None:
        print("\nNo scale meets P(day <= -5%) < 2% and P(fail) <= 15%.")
    else:
        row = table_odds[table_odds["scale"] == scale].iloc[0]
        strong = (row.p_pass_12m >= MIN_P_PASS_12M and year_share <= MAX_SHARE
                  and symbol_share <= MAX_SHARE)
        print(f"\nScale {scale:g}x: P(pass) {row.p_pass:.0%}, within 12 months "
              f"{row.p_pass_12m:.0%}, P(fail) {row.p_fail:.0%}, median "
              f"{row.median_months_to_pass:.1f} months")
        print(f"  3-month view: P(+10% within 3 months) {row.p_pass_3m:.0%}; with the -4% "
              f"hard stop {row.p_pass_3m_hard4:.0%}")
    print(f"\nVERDICT: {'STRONG - meets every pre-declared test' if strong else 'NOT strong enough'}")

    pl = plateau(a.data_dir, kept, cut2)
    with pd.option_context("display.width", 200, "display.max_rows", None):
        print("\n== Phase 2 plateau check (discovery + validate, check only) ==")
        print(pl.to_string(index=False))
    bad = pl[~(pl["pf"] > 1.0)]
    print(f"  plateau {'holds' if bad.empty else 'BROKEN for ' + str(sorted(set(bad.combo)))}")


if __name__ == "__main__":
    main()
