"""Run the BACKTEST_SPEC.md setups and write reports/<setup>/ plus reports/COMPARISON.md.

    python -m bots.spec10.run                 # everything (about 10-20 minutes on 4 CPUs)
    python -m bots.spec10.run --only S5 S6    # some setups

Per setup: sweep the whole grid -> choose the best combination on IN-SAMPLE expectancy
(first 70% of dates, costs x1, >= 30 trades) -> report that one combination in- and
out-of-sample at costs x0/x1/x2 -> random-entry baseline (100 runs) -> walk-forward
(2y train / 6m test) -> verdict. PASS = out-of-sample expectancy > 0 at costs x1 AND
out-of-sample net beats the 95th percentile of the random-entry runs.
"""
from __future__ import annotations

import argparse
import multiprocessing as mp
import sys
from pathlib import Path
from typing import Dict, List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from bots.intraday.research.data import load_symbol

from . import strategies as S
from .engine import (EQUITY, CostModel, SweepResult, choose_best, fx_costs, in_out_split,
                     index_costs, price_trades, random_entry_totals, stats, walk_forward)

ROOT = Path(__file__).resolve().parents[2]
LONG, SHORT = ROOT / "data" / "intraday_hd", ROOT / "data" / "intraday"
REPORTS = ROOT / "reports"
EVENTS = ROOT / "data" / "events.csv"

INDEX_MAIN, INDEX_EXTRA = ["US500", "USTECH100M"], ["US30"]
FX_MAIN, FX_EXTRA = ["EURUSD", "GBPUSD"], ["USDJPY", "AUDUSD"]

SETUPS: Dict[str, dict] = {
    "S1B_orb_index": dict(fn=S.s1b, kind="index", grid=S.grid(or_min=[5, 15, 30]),
                          title="Strategy 1B - Opening Range Breakout (QQQ/SPY stand-ins)"),
    "S2_intraday_momentum": dict(fn=S.s2, kind="index",
                                 grid=S.grid(variant=["base", "2B"], skip_small=[False, True]),
                                 title="Strategy 2 - first half-hour predicts last half-hour"),
    "S3_news_momentum": dict(fn=S.s3, kind="index",
                             grid=S.grid(event=["FOMC", "CPI", "NFP", "all"], variant=["base", "2B"]),
                             title="Strategy 3 - intraday momentum on FOMC/CPI/NFP days"),
    "S4_vwap_trend": dict(fn=S.s4, kind="index",
                          grid=S.grid(check_every=[5, 15], buffer=[0.0, 0.0005, 0.001]),
                          title="Strategy 4 - VWAP trend-following"),
    "S5_london_fix": dict(fn=S.s5, kind="fx",
                          grid=S.grid(exit_time=["16:30", "17:00", "17:30"], min_move=[0, 5, 10],
                                      days=["all", "last1", "last3"]),
                          title="Strategy 5 - London 4pm fix reversal"),
    "S6_tokyo_ecb_fix": dict(fn=S.s6, kind="fx",
                             grid=S.grid(window=[1, 2, 3], fix=["Tokyo", "ECB", "both"]),
                             title="Strategy 6 - Tokyo & ECB fix reversals"),
    "S7_round_fade": dict(fn=S.s7, kind="fx_bars",
                          grid=S.grid(entry_buffer=[0, 2, 5], stop_pips=[10, 15, 25],
                                      target_R=[1, 1.5, 2], approach_atr=[1, 2]),
                          title="Strategy 7 - round-number fade"),
    "S8_round_break": dict(fn=S.s8, kind="fx_bars",
                           grid=S.grid(break_pips=[2, 5, 10], stop_pips=[5, 10], target_R=[1, 2, 3]),
                           title="Strategy 8 - stop-run continuation through round numbers"),
    "S9_sweep_M15": dict(fn=S.s9, kind="fx_M15",
                         grid=S.grid(N=[10, 20, 50], over=[0.1, 0.25, 0.5], target_R=[1, 2, 3],
                                     stop_buffer=[0, 1, 2]),
                         title="Strategy 9 - liquidity sweep reversal, 15-minute bars"),
    "S9_sweep_H1": dict(fn=S.s9, kind="fx_H1",
                        grid=S.grid(N=[10, 20, 50], over=[0.1, 0.25, 0.5], target_R=[1, 2, 3],
                                    stop_buffer=[0, 1, 2]),
                        title="Strategy 9 - liquidity sweep reversal, 1-hour bars"),
}

NOT_TESTABLE = {
    "S1_orb_stocks_in_play": "needs 1-minute + daily data for the full US stock universe "
                             "including delisted stocks; we only have index CFDs.",
    "S10_liquidity_provision": "needs order-book (Level 2) data and queue modelling; the spec "
                               "itself says 1-minute bars cannot test it honestly.",
}

NOTES = [
    "Data: M5 bars only (no 1-minute bars, no bid/ask quotes). Fills use M5 bar opens and "
    "highs/lows; stop-before-target is assumed whenever one bar covers both.",
    "Long history 2019-2026: HistData M5 until 2025, then the MetaQuotes-Demo broker feed "
    "(data/intraday_hd). Short history (~1.5 years, 2025-2026, broker only): USDJPY, AUDUSD, "
    "US30 - reported separately as an extra check, low confidence.",
    "US500 / USTECH100M are broker index CFDs used as stand-ins for SPY / QQQ, not the ETFs. "
    "Their costs are the broker's own bar spread (median where unknown) plus half a spread of "
    "slippage per market/stop fill; no commission; 4x leverage cap. That is roughly 3-4 basis "
    "points per round trip - about 4-5x the spec's ETF costs (~0.8 bp on SPY), so for the "
    "ETFs themselves the truth would sit between the x0 and x1 columns.",
    "FX costs are the spec defaults (0.8 pip EURUSD / 1.2 pip others spread, 0.2 pip slippage "
    "on market/stop fills, 3.5 USD per 100k per side) - not real bid/ask around the fixes.",
    "These markets/years overlap earlier tests in this repo, so this is not a fully fresh "
    "sample; the out-of-sample part (last 30% of dates) was touched once, here.",
    "1R = 0.5% of the 100,000 starting equity (500) for every setup, including the ones "
    "without a stop (1x notional), so R is comparable. No compounding.",
]


# ----------------------------------------------------------------------- data + context
def load(sym: str) -> pd.DataFrame:
    d = LONG if (LONG / f"{sym}_spec.json").exists() else SHORT
    df, spec = load_symbol(d, sym)
    df.attrs["point"] = float(spec["point"])
    return df


def costs_for(sym: str, df: pd.DataFrame) -> CostModel:
    if len(sym) == 6 and sym[:3] in {"EUR", "GBP", "USD", "AUD"}:
        return fx_costs(sym)
    sp = df["spread_price"]
    return index_costs(float(sp[sp > 0].median()), df.attrs["point"])


def context(kind: str, syms: List[str], data: Dict[str, pd.DataFrame],
            costs: Dict[str, CostModel]) -> dict:
    markets = {s: data[s] for s in syms}
    ctx = {"markets": markets}
    if kind == "index":
        ctx["sessions"] = {s: S.us_session(markets[s]) for s in syms}
        if EVENTS.exists():
            ctx["events"] = pd.read_csv(EVENTS)
    elif kind == "fx_bars":
        ctx["bars"] = {s: S.make_bars(markets[s]) for s in syms}
        ctx["appr"] = {s: S.approaches(s, ctx["bars"][s]) for s in syms}
    elif kind in ("fx_M15", "fx_H1"):
        rule, step = ("15min", pd.Timedelta(minutes=15)) if kind == "fx_M15" else ("1h", pd.Timedelta(hours=1))
        ctx["bars"] = {s: S.make_bars(S.resample(markets[s], rule), step) for s in syms}
        ctx["spreads"] = {s: costs[s].spread for s in syms}
    return ctx


CTX: Dict[str, dict] = {}


def _job(args):
    name, group, params = args
    ctx = CTX[f"{SETUPS[name]['kind']}:{group}"]
    return SETUPS[name]["fn"](**ctx, **params)


def run_grid(pool, name: str, group: str, params_list: List[dict]) -> List[SweepResult]:
    out = pool.map(_job, [(name, group, p) for p in params_list], chunksize=1)
    return [SweepResult(p, t) for p, t in zip(params_list, out)]


# ----------------------------------------------------------------------- reporting helpers
def bdays(a, b) -> pd.DatetimeIndex:
    return pd.bdate_range(pd.Timestamp(a).tz_localize(None).normalize(),
                          pd.Timestamp(b).tz_localize(None).normalize(), tz="UTC")


def fmt(v) -> str:
    if isinstance(v, float) and np.isfinite(v) and v.is_integer() and abs(v) >= 100:
        return f"{v:,.0f}"
    if isinstance(v, float):
        return "nan" if not np.isfinite(v) else (f"{v:,.2f}" if abs(v) >= 100 else f"{v:.4g}")
    return str(v)


def md_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_(none)_\n"
    cols = list(df.columns)
    lines = ["| " + " | ".join(map(str, cols)) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(fmt(r[c]) for c in cols) + " |")
    return "\n".join(lines) + "\n"


STAT_ROWS = ["trades", "win_rate", "avg_win", "avg_loss", "expectancy_R", "profit_factor",
             "net", "net_pct", "cagr", "sharpe", "max_dd_pct", "longest_losing_streak",
             "top5_share"]


def plots(df: pd.DataFrame, cut: pd.Timestamp, out: Path, title: str) -> None:
    daily = df.groupby(pd.to_datetime(df["exit_time"]).dt.normalize())["net"].sum().sort_index()
    eq = EQUITY + daily.cumsum()
    dd = (eq / eq.cummax().clip(lower=EQUITY) - 1) * 100
    for series, fname, ylab in ((eq, "equity_curve.png", "equity (USD)"),
                                (dd, "drawdown.png", "drawdown (%)")):
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(series.index, series.values, lw=1.2, color="#2a6f97")
        if fname == "drawdown.png":
            ax.fill_between(series.index, series.values, 0, color="#c44e52", alpha=0.3)
        ax.axvline(cut, color="#555", ls="--", lw=1)
        ax.text(cut, ax.get_ylim()[1], " out-of-sample ->", va="top", fontsize=8, color="#555")
        ax.set_title(f"{title} (chosen combination, costs x1)", fontsize=10)
        ax.set_ylabel(ylab)
        ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(out / fname, dpi=110)
        plt.close(fig)


# ----------------------------------------------------------------------- one setup
def evaluate(pool, name: str, data, costs) -> dict:
    cfg = SETUPS[name]
    kind = cfg["kind"]
    out = REPORTS / name
    out.mkdir(parents=True, exist_ok=True)
    main = INDEX_MAIN if kind == "index" else FX_MAIN
    extra = INDEX_EXTRA if kind == "index" else FX_EXTRA
    if name.startswith("S3") and not EVENTS.exists():
        (out / "summary.md").write_text(f"# {cfg['title']}\n\nNOT RUN - data/events.csv missing.\n")
        return {"name": name, "verdict": "NOT RUN"}

    results = run_grid(pool, name, "main", cfg["grid"])
    start = min(data[s].index[0] for s in main)
    end = max(data[s].index[-1] for s in main)
    cut = in_out_split(start, end)
    best, is_table = choose_best(results, costs, cut)

    # every combination, in- and out-of-sample (OOS shown for transparency only)
    allc = is_table.copy()
    oos_cols = []
    for r in results:
        p = price_trades([t for t in r.trades if t.entry_time >= cut], costs, 1.0)
        s = stats(p)
        oos_cols.append({"oos_trades": s["trades"], "oos_exp_R": s["expectancy_R"], "oos_net": s["net"]})
    allc = pd.concat([allc, pd.DataFrame(oos_cols)], axis=1)
    allc.to_csv(out / "all_combinations.csv", index=False)

    lines = [f"# {cfg['title']}\n",
             f"Markets: {', '.join(main)} (M5, {start.date()} -> {end.date()}). "
             f"In-sample before {cut.date()}, out-of-sample after.\n"]
    rec = {"name": name, "title": cfg["title"]}
    if best is None:
        lines.append("\n**No combination had >= 30 in-sample trades - cannot be evaluated.**\n")
        lines.append("\n## All combinations (in-sample, costs x1)\n\n" + md_table(is_table))
        (out / "summary.md").write_text("\n".join(lines))
        rec.update(verdict="FAIL (too few trades)", oos_trades=0, oos_exp=np.nan, sharpe=np.nan,
                   dd=np.nan, beats=False)
        return rec

    chosen = results[best]
    trades = chosen.trades
    is_tr = [t for t in trades if t.entry_time < cut]
    oos_tr = [t for t in trades if t.entry_time >= cut]
    is_days, oos_days = bdays(start, cut), bdays(cut, end)

    table = {}
    for m in (0.0, 1.0, 2.0):
        table[f"IS x{m:g}"] = stats(price_trades(is_tr, costs, m), is_days)
        table[f"OOS x{m:g}"] = stats(price_trades(oos_tr, costs, m), oos_days)
    st = pd.DataFrame(table).loc[STAT_ROWS].reset_index().rename(columns={"index": "metric"})

    oos1 = price_trades(oos_tr, costs, 1.0)
    rnd = random_entry_totals(oos_tr, costs, runs=100)
    p95 = float(np.percentile(rnd, 95))
    oos_net = float(oos1["net"].sum()) if len(oos1) else 0.0
    rank = float((rnd < oos_net).mean() * 100)
    oos_exp = table["OOS x1"]["expectancy_R"]
    beats = oos_net > p95
    verdict = "PASS" if (len(oos_tr) and oos_exp > 0 and beats) else "FAIL"

    wf = walk_forward(results, costs, start, end)

    full = price_trades(trades, costs, 1.0)
    full["period"] = np.where(full["entry_time"] < cut, "in-sample", "out-of-sample")
    full.to_csv(out / "trades.csv", index=False)
    mon = full.groupby(pd.to_datetime(full["exit_time"]).dt.tz_localize(None).dt.to_period("M"))["net"].sum()
    pd.DataFrame({"month": mon.index.astype(str), "net_usd": mon.round(2).values,
                  "return_pct": (mon / EQUITY * 100).round(3).values}).to_csv(out / "monthly_returns.csv", index=False)
    plots(full, cut, out, cfg["title"])

    lines += [f"\n## Verdict: **{verdict}**\n",
              f"Out-of-sample expectancy at costs x1 = {oos_exp} R over {len(oos_tr)} trades; "
              f"out-of-sample net {oos_net:,.0f} USD vs random-entry 95th percentile "
              f"{p95:,.0f} USD (strategy beats {rank:.0f}% of 100 random runs).\n",
              f"\nChosen on in-sample data only: `{chosen.params}`\n",
              "\n## Chosen combination: costs x0 / x1 / x2, in-sample vs out-of-sample\n\n" + md_table(st)]

    # per-market breakdown and buy-and-hold
    pm = []
    for sym in main:
        sub = oos1[oos1["symbol"] == sym]
        s = stats(sub)
        px = data[sym]["close"]
        bh = (px[px.index >= cut].iloc[-1] / px[px.index >= cut].iloc[0] - 1) * 100
        pm.append({"symbol": sym, "oos_trades": s["trades"], "oos_exp_R": s["expectancy_R"],
                   "oos_net_pct": s["net_pct"], "buy_and_hold_oos_pct": round(bh, 2)})
    lines.append("\n## Out-of-sample by market (costs x1) and buy-and-hold of the same market\n\n"
                 + md_table(pd.DataFrame(pm)))
    if kind.startswith("fx"):
        lines.append("\nBuy-and-hold is not a meaningful benchmark for FX pairs (shown for completeness).\n")
    if name.startswith("S9") and len(oos1):
        by = oos1.groupby("tag").agg(trades=("R", "size"), exp_R=("R", "mean"), net=("net", "sum")).reset_index()
        by = by.rename(columns={"tag": "session (entry, UTC hours)"})
        lines.append("\n## Out-of-sample by session (Asia 22-07, London 07-13, New York 13-22 UTC)\n\n" + md_table(by))
        allp = price_trades(trades, costs, 1.0)
        lines.append("\nFull period by session:\n\n" + md_table(
            allp.groupby("tag").agg(trades=("R", "size"), exp_R=("R", "mean")).reset_index()))
        tr = allc.groupby("target_R").agg(is_exp_R=("is_exp_R", "mean"), oos_exp_R=("oos_exp_R", "mean")).reset_index()
        lines.append("\n## Does it only work at 2R-3R? Mean expectancy of all combinations by target\n\n" + md_table(tr))
    if name.startswith("S4"):
        days_n = full.groupby(pd.to_datetime(full["entry_time"]).dt.normalize()).size()
        lines.append(f"\nPositions per trading day (chosen combination): mean {days_n.mean():.2f}, "
                     f"max {days_n.max()}.\n")
    if name.startswith("S3"):
        ev = pd.read_csv(EVENTS)
        lines.append(f"\n**Trade count warning:** chosen combination has {len(trades)} trades in total "
                     f"({len(oos_tr)} out-of-sample). The spec says not to trust fewer than 50.\n"
                     f"Events file: {len(ev)} dates, source = "
                     f"{', '.join(sorted(ev['source'].unique()))} (official calendar pages could not "
                     "be fetched from this environment; dates were written from memory and spot-checked "
                     "by web search for 2025-2026).\n")
    if name.startswith("S6"):
        lines.append("\nTokyo trades end by 13:00 Tokyo time and ECB trades start at 14:20 Berlin "
                     "time, so 'both' never holds two positions in the same pair at once.\n")

    lines.append("\n## Random-entry baseline (out-of-sample, costs x1, 100 runs)\n\n"
                 f"Same entry times, holding times and sizes, random direction. Percentiles: "
                 f"5th {np.percentile(rnd, 5):,.0f}, median {np.median(rnd):,.0f}, "
                 f"95th {p95:,.0f} USD. Strategy: {oos_net:,.0f} USD.\n")
    lines.append("\n## Walk-forward (2-year train, 6-month test, costs x1)\n\n" + md_table(wf))
    if len(wf):
        lines.append(f"\nWalk-forward total: {wf['net'].sum():,.0f} USD over {wf['trades'].sum()} "
                     f"trades; {(wf['net'] > 0).sum()} of {len(wf)} test windows positive.\n")

    # extra check on the short-history markets with the chosen parameters
    ex_rows = []
    variants = [("single pairs", {})]
    if name.startswith("S6"):
        variants.append(("4-pair USD basket", {"basket": True}))
    for label, extra_kw in variants:
        params = {**chosen.params, **extra_kw}
        syms = extra if not extra_kw else ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]
        group = "extra" if not extra_kw else "basket"
        res = run_grid(pool, name, group, [params])[0].trades
        for sym in sorted({t.symbol for t in res}) if not extra_kw else ["basket"]:
            sub = [t for t in res if extra_kw or t.symbol == sym]
            p = price_trades(sub, costs, 1.0)
            s = stats(p)
            ex_rows.append({"market": sym if not extra_kw else label, "from": str(min(t.entry_time for t in sub).date()) if sub else "",
                            "trades": s["trades"], "exp_R": s["expectancy_R"], "pf": s["profit_factor"],
                            "net_pct": s["net_pct"]})
    lines.append("\n## Extra check: short-history markets (~1.5 years, chosen parameters, costs x1, low confidence)\n\n"
                 + md_table(pd.DataFrame(ex_rows)))

    lines.append("\n## All combinations\n\nChoice uses the in-sample columns only; out-of-sample "
                 "columns are shown so nothing is hidden, not for picking.\n\n" + md_table(allc))
    lines.append("\n## Notes\n\n" + "\n".join(f"- {n}" for n in NOTES) + "\n")
    lines.append("\nFiles: `trades.csv`, `monthly_returns.csv`, `all_combinations.csv`, "
                 "`equity_curve.png`, `drawdown.png`.\n")
    (out / "summary.md").write_text("\n".join(lines))
    rec.update(verdict=verdict, oos_trades=len(oos_tr), oos_exp=oos_exp,
               sharpe=table["OOS x1"]["sharpe"], dd=table["OOS x1"]["max_dd_pct"], beats=beats,
               rank=rank, params=chosen.params, oos_exp2=table["OOS x2"]["expectancy_R"],
               is_exp=table["IS x1"]["expectancy_R"], trades=trades, cut=cut)
    return rec


# ----------------------------------------------------------------------- S7 vs S8 + comparison
def round_number_table(recs: Dict[str, dict], costs, bars) -> str:
    out = []
    a, b = recs.get("S7_round_fade"), recs.get("S8_round_break")
    if a and b and a.get("trades") and b.get("trades"):
        pa, pb = price_trades(a["trades"], costs, 1.0), price_trades(b["trades"], costs, 1.0)
        for p in (pa, pb):
            p["date"] = pd.to_datetime(p["entry_time"]).dt.date
        ka = pa.groupby(["symbol", "date"])["R"].sum()
        kb = pb.groupby(["symbol", "date"])["R"].sum()
        both = ka.index.intersection(kb.index)
        out.append(f"Dates where both chosen versions traded the same pair: {len(both)}. "
                   f"Fade (S7) total {ka.loc[both].sum():.1f} R, mean {ka.loc[both].mean():.3f} R/day; "
                   f"break (S8) total {kb.loc[both].sum():.1f} R, mean {kb.loc[both].mean():.3f} R/day "
                   "(costs x1).\n")
    lo = S.level_outcomes({s: None for s in bars}, bars)
    if len(lo):
        t = lo.groupby(["symbol", "outcome"]).size().unstack(fill_value=0).reset_index()
        out.append("\nModel-free check - first touch of a round level each day (07:00-17:00 London): "
                   "did price go 20 pips THROUGH (break) or 20 pips BACK (reverse) first, within 2 hours?\n\n"
                   + md_table(t))
    return "\n".join(out)


def comparison(recs: Dict[str, dict], costs, rn_text: str) -> None:
    rows = []
    for name in SETUPS:
        r = recs.get(name)
        if not r:
            continue
        rows.append({"Strategy": name, "OOS trades": r.get("oos_trades", 0),
                     "OOS expectancy (R) @ x1": r.get("oos_exp", np.nan),
                     "OOS expectancy (R) @ x2": r.get("oos_exp2", np.nan),
                     "IS expectancy (R) @ x1": r.get("is_exp", np.nan),
                     "Sharpe @ x1": r.get("sharpe", np.nan), "Max DD %": r.get("dd", np.nan),
                     "Beats random 95%?": "yes" if r.get("beats") else "no",
                     "Verdict": r["verdict"]})
    for k, why in NOT_TESTABLE.items():
        rows.append({"Strategy": k, "OOS trades": "-", "OOS expectancy (R) @ x1": "-",
                     "OOS expectancy (R) @ x2": "-", "IS expectancy (R) @ x1": "-",
                     "Sharpe @ x1": "-", "Max DD %": "-", "Beats random 95%?": "-",
                     "Verdict": "NOT TESTABLE"})
    lines = ["# Comparison - BACKTEST_SPEC.md setups\n",
             "Out-of-sample = last 30% of dates, touched once. Each setup's parameters were chosen "
             "on the first 70% only. PASS = OOS expectancy > 0 at costs x1 AND beats the 95th "
             "percentile of 100 random-entry runs.\n\n", md_table(pd.DataFrame(rows)),
             "\n'Beats random' alone is not enough: random entries pay the same costs, so a "
             "losing setup can still beat a worse-losing random baseline. Max DD is measured on "
             "non-compounded equity (100,000 + cumulative P&L), so it can exceed -100% when a "
             "setup loses more than the starting equity over the test.\n",
             "\n## Not testable with our data\n\n" + "\n".join(f"- **{k}**: {v}" for k, v in NOT_TESTABLE.items()) + "\n"]
    passed = [n for n, r in recs.items() if r.get("verdict") == "PASS"]
    if len(passed) >= 2:
        series = {}
        for n in passed:
            r = recs[n]
            p = price_trades([t for t in r["trades"] if t.entry_time >= r["cut"]], costs, 1.0)
            series[n] = p.groupby(pd.to_datetime(p["exit_time"]).dt.normalize())["net"].sum()
        corr = pd.DataFrame(series).fillna(0.0).corr().round(2).reset_index()
        lines.append("\n## Correlation of daily OOS returns between PASSing setups\n\n" + md_table(corr))
    else:
        lines.append(f"\n## Correlation of daily returns\n\n{len(passed)} setup(s) passed, so there is "
                     "nothing to combine.\n")
    if rn_text:
        lines.append("\n## Round numbers: reverse or break? (S7 vs S8)\n\n" + rn_text)
    lines.append("\n## Data notes\n\n" + "\n".join(f"- {n}" for n in NOTES) + "\n")
    (REPORTS / "COMPARISON.md").write_text("\n".join(lines))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", nargs="*", help="setup name prefixes, e.g. S5 S9_sweep_H1")
    ap.add_argument("--workers", type=int, default=max(1, mp.cpu_count()))
    a = ap.parse_args(argv)
    names = [n for n in SETUPS if not a.only or any(n.startswith(p) for p in a.only)]
    kinds = {SETUPS[n]["kind"] for n in names}
    need = set()
    if "index" in kinds:
        need |= set(INDEX_MAIN + INDEX_EXTRA)
    if kinds - {"index"}:
        need |= set(FX_MAIN + FX_EXTRA)
    data = {s: load(s) for s in sorted(need)}
    costs = {s: costs_for(s, df) for s, df in data.items()}
    for k in kinds:
        main_, extra_ = (INDEX_MAIN, INDEX_EXTRA) if k == "index" else (FX_MAIN, FX_EXTRA)
        CTX[f"{k}:main"] = context(k, main_, data, costs)
        CTX[f"{k}:extra"] = context(k, extra_, data, costs)
        if k == "fx":
            CTX[f"{k}:basket"] = context(k, FX_MAIN + FX_EXTRA, data, costs)
        print(f"prepared {k}", flush=True)
    REPORTS.mkdir(exist_ok=True)
    recs = {}
    with mp.get_context("fork").Pool(a.workers) as pool:
        for n in names:
            recs[n] = evaluate(pool, n, data, costs)
            r = recs[n]
            print(f"{n:24s} {r['verdict']:8s} OOS trades {r.get('oos_trades', 0):5} "
                  f"exp@x1 {r.get('oos_exp', float('nan'))}", flush=True)
    rn = ""
    if "fx_bars" in kinds:
        rn = round_number_table(recs, costs, CTX["fx_bars:main"]["bars"])
        s8 = REPORTS / "S8_round_break" / "summary.md"
        if s8.exists() and rn:
            s8.write_text(s8.read_text() + "\n## S7 vs S8 on identical dates\n\n" + rn)
    if not a.only:
        comparison(recs, costs, rn)
    return 0


if __name__ == "__main__":
    sys.exit(main())
