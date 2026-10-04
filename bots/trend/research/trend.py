"""Daily trend-following across many markets - pre-declared test (written and committed
BEFORE the data was seen; see git history).

    python -m bots.trend.research.trend --data-dir data/trend

Data: D1 bars from the user's MT5 server (bots.amd_fx.download_history --timeframe D1
--out-dir data/trend --gzip), one <SYMBOL>_D1.csv.gz + <SYMBOL>_spec.json per market.
Universe: every downloaded market with >= 5 years of daily bars (no picking markets after
the fact). At least 8 markets are required, otherwise the verdict is "not enough data".

Candidates (classic, published rules; parameters fixed):
    TS  12-month time-series momentum: sign of the last 252-day return
        (Moskowitz, Ooi & Pedersen 2012; Hurst, Ooi & Pedersen 2017)
    MA  50/200-day moving-average crossover: sign(SMA50 - SMA200)
    DC  Donchian breakout (Turtle style): long on a close above the prior 50-day high,
        exit below the prior 25-day low; short mirrored
    ALL equal-weight mix of TS, MA and DC
The signal is known at the close of day t and held over day t+1 (no look-ahead).

Sizing: each market targets 10% annual volatility (60-day EWMA of daily returns),
position capped at 5x; the portfolio is the average across markets trading that day.
Costs on every change of position: half the bar's spread + slippage of half the market's
median spread, per unit traded. Financing (CFD swap): 2% a year of the position held.

Split (one calendar): discovery first 60%, validate next 20%, hold-out last 20% (once).
JOIN:   discovery Sharpe >= 0.4 after costs, and still > 0 with doubled costs.
KEEP:   validate Sharpe >= 0.2.
PORTFOLIO: equal-weight mix of the kept candidates' daily returns.
STRONG (as in the intraday race, on validate + hold-out days only): at the largest scale
    with P(day <= -5%) < 2% and P(fail) <= 15%, P(+10% within 12 months) >= 50%; and no
    single calendar year or market earns more than 50% of the profit.
REPORT ONLY: P(+10% within 3 months), also with the -4% hard stop.
"""
from __future__ import annotations

import argparse
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from ...intraday.research.data import available_symbols, load_symbol
from ...intraday.research.protocol import best_scale, odds

TARGET_VOL = 0.10
MAX_POSITION = 5.0
VOL_SPAN = 60
FINANCING = 0.02
MIN_YEARS, MIN_MARKETS = 5.0, 8
JOIN_SHARPE, KEEP_SHARPE = 0.4, 0.2
MIN_P_PASS_12M, MAX_SHARE = 0.50, 0.50
CANDIDATES = ("TS", "MA", "DC", "ALL")


# ------------------------------------------------------------------ signals (known at close t)
def signal_ts(close: pd.Series, lookback: int = 252) -> pd.Series:
    return np.sign(close / close.shift(lookback) - 1.0).fillna(0.0)


def signal_ma(close: pd.Series, fast: int = 50, slow: int = 200) -> pd.Series:
    f, s = close.rolling(fast).mean(), close.rolling(slow).mean()
    return np.sign(f - s).fillna(0.0)


def signal_dc(high: pd.Series, low: pd.Series, close: pd.Series, entry: int = 50,
              exit_: int = 25) -> pd.Series:
    hi_in = high.shift(1).rolling(entry).max()
    lo_in = low.shift(1).rolling(entry).min()
    hi_out = high.shift(1).rolling(exit_).max()
    lo_out = low.shift(1).rolling(exit_).min()
    pos = np.zeros(len(close))
    c = close.to_numpy()
    for t in range(len(c)):
        p = pos[t - 1] if t else 0.0
        if p == 1 and c[t] < lo_out.iat[t]:
            p = 0.0
        elif p == -1 and c[t] > hi_out.iat[t]:
            p = 0.0
        if p == 0:
            if c[t] > hi_in.iat[t]:
                p = 1.0
            elif c[t] < lo_in.iat[t]:
                p = -1.0
        pos[t] = p
    return pd.Series(pos, index=close.index)


def signals(df: pd.DataFrame) -> Dict[str, pd.Series]:
    s = {"TS": signal_ts(df["close"]), "MA": signal_ma(df["close"]),
         "DC": signal_dc(df["high"], df["low"], df["close"])}
    s["ALL"] = (s["TS"] + s["MA"] + s["DC"]) / 3.0
    return s


# ------------------------------------------------------------------ one market's daily P&L
def market_pnl(df: pd.DataFrame, signal: pd.Series, cost_mult: float = 1.0) -> pd.DataFrame:
    """Daily P&L (fraction of the capital given to this market) of holding `signal`
    (decided at each close) over the next day, vol-targeted, after costs."""
    close = df["close"]
    ret = close.pct_change()
    vol = ret.ewm(span=VOL_SPAN, min_periods=VOL_SPAN).std() * np.sqrt(252)
    size = (TARGET_VOL / vol).clip(upper=MAX_POSITION)
    w = (signal * size).fillna(0.0)                       # position held from close t
    held = w.shift(1).fillna(0.0)                         # earns day t+1's return
    gross = held * ret.fillna(0.0)
    spread_frac = (df["spread_price"] / close).fillna(0.0)
    med = float(spread_frac[spread_frac > 0].median()) if (spread_frac > 0).any() else 0.0
    turnover = (w - w.shift(1).fillna(0.0)).abs()
    trade_cost = turnover * (0.5 * spread_frac + 0.5 * med) * cost_mult
    financing = (held.abs() * FINANCING / 252.0 * cost_mult)  # charged on the position held
    cost = trade_cost + financing                         # trades are paid on the day they're made
    return pd.DataFrame({"gross": gross, "cost": cost, "net": gross - cost, "position": w})


# ------------------------------------------------------------------ portfolio and stats
def portfolio(markets: Dict[str, pd.DataFrame], name: str, cost_mult: float = 1.0
              ) -> Tuple[pd.Series, pd.DataFrame]:
    """(portfolio daily net return, per-market net returns) for one candidate."""
    cols = {}
    for sym, df in markets.items():
        cols[sym] = market_pnl(df, signals(df)[name], cost_mult)["net"]
    per = pd.DataFrame(cols).sort_index()
    active = per.notna()
    port = per.fillna(0.0).sum(axis=1) / active.sum(axis=1).clip(lower=1)
    return port, per


def stats(r: pd.Series) -> Dict[str, float]:
    r = r.dropna()
    if len(r) < 20 or r.std() == 0:
        return {"days": len(r), "ann_ret": float("nan"), "ann_vol": float("nan"),
                "sharpe": float("nan"), "max_dd": float("nan")}
    eq = r.cumsum()
    return {"days": int(len(r)), "ann_ret": round(float(r.mean() * 252), 4),
            "ann_vol": round(float(r.std() * np.sqrt(252)), 4),
            "sharpe": round(float(r.mean() / r.std() * np.sqrt(252)), 3),
            "max_dd": round(float((eq - eq.cummax()).min()), 4)}


def split_dates(index: pd.DatetimeIndex) -> Tuple[pd.Timestamp, pd.Timestamp]:
    start, end = index.min(), index.max()
    return start + 0.6 * (end - start), start + 0.8 * (end - start)


def periods(r: pd.Series, cut1, cut2) -> Dict[str, pd.Series]:
    return {"discovery": r[r.index < cut1], "validate": r[(r.index >= cut1) & (r.index < cut2)],
            "holdout": r[r.index >= cut2]}


def select(table: pd.DataFrame) -> Tuple[List[str], List[str]]:
    joined = table[(table["discovery_sharpe"] >= JOIN_SHARPE) & (table["cost2_discovery_ret"] > 0)]
    kept = joined[joined["validate_sharpe"] >= KEEP_SHARPE]
    return list(joined["candidate"]), list(kept["candidate"])


def concentration(port: pd.Series, per_market: pd.DataFrame) -> Tuple[float, float]:
    total = port.sum()
    if total <= 0:
        return float("inf"), float("inf")
    by_year = port.groupby(port.index.year).sum()
    n = per_market.notna().sum(axis=1).clip(lower=1)
    by_market = per_market.fillna(0.0).div(n, axis=0).sum()
    return float(by_year.max() / total), float(by_market.max() / total)


# ------------------------------------------------------------------ data
def load_markets(data_dir: str) -> Tuple[Dict[str, pd.DataFrame], List[str]]:
    markets, skipped = {}, []
    for sym in available_symbols(data_dir, "D1"):
        df, _ = load_symbol(data_dir, sym, "D1")
        df.index = df.index.normalize()
        df = df[~df.index.duplicated(keep="last")]
        years = (df.index.max() - df.index.min()).days / 365.25
        if years >= MIN_YEARS:
            markets[sym] = df
        else:
            skipped.append(f"{sym} ({years:.1f} y)")
    return markets, skipped


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description="Pre-declared daily trend-following test")
    ap.add_argument("--data-dir", default="data/trend")
    ap.add_argument("--out", help="write the candidate table to CSV")
    a = ap.parse_args(argv)
    markets, skipped = load_markets(a.data_dir)
    print(f"\nMarkets ({len(markets)}): {sorted(markets)}")
    if skipped:
        print(f"Skipped (< {MIN_YEARS:g} years): {skipped}")
    if len(markets) < MIN_MARKETS:
        print(f"\nVERDICT: not enough data - need >= {MIN_MARKETS} markets with "
              f">= {MIN_YEARS:g} years of daily bars.")
        return
    for s, df in sorted(markets.items()):
        print(f"  {s}: {df.index.min():%Y-%m-%d} .. {df.index.max():%Y-%m-%d}")

    runs = {c: portfolio(markets, c) for c in CANDIDATES}
    runs2 = {c: portfolio(markets, c, cost_mult=2.0)[0] for c in CANDIDATES}
    all_idx = runs["TS"][0].index
    cut1, cut2 = split_dates(all_idx)
    print(f"Discovery to {cut1:%Y-%m-%d}, validate to {cut2:%Y-%m-%d}, hold-out to "
          f"{all_idx.max():%Y-%m-%d}")
    rows = []
    for c in CANDIDATES:
        row = {"candidate": c}
        for per, r in periods(runs[c][0], cut1, cut2).items():
            for k, v in stats(r).items():
                row[f"{per}_{k}"] = v
        row["cost2_discovery_ret"] = stats(periods(runs2[c], cut1, cut2)["discovery"])["ann_ret"]
        rows.append(row)
    table = pd.DataFrame(rows)
    cols = ["candidate"] + [f"{p}_{k}" for p in ("discovery", "validate", "holdout")
                            for k in ("ann_ret", "sharpe", "max_dd")] + ["cost2_discovery_ret"]
    with pd.option_context("display.width", 250, "display.max_columns", None):
        print("\n== Candidates (portfolio of all markets; 10% annual vol per market) ==")
        print(table[cols].to_string(index=False))
    if a.out:
        table.to_csv(a.out, index=False)
    joined, kept = select(table)
    print(f"\nJoined on discovery (Sharpe >= {JOIN_SHARPE}): {joined}")
    print(f"Kept after validate (Sharpe >= {KEEP_SHARPE}): {kept}")
    if not kept:
        print("\nVERDICT: nothing survived - no strong trend strategy in this data.")
        return

    port = pd.concat([runs[c][0] for c in kept], axis=1).mean(axis=1)
    per_market = sum(runs[c][1] for c in kept) / len(kept)
    oos = port[port.index >= cut1]
    year_share, market_share = concentration(oos, per_market[per_market.index >= cut1])
    print(f"\n== Portfolio of {kept}, validate + hold-out ==")
    st = stats(oos)
    print(f"  {st['ann_ret']:+.2%}/yr, vol {st['ann_vol']:.2%}, Sharpe {st['sharpe']}, "
          f"max drawdown {st['max_dd']:+.2%}; hold-out alone "
          f"{stats(port[port.index >= cut2])['ann_ret']:+.2%}/yr")
    print(f"  largest share of profit: one year {year_share:.0%}, one market {market_share:.0%}")
    t = odds(oos.to_numpy())
    with pd.option_context("display.float_format", "{:.3f}".format, "display.max_rows", None):
        print("\n== Challenge odds (+10% target, -10% max loss, -5% day; no time limit) ==")
        print(t.to_string(index=False))
    scale = best_scale(t)
    strong = False
    if scale is None:
        print("\nNo scale meets P(day <= -5%) < 2% and P(fail) <= 15%.")
    else:
        row = t[t["scale"] == scale].iloc[0]
        strong = (row.p_pass_12m >= MIN_P_PASS_12M and year_share <= MAX_SHARE
                  and market_share <= MAX_SHARE)
        print(f"\nScale {scale:g}x: P(pass) {row.p_pass:.0%}, within 12 months "
              f"{row.p_pass_12m:.0%}, P(fail) {row.p_fail:.0%}, median "
              f"{row.median_months_to_pass:.1f} months; within 3 months {row.p_pass_3m:.0%} "
              f"(with -4% hard stop {row.p_pass_3m_hard4:.0%})")
    print(f"\nVERDICT: {'STRONG - meets every pre-declared test' if strong else 'NOT strong enough'}")


if __name__ == "__main__":
    main()
