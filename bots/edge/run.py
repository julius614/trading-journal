"""Run the pre-declared edge search (bots/edge/protocol.md) and write reports/edge/.

    python -m bots.edge.run
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Dict, List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from bots.spec10 import strategies as S
from bots.spec10.engine import (EQUITY, CostModel, SweepResult, choose_best, fx_costs,
                                price_trades, random_entry_totals, stats, walk_forward)
from bots.spec10.run import load as load_m5, md_table
from bots.trend.research.trend import load_markets

from . import calendar as C

ROOT = Path(__file__).resolve().parents[2]
D1_DIR = ROOT / "data" / "trend"
OUT = ROOT / "reports" / "edge"
EVENTS = ROOT / "data" / "events.csv"

C1_TOM = ["US500", "US30", "USTECH100M"]
C1_FOMC = ["US500", "USTECH100M"]
C1_P = {"discovery": ("2012-08-01", "2019-01-01"), "validate": ("2019-01-01", "2023-01-01"),
        "hold-out": ("2023-01-01", "2026-12-31")}
C2_MARKETS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "NZDUSD", "USDCAD", "USDCHF", "XAUUSD",
              "US500", "USTECH100M", "US30"]
C2_P = {"discovery": ("2004-01-01", "2017-01-01"), "validate": ("2017-01-01", "2022-01-01"),
        "hold-out": ("2022-01-01", "2026-12-31")}
C2_GRID = S.grid(N=[20, 50], over=[0.25, 0.5], target_R=[2, 3], stop_buffer=[0])
H4_MARKETS = ["EURUSD", "GBPUSD", "XAUUSD", "US500", "USTECH100M"]
STAT_ROWS = ["trades", "win_rate", "expectancy_R", "profit_factor", "net", "net_pct", "cagr",
             "sharpe", "max_dd_pct", "longest_losing_streak", "top5_share"]


# ----------------------------------------------------------------------- costs
def is_fx(sym: str) -> bool:
    return len(sym) == 6 and sym[:3] in {"EUR", "GBP", "USD", "AUD", "NZD"}


def d1_costs(sym: str, df: pd.DataFrame) -> CostModel:
    if is_fx(sym):
        return replace(fx_costs(sym), financing_per_year=0.02)
    point = json.loads((D1_DIR / f"{sym}_spec.json").read_text())["point"]
    sp = df["spread_price"]
    med = float(sp[sp > 0].median())
    return CostModel(spread=med, slippage=0.5 * med, leverage_cap=10.0 if sym.startswith("XAU") else 4.0,
                     tick=float(point), financing_per_year=0.05)


def ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz="UTC")


def part(trades, a, b):
    return [t for t in trades if ts(a) <= t.entry_time < ts(b)]


def period_table(trades, costs, periods) -> pd.DataFrame:
    cols = {}
    for name, (a, b) in periods.items():
        days = pd.bdate_range(ts(a), min(ts(b), pd.Timestamp.now(tz="UTC")), tz="UTC")
        for m in (0.0, 1.0, 2.0):
            cols[f"{name} x{m:g}"] = stats(price_trades(part(trades, a, b), costs, m), days)
    return pd.DataFrame(cols).loc[STAT_ROWS].reset_index().rename(columns={"index": "metric"})


def exp_R(trades, costs, a, b, m=1.0) -> float:
    p = price_trades(part(trades, a, b), costs, m)
    return float(p["R"].mean()) if len(p) else float("nan")


def plot(trades, costs, out: Path, title: str, cuts) -> None:
    p = price_trades(trades, costs, 1.0)
    daily = p.groupby(pd.to_datetime(p["exit_time"]).dt.normalize())["net"].sum().sort_index()
    eq = EQUITY + daily.cumsum()
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(eq.index, eq.values, lw=1.2, color="#2a6f97")
    for c in cuts:
        ax.axvline(ts(c), color="#555", ls="--", lw=1)
    ax.set_title(f"{title} - equity, costs x1 (dashed: validate / hold-out start)", fontsize=10)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out / "equity_curve.png", dpi=110)
    plt.close(fig)


def pf(ok: bool) -> str:
    return "yes" if ok else "NO"


# ----------------------------------------------------------------------- C1 calendar
def run_c1(d1, costs, fomc_dates) -> dict:
    out = OUT / "C1_calendar"
    out.mkdir(parents=True, exist_ok=True)
    tom_m = {s: d1[s] for s in C1_TOM}
    fomc_m = {s: d1[s] for s in C1_FOMC}

    def sleeve(e=2, x=3):
        return sorted(C.tom_trades(tom_m, e, x) + C.fomc_trades(fomc_m, fomc_dates),
                      key=lambda t: t.entry_time)

    trades = sleeve()
    d, v, h = C1_P["discovery"], C1_P["validate"], C1_P["hold-out"]
    join = exp_R(trades, costs, *d) > 0
    keep = exp_R(trades, costs, *v) > 0
    hold = part(trades, *h)
    e1, e2 = exp_R(trades, costs, *h, 1.0), exp_R(trades, costs, *h, 2.0)
    priced = lambda tr: price_trades(tr, costs, 1.0)
    rnd = C.random_dates_totals(hold, {**tom_m, **fomc_m}, priced, ts(h[0]), ts(h[1]))
    net = float(priced(hold)["net"].sum())
    p99 = float(np.percentile(rnd, 99))
    allp = priced(part(trades, v[0], h[1]))
    years = allp.groupby(pd.to_datetime(allp["exit_time"]).dt.year)["net"].sum()
    shifts = {(3, 3): None, (1, 3): None, (2, 2): None, (2, 4): None}
    for k in shifts:
        shifts[k] = exp_R(sleeve(*k), costs, v[0], h[1])
    gates = {"JOIN discovery exp>0 @x1": join, "KEEP validate exp>0 @x1": keep,
             "(a) hold-out exp>0 @x1 and >=0 @x2": e1 > 0 and e2 >= 0,
             "(b) beats random-dates 99th pct": net > p99,
             "(c) >= 100 hold-out trades": len(hold) >= 100,
             "(d) > half of years 2019+ positive": (years > 0).sum() > len(years) / 2,
             "(e) plateau: >= 3 of 4 TOM shifts positive": sum(x > 0 for x in shifts.values()) >= 3}
    verdict = "PASS" if all(gates.values()) else "FAIL"

    price_trades(trades, costs, 1.0).assign(
        period=lambda x: np.select([x.entry_time < ts(v[0]), x.entry_time < ts(h[0])],
                                   ["discovery", "validate"], "hold-out")).to_csv(out / "trades.csv", index=False)
    plot(trades, costs, out, "C1 calendar sleeve", [v[0], h[0]])

    parts = []
    for tag in ("TOM", "FOMC"):
        for sym in sorted({t.symbol for t in trades if t.tag == tag}):
            sub = [t for t in trades if t.tag == tag and t.symbol == sym]
            row = {"part": tag, "market": sym}
            for name, (a, b) in C1_P.items():
                p = price_trades(part(sub, a, b), costs, 1.0)
                row[f"{name} trades"] = len(p)
                row[f"{name} exp_R"] = round(float(p["R"].mean()), 4) if len(p) else float("nan")
            parts.append(row)
    bh = []
    for sym in C1_TOM:
        px = d1[sym]["close"]
        px = px[px.index >= ts(h[0])]
        bh.append({"market": sym, "buy_and_hold_holdout_pct": round((px.iloc[-1] / px.iloc[0] - 1) * 100, 1)})

    lines = ["# C1 - Calendar sleeve: turn-of-the-month + pre-FOMC drift (long indices)\n",
             f"## Verdict: **{verdict}**\n",
             f"Hold-out ({h[0]} on): {len(hold)} trades, expectancy {e1:.4f} R at x1 and "
             f"{e2:.4f} R at x2; net {net:,.0f} USD vs random-dates 99th percentile {p99:,.0f} USD "
             f"(median {np.median(rnd):,.0f}).\n",
             "\n## Gates (pre-declared)\n\n" + md_table(pd.DataFrame(
                 [{"gate": k, "passed": pf(x)} for k, x in gates.items()])),
             "\n## Results by period, costs x0 / x1 / x2\n\n" + md_table(period_table(trades, costs, C1_P)),
             "\n## By part and market (costs x1)\n\n" + md_table(pd.DataFrame(parts)),
             "\n## Calendar years 2019+ (net USD, costs x1)\n\n" + md_table(
                 pd.DataFrame({"year": years.index.astype(str), "net": years.round(0).values})),
             "\n## Plateau: TOM shifted one day (validate + hold-out expectancy, x1)\n\n" + md_table(
                 pd.DataFrame([{"entry (from month end)": k[0], "exit (trading day)": k[1],
                                "exp_R": round(x, 4)} for k, x in shifts.items()])),
             "\n## Buy-and-hold over the hold-out (1x, for scale)\n\n" + md_table(pd.DataFrame(bh)),
             f"\nRandom-dates null: being long on random days of the same hold-out earned a median "
             f"{np.median(rnd):,.0f} USD, about the same as the sleeve - so in this sample the "
             "calendar days added little beyond the market's general rise.\n",
             "\nThe sleeve is in the market about 25% of days (TOM about 5 of 21 days, plus FOMC "
             "days), so it should be compared with buy-and-hold per day held, not in total.\n"]
    return {"name": "C1_calendar", "verdict": verdict, "lines": lines, "trades": trades,
            "hold_trades": len(hold), "e1": e1, "e2": e2, "net": net, "p99": p99}


def run_c1_m5_info(fomc_dates) -> str:
    try:
        from bots.spec10.run import costs_for
        m5 = {s: load_m5(s) for s in C1_FOMC}
        costs = {s: replace(costs_for(s, df), financing_per_year=0.05, use_bar_spread=False)
                 for s, df in m5.items()}
        tr = C.fomc_m5_trades(m5, [d for d in fomc_dates if d >= pd.Timestamp("2019-01-01")])
        rows = []
        for m in (0.0, 1.0, 2.0):
            s = stats(price_trades(tr, costs, m))
            rows.append({"costs": f"x{m:g}", "trades": s["trades"], "exp_R": s["expectancy_R"],
                         "win_rate": s["win_rate"], "net_pct": s["net_pct"]})
        return ("\n## Information only: pre-FOMC drift on M5, 14:00 ET day before -> 13:55 ET "
                "(2019-2026, US500 + USTECH100M, 0.5x each)\n\n" + md_table(pd.DataFrame(rows)))
    except Exception as e:  # information only - never blocks the verdict
        return f"\n(M5 pre-FOMC information run skipped: {e})\n"


# ----------------------------------------------------------------------- C2 sweep on D1
def sweep(bars, spreads, markets, params) -> List:
    return S.s9(markets, bars=bars, spreads=spreads, **params)


def run_c2(d1, costs) -> dict:
    out = OUT / "C2_sweep_D1"
    out.mkdir(parents=True, exist_ok=True)
    mk = {s: d1[s] for s in C2_MARKETS}
    bars = {s: S.make_bars(df, pd.Timedelta(days=1), gap_hours=24 * 5) for s, df in mk.items()}
    spreads = {s: costs[s].spread for s in mk}
    results = [SweepResult(p, sweep(bars, spreads, mk, p)) for p in C2_GRID]
    d, v, h = C2_P["discovery"], C2_P["validate"], C2_P["hold-out"]
    best, table = choose_best(results, costs, ts(d[1]))
    lines = ["# C2 - Swing liquidity-sweep reversal on daily bars (data-inspired)\n"]
    if best is None:
        lines.append("\n## Verdict: **FAIL** (no combination with >= 30 discovery trades)\n")
        return {"name": "C2_sweep_D1", "verdict": "FAIL", "lines": lines}
    ch = results[best]
    trades = ch.trades
    join = table.loc[best, "is_exp_R"] > 0
    keep = exp_R(trades, costs, *v) > 0
    hold = part(trades, *h)
    e1, e2 = exp_R(trades, costs, *h, 1.0), exp_R(trades, costs, *h, 2.0)
    net = float(price_trades(hold, costs, 1.0)["net"].sum()) if hold else 0.0
    rnd = random_entry_totals(hold, costs, runs=100)
    p99 = float(np.percentile(rnd, 99))
    wf = walk_forward(results, costs, ts(d[0]), ts("2026-10-02"), train_years=4.0,
                      test_months=12, min_trades=20)
    N, over = ch.params["N"], ch.params["over"]
    neigh = [dict(ch.params, N=int(round(N * 0.75))), dict(ch.params, N=int(round(N * 1.25))),
             dict(ch.params, over=over * 0.75), dict(ch.params, over=over * 1.25)]
    plateau = [(p, exp_R(sweep(bars, spreads, mk, p), costs, *v)) for p in neigh]
    gates = {"JOIN discovery exp>0 @x1": bool(join), "KEEP validate exp>0 @x1": keep,
             "(a) hold-out exp>0 @x1 and >=0 @x2": e1 > 0 and e2 >= 0,
             "(b) beats random-direction 99th pct": net > p99,
             "(c) >= 100 hold-out trades": len(hold) >= 100,
             "(d) > half of walk-forward windows positive": len(wf) > 0 and (wf["net"] > 0).sum() > len(wf) / 2,
             "(e) plateau: >= 3 of 4 neighbours positive (validate)": sum(x > 0 for _, x in plateau) >= 3}
    verdict = "PASS" if all(gates.values()) else "FAIL"
    p = price_trades(trades, costs, 1.0)
    p.to_csv(out / "trades.csv", index=False)
    plot(trades, costs, out, "C2 sweep D1", [v[0], h[0]])
    hp = price_trades(hold, costs, 1.0)
    by_mkt = hp.groupby("symbol").agg(trades=("R", "size"), exp_R=("R", "mean"), net=("net", "sum")).reset_index()
    lines += [f"\n## Verdict: **{verdict}**\n",
              f"Chosen on discovery only: `{ch.params}`. Hold-out ({h[0]} on): {len(hold)} trades, "
              f"expectancy {e1:.4f} R at x1, {e2:.4f} R at x2; net {net:,.0f} USD vs random 99th "
              f"percentile {p99:,.0f} USD.\n",
              "\n## Gates (pre-declared)\n\n" + md_table(pd.DataFrame(
                  [{"gate": k, "passed": pf(x)} for k, x in gates.items()])),
              "\n## Chosen combination by period, costs x0 / x1 / x2\n\n" + md_table(period_table(trades, costs, C2_P)),
              "\n## Hold-out by market (x1)\n\n" + md_table(by_mkt),
              "\n## Walk-forward (4-year train, 1-year test, x1)\n\n" + md_table(wf),
              "\n## Plateau (validate expectancy, x1)\n\n" + md_table(pd.DataFrame(
                  [{"params": str(p_), "exp_R": round(x, 4)} for p_, x in plateau])),
              "\n## All combinations (discovery columns used for the choice)\n\n" + md_table(table)]
    return {"name": "C2_sweep_D1", "verdict": verdict, "lines": lines, "trades": trades,
            "hold_trades": len(hold), "e1": e1, "e2": e2, "net": net, "p99": p99, "params": ch.params}


def run_c2_h4_info(params) -> str:
    try:
        from bots.spec10.run import costs_for
        rows = []
        m5 = {s: load_m5(s) for s in H4_MARKETS}
        costs = {s: replace(costs_for(s, df), financing_per_year=0.02 if is_fx(s) else 0.05,
                            use_bar_spread=False) for s, df in m5.items()}
        h4 = {s: S.resample(df, "4h") for s, df in m5.items()}
        bars = {s: S.make_bars(df, pd.Timedelta(hours=4), gap_hours=12) for s, df in h4.items()}
        tr = S.s9(h4, bars=bars, spreads={s: c.spread for s, c in costs.items()}, **params)
        for m in (0.0, 1.0, 2.0):
            s = stats(price_trades(tr, costs, m))
            rows.append({"costs": f"x{m:g}", "trades": s["trades"], "exp_R": s["expectancy_R"],
                         "net_pct": s["net_pct"]})
        return ("\n## Information only: same rule and parameters on H4 bars (2019-2026)\n\n"
                + md_table(pd.DataFrame(rows)))
    except Exception as e:
        return f"\n(H4 information run skipped: {e})\n"


# ----------------------------------------------------------------------- portfolio
def portfolio_text(passed: List[dict], costs) -> str:
    """Combine passing sleeves with the AUD/NZD pairs bot and estimate prop-firm odds."""
    try:
        from bots.statarb_3leg.portfolio import _run_pair, daily_pnl, odds_table, recommend_scale
        paths = {s: str(ROOT / "data" / "amd_fx" / f"{s}_H1.csv") for s in ("AUDUSD", "NZDUSD")}
        _, pairs = _run_pair((("AUDUSD", "NZDUSD"), paths, 7.0))
        start = "2023-01-01"
        end = pd.Timestamp("2026-10-01", tz="UTC")
        cols = {"AUD/NZD pairs": daily_pnl({"p": pairs}, start, end)["p"]}
        for r in passed:
            p = price_trades([t for t in r["trades"] if t.entry_time >= ts(start)], costs, 1.0)
            s = p.groupby(pd.to_datetime(p["exit_time"]).dt.normalize())["net"].sum() / EQUITY
            cols[r["name"]] = s.reindex(cols["AUD/NZD pairs"].index, fill_value=0.0)
        df = pd.DataFrame(cols).fillna(0.0)
        port = df.sum(axis=1)
        odds = odds_table(port.to_numpy())
        sc = recommend_scale(odds)
        return ("\n## Portfolio with the AUD/NZD pairs bot (2023+, daily P&L, 1x each)\n\n"
                + md_table(df.corr().round(2).reset_index()) +
                f"\nReturn {port.sum() * 100:.1f}% over {len(port) / 252:.1f} years at 1x.\n\n"
                "Prop-firm odds (+10% before -10% / -5% day, block bootstrap):\n\n"
                + md_table(odds.round(3)) + f"\nLargest safe scale: {sc}\n")
    except Exception as e:
        return f"\n(Portfolio step skipped: {e})\n"


def main(argv=None) -> int:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args(argv)
    d1, _ = load_markets(str(D1_DIR))
    d1.pop("UK100", None)                       # amendment 1: sparse D1 data
    costs = {s: d1_costs(s, df) for s, df in d1.items()}
    ev = pd.read_csv(EVENTS)
    fomc = sorted(pd.to_datetime(ev.loc[ev["event"] == "FOMC", "date"]))
    OUT.mkdir(parents=True, exist_ok=True)

    c1 = run_c1(d1, costs, fomc)
    c1["lines"].append(run_c1_m5_info(fomc))
    c2 = run_c2(d1, costs)
    if c2.get("params"):
        c2["lines"].append(run_c2_h4_info(c2["params"]))
    note = ("\n## Notes\n\n- Rules, periods and gates: `bots/edge/protocol.md` (committed before "
            "this run).\n- Costs: spread + slippage + swap (indices/gold 5%/yr, FX 2%/yr, "
            "Wednesday x3).\n- FOMC dates: `data/events.csv`, written from memory (official pages "
            "unreachable), so one-day errors are possible.\n")
    for r in (c1, c2):
        (OUT / r["name"]).mkdir(parents=True, exist_ok=True)
        (OUT / r["name"] / "summary.md").write_text("\n".join(r["lines"]) + note)
        print(f"{r['name']:14s} {r['verdict']}  hold-out trades {r.get('hold_trades', 0)}  "
              f"exp@x1 {r.get('e1', float('nan')):.4f}  exp@x2 {r.get('e2', float('nan')):.4f}  "
              f"net {r.get('net', 0):,.0f} vs p99 {r.get('p99', float('nan')):,.0f}", flush=True)

    passed = [r for r in (c1, c2) if r["verdict"] == "PASS"]
    summary = ["# Edge search - summary\n",
               "Pre-declared protocol: `bots/edge/protocol.md`. Hold-out touched once.\n\n",
               md_table(pd.DataFrame([{"candidate": r["name"], "hold-out trades": r.get("hold_trades", 0),
                                       "exp R @x1": round(r.get("e1", float("nan")), 4),
                                       "exp R @x2": round(r.get("e2", float("nan")), 4),
                                       "net USD": round(r.get("net", 0)), "random p99": round(r.get("p99", float("nan"))),
                                       "verdict": r["verdict"]} for r in (c1, c2)]))]
    summary.append(portfolio_text(passed, costs) if passed else
                   "\nNothing passed, so there is no portfolio step.\n")
    (OUT / "SUMMARY.md").write_text("\n".join(summary) + note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
