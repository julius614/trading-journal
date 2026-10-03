"""Pre-declared multi-pair portfolio test and prop-challenge pass-probability simulator
(written and committed BEFORE it was run on the data; see git history).

    python -m bots.statarb_3leg.portfolio --data-dir data/amd_fx

Why: one pair (AUD/NZD) makes ~1%/yr at 1x notional - too slow for a 10% challenge
target. More independent pairs give more trades without more risk per trade.

Protocol
--------
Candidates: every pair of EURUSD, GBPUSD, AUDUSD, NZDUSD (6 pairs). The y leg is the
earlier symbol in that order (EUR/GBP, EUR/AUD, EUR/NZD, GBP/AUD, GBP/NZD, AUD/NZD).
All run with the bot's defaults (entry Z 2.0, exit 0.1, stop Z_entry+-2, 48-bar time
stop, gate off), $100,000 at 1x notional, the broker's per-bar spreads, $7/lot commission.

Trades are split by entry time as in tune.py:
    tune 2018-09..2022-12   validate 2023-01..2024-12   hold-out 2025-01..end
A pair JOINS the portfolio if, on the tune period, it has >= 40 trades and PF >= 1.1.
It is KEPT only if its validate-period PF is > 1.0. The hold-out is reported once.

Pass probability: daily closed P&L (fraction of the $100k start) of the kept pairs over
2023-01..end only (the period not used to choose them) is block-bootstrapped (5-day
blocks, 10,000 paths, up to 3 years) at notional scales 1x..10x. A path PASSES when
cumulative P&L reaches +10% before it reaches -10% or any single day loses >= 5%
(FTMO 2-Step phase 1). The recommended scale is the largest with P(daily breach) < 2%
and P(fail) < 10%. Caveats: closed P&L only (floating drawdown inside a day is not
seen; the bot's 2% Prop Shield would cut such days short), and the 2023+ history is short.
"""
from __future__ import annotations

import argparse
import asyncio
import itertools
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .backtest import run_replay, with_overrides
from .config import load_config
from .data_fetcher import load_pair
from .tune import PERIODS, period_stats, split_by_period

SYMBOLS = ("EURUSD", "GBPUSD", "AUDUSD", "NZDUSD")
CANDIDATES: List[Tuple[str, str]] = list(itertools.combinations(SYMBOLS, 2))
BALANCE = 100_000.0
MIN_TUNE_TRADES = 40
MIN_TUNE_PF = 1.1
MIN_VALIDATE_PF = 1.0
SIM_START = PERIODS["validate"][0]
SCALES = tuple(np.arange(1.0, 10.01, 0.5))
TARGET, MAX_LOSS, DAILY_LIMIT = 0.10, 0.10, 0.05
MAX_P_DAILY, MAX_P_FAIL = 0.02, 0.10


def _run_pair(args) -> Tuple[Tuple[str, str], pd.DataFrame]:
    pair, paths, commission = args
    cfg = with_overrides(load_config(), pair, no_coint_gate=True)
    data = load_pair(paths, pair)
    res = asyncio.run(run_replay(cfg, {}, BALANCE, None, commission, None, frames=data,
                                 verbose=False))
    rows = [{"opened_at": b.opened_at, "closed_at": b.closed_at, "pnl": b.pnl,
             "exit": b.exit_reason} for b in res["baskets"]]
    return pair, pd.DataFrame(rows, columns=["opened_at", "closed_at", "pnl", "exit"])


def pair_name(pair: Sequence[str]) -> str:
    return f"{pair[0][:3]}/{pair[1][:3]}"


def select_pairs(table: pd.DataFrame) -> Tuple[List[str], List[str]]:
    """(joined on tune, kept after validate) by the pre-declared rule."""
    joined = table[(table["tune_trades"] >= MIN_TUNE_TRADES)
                   & (table["tune_pf"] >= MIN_TUNE_PF)]
    kept = joined[joined["validate_pf"] > MIN_VALIDATE_PF]
    return list(joined["pair"]), list(kept["pair"])


def daily_pnl(trades: Dict[str, pd.DataFrame], start: str, end: pd.Timestamp,
              balance: float = BALANCE) -> pd.DataFrame:
    """Closed P&L per weekday (fraction of balance), one column per pair, zeros on quiet days."""
    days = pd.bdate_range(pd.Timestamp(start, tz="UTC"), end.normalize(), tz="UTC")
    out = pd.DataFrame(0.0, index=days, columns=list(trades))
    for name, t in trades.items():
        if t.empty:
            continue
        closed = pd.to_datetime(t["closed_at"], utc=True).dt.normalize()
        # weekend closes (none expected) roll to the next weekday
        closed = closed.map(lambda d: d if d.weekday() < 5 else d + pd.offsets.BDay(1))
        s = (t["pnl"] / balance).groupby(closed).sum()
        s = s[(s.index >= days[0]) & (s.index <= days[-1])]
        out[name] = out[name].add(s, fill_value=0.0)
    return out


def bootstrap_paths(daily: np.ndarray, n_paths: int, horizon: int, block: int,
                    rng: np.random.Generator) -> np.ndarray:
    """n_paths x horizon matrix of daily returns built from random contiguous blocks."""
    daily = np.asarray(daily, dtype=float)
    n = len(daily)
    if n < block:
        raise ValueError("history shorter than one block")
    n_blocks = -(-horizon // block)
    starts = rng.integers(0, n - block + 1, size=(n_paths, n_blocks))
    idx = (starts[..., None] + np.arange(block)).reshape(n_paths, -1)[:, :horizon]
    return daily[idx]


def _first_hit(mask: np.ndarray) -> np.ndarray:
    """Index of the first True per row, or the row length if none."""
    hit = mask.any(axis=1)
    return np.where(hit, mask.argmax(axis=1), mask.shape[1])


def challenge_odds(paths: np.ndarray, scale: float, target: float = TARGET,
                   max_loss: float = MAX_LOSS, daily_limit: float = DAILY_LIMIT,
                   days_per_year: int = 252) -> Dict[str, float]:
    """Pass / fail odds of a no-time-limit challenge at a notional scale (P&L scales
    linearly with notional; limits are on the starting balance, so no compounding)."""
    r = paths * scale
    cum = np.cumsum(r, axis=1)
    t_pass = _first_hit(cum >= target - 1e-12)
    t_total = _first_hit(cum <= -max_loss + 1e-12)
    t_daily = _first_hit(r <= -daily_limit + 1e-12)
    t_fail = np.minimum(t_total, t_daily)
    horizon = paths.shape[1]
    passed = t_pass < t_fail
    failed = t_fail < t_pass
    return {
        "scale": float(scale),
        "p_pass": float(passed.mean()),
        "p_fail": float(failed.mean()),
        "p_daily_breach": float(((t_daily < horizon) & (t_daily <= t_pass)).mean()),
        "p_pass_12m": float((passed & (t_pass + 1 <= days_per_year)).mean()),
        "median_months_to_pass": (float(np.median(t_pass[passed] + 1)) / 21.0
                                  if passed.any() else float("nan")),
    }


def recommend_scale(odds: pd.DataFrame) -> Optional[float]:
    ok = odds[(odds["p_daily_breach"] < MAX_P_DAILY) & (odds["p_fail"] < MAX_P_FAIL)]
    return float(ok["scale"].max()) if len(ok) else None


def odds_table(daily: np.ndarray, n_paths: int = 10_000, years: int = 3, block: int = 5,
               seed: int = 11, scales: Sequence[float] = SCALES) -> pd.DataFrame:
    paths = bootstrap_paths(daily, n_paths, years * 252, block, np.random.default_rng(seed))
    return pd.DataFrame([challenge_odds(paths, s) for s in scales])


def pair_table(results: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for name, trades in results.items():
        row = {"pair": name}
        for per, part in split_by_period(trades).items():
            for k, v in period_stats(part).items():
                row[f"{per}_{k}"] = v
        rows.append(row)
    return pd.DataFrame(rows)


def run(data_dir: str, commission: float, workers: int = 6) -> Dict[str, pd.DataFrame]:
    jobs = []
    for pair in CANDIDATES:
        paths = {s: str(Path(data_dir) / f"{s}_H1.csv") for s in pair}
        jobs.append((pair, paths, commission))
    with ProcessPoolExecutor(workers) as pool:
        return {pair_name(p): t for p, t in pool.map(_run_pair, jobs)}


def main(argv: Optional[List[str]] = None) -> None:
    p = argparse.ArgumentParser(description="Pre-declared multi-pair portfolio test")
    p.add_argument("--data-dir", default="data/amd_fx")
    p.add_argument("--commission", type=float, default=7.0)
    p.add_argument("--out", help="write all baskets to this CSV")
    a = p.parse_args(argv)

    results = run(a.data_dir, a.commission)
    table = pair_table(results)
    joined, kept = select_pairs(table)
    cols = ["pair"] + [f"{per}_{k}" for per in PERIODS for k in ("trades", "pnl", "pf", "win")]
    with pd.option_context("display.width", 250, "display.max_columns", None):
        print("\n== Candidate pairs ($100k, 1x notional, defaults) ==")
        print(table[cols].to_string(index=False))
    print(f"\nJoined on tune (>= {MIN_TUNE_TRADES} trades, PF >= {MIN_TUNE_PF}): {joined}")
    print(f"Kept after validate (PF > {MIN_VALIDATE_PF}): {kept}")
    if a.out:
        pd.concat({k: v for k, v in results.items()}, names=["pair"]).to_csv(a.out)
    if not kept:
        print("No pair survived - no portfolio.")
        return

    end = max(pd.to_datetime(t["closed_at"], utc=True).max() for t in results.values()
              if not t.empty)
    daily = daily_pnl({k: results[k] for k in kept}, SIM_START, end)
    port = daily.sum(axis=1)
    monthly = daily.resample("ME").sum()
    years = len(port) / 252
    print(f"\n== Portfolio of {kept}, {SIM_START[:7]} .. {end:%Y-%m} (not used for selection) ==")
    print(f"  return {port.sum():+.2%} over {years:.1f} years ({port.sum() / years:+.2%}/yr at 1x)")
    print(f"  worst day {port.min():+.2%}  worst month {monthly.sum(axis=1).min():+.2%}  "
          f"max drawdown {(port.cumsum() - port.cumsum().cummax()).min():+.2%}")
    print(f"  months profitable: {(monthly.sum(axis=1) > 0).mean():.0%}")
    if len(kept) > 1:
        print("  monthly P&L correlation between pairs:")
        print(monthly.corr().round(2).to_string())

    odds = odds_table(port.to_numpy())
    print("\n== Challenge odds (target +10%, max loss -10%, daily -5%; no time limit) ==")
    with pd.option_context("display.float_format", "{:.3f}".format):
        print(odds.to_string(index=False))
    best = recommend_scale(odds)
    if best is None:
        print("\nNo scale meets P(daily breach) < 2% and P(fail) < 10%.")
    else:
        row = odds[odds["scale"] == best].iloc[0]
        print(f"\nRecommended scale: {best:g}x notional (STATARB_NOTIONAL_MULT={best:g}) -> "
              f"P(pass) {row.p_pass:.0%}, P(pass within 12 months) {row.p_pass_12m:.0%}, "
              f"median {row.median_months_to_pass:.0f} months")


if __name__ == "__main__":
    main()
