"""Shared engine for the BACKTEST_SPEC.md day-trading setups (Section 1).

Data: M5 bars (UTC, bar OPEN times, bid prices) from this repo's data folders. Fills follow
Section 1.2:
  1. no look-ahead - a signal on bar t fills at bar t+1's open or later;
  2. stops fill at the stop, or at the bar open if the bar gaps through it;
  3. limits fill only if price trades THROUGH the limit by >= 1 tick;
  4. if one bar covers both stop and target, the stop is assumed first;
  5. day trades are closed at the strategy's end time.
Costs (Section 1.3) are parameters and every result is reported at x0, x1 and x2.
Sizing (1.4): 0.5% of equity at risk from the entry-to-stop distance, leverage capped
(10x FX, 4x indices); strategies without a stop use 1x equity notional. 1R = 0.5% of the
100,000 starting equity for every strategy, so R is comparable. Equity is not compounded.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

EQUITY = 100_000.0
RISK = 0.005
ONE_R = EQUITY * RISK


# ----------------------------------------------------------------------- cost model
@dataclass(frozen=True)
class CostModel:
    """Per-instrument costs in PRICE units (spread, slippage) and as a fraction of notional
    (commission, per side). If use_bar_spread, the bar's own spread is used for the spread
    cost (falling back to `spread` when the bar has none)."""
    spread: float
    slippage: float
    commission_frac: float = 0.0
    use_bar_spread: bool = False
    leverage_cap: float = 10.0
    tick: float = 0.00001
    financing_per_year: float = 0.0    # swap, fraction of notional per year (360-day basis)


def rollover_nights(entry: pd.Timestamp, exit_: pd.Timestamp, hour_utc: int = 21) -> int:
    """Weekday rollovers (hour_utc UTC) strictly between entry and exit; Wednesday counts
    three times (the weekend is charged then)."""
    if exit_ <= entry:
        return 0
    n = 0
    day = entry.normalize()
    while day <= exit_:
        roll = day + pd.Timedelta(hours=hour_utc)
        if day.dayofweek < 5 and entry < roll < exit_:
            n += 3 if day.dayofweek == 2 else 1
        day += pd.Timedelta(days=1)
    return n


def pip_size(symbol: str) -> float:
    return 0.01 if symbol.upper().startswith("USDJPY") or symbol.upper().endswith("JPY") else 0.0001


def fx_costs(symbol: str) -> CostModel:
    """Spec defaults: spread 0.8 pip EURUSD / 1.2 pip others, commission 3.5 USD per 100k
    per side, slippage 0.2 pip on market and stop orders."""
    pip = pip_size(symbol)
    spread = (0.8 if symbol.upper().startswith("EURUSD") else 1.2) * pip
    return CostModel(spread=spread, slippage=0.2 * pip, commission_frac=3.5 / 100_000,
                     use_bar_spread=False, leverage_cap=10.0, tick=pip / 10)


def index_costs(median_spread: float, tick: float) -> CostModel:
    """Index CFDs (stand-ins for SPY/QQQ): the broker's own bar spread, slippage of half the
    median spread per market/stop fill, no commission, 4x leverage cap."""
    return CostModel(spread=median_spread, slippage=0.5 * median_spread, commission_frac=0.0,
                     use_bar_spread=True, leverage_cap=4.0, tick=tick)


# ----------------------------------------------------------------------- trades
@dataclass
class Trade:
    symbol: str
    side: int                 # +1 long, -1 short
    entry_time: pd.Timestamp
    entry_price: float
    entry_kind: str           # market | stop | limit
    exit_time: pd.Timestamp
    exit_price: float
    exit_kind: str            # stop | target | time | close
    stop: float = float("nan")
    spread_in: float = float("nan")    # bar spread at entry / exit (price), nan = use default
    spread_out: float = float("nan")
    ref_exit: float = float("nan")     # market price at exit time (for the random baseline)
    tag: str = ""
    weight: float = 1.0                # notional multiplier (e.g. 0.25 per leg of a basket)


SLIPPED = {"market", "stop", "time", "close"}


def price_trades(trades: Sequence[Trade], costs: Dict[str, CostModel],
                 mult: float = 1.0) -> pd.DataFrame:
    """Turn trades into money: size, gross P&L, costs x mult, net P&L and R."""
    cols = ["symbol", "side", "entry_time", "entry_price", "entry_kind", "exit_time",
            "exit_price", "exit_kind", "stop", "notional", "gross", "cost", "net", "R", "tag"]
    rows = []
    for t in trades:
        c = costs[t.symbol]
        if math.isfinite(t.stop) and t.stop != t.entry_price:
            frac = abs(t.entry_price - t.stop) / t.entry_price
            notional = min(ONE_R / frac, c.leverage_cap * EQUITY)
        else:
            notional = EQUITY
        notional *= t.weight
        units = notional / t.entry_price
        gross = t.side * (t.exit_price - t.entry_price) * units
        s_in = t.spread_in if (c.use_bar_spread and math.isfinite(t.spread_in) and t.spread_in > 0) else c.spread
        s_out = t.spread_out if (c.use_bar_spread and math.isfinite(t.spread_out) and t.spread_out > 0) else c.spread
        spread_cost = 0.5 * (s_in + s_out) * units
        slip = c.slippage * units * ((t.entry_kind in SLIPPED) + (t.exit_kind in SLIPPED))
        comm = 2 * c.commission_frac * notional
        fin = (c.financing_per_year / 360 * notional * rollover_nights(t.entry_time, t.exit_time)
               if c.financing_per_year else 0.0)
        cost = mult * (spread_cost + slip + comm + fin)
        net = gross - cost
        rows.append((t.symbol, t.side, t.entry_time, t.entry_price, t.entry_kind, t.exit_time,
                     t.exit_price, t.exit_kind, t.stop, notional, gross, cost, net, net / ONE_R,
                     t.tag))
    return pd.DataFrame(rows, columns=cols)


# ----------------------------------------------------------------------- exit simulation
def walk_exit(o: np.ndarray, h: np.ndarray, l: np.ndarray, c: np.ndarray, start: int, end: int,
              side: int, stop: float, target: float, tick: float,
              stop_active_on_start: bool = True) -> Tuple[int, float, str]:
    """Walk bars start..end (inclusive). Stop first (gap -> bar open), then a target LIMIT
    that needs a trade-through of 1 tick; same bar -> stop. If neither, exit at close[end]
    ('close'). Returns (bar index, price, kind)."""
    for i in range(start, end + 1):
        if math.isfinite(stop) and (i > start or stop_active_on_start):
            if side == 1 and l[i] <= stop:
                return i, (o[i] if o[i] < stop else stop), "stop"
            if side == -1 and h[i] >= stop:
                return i, (o[i] if o[i] > stop else stop), "stop"
        if math.isfinite(target):
            if side == 1 and h[i] >= target + tick * 0.999:
                return i, target, "target"
            if side == -1 and l[i] <= target - tick * 0.999:
                return i, target, "target"
    return end, c[end], "close"


# ----------------------------------------------------------------------- statistics
def stats(df: pd.DataFrame, days: Optional[Sequence[pd.Timestamp]] = None) -> Dict[str, float]:
    if df.empty:
        return {"trades": 0, "win_rate": float("nan"), "avg_win": float("nan"),
                "avg_loss": float("nan"), "expectancy_R": float("nan"), "profit_factor": float("nan"),
                "net": 0.0, "net_pct": 0.0, "cagr": float("nan"), "sharpe": float("nan"),
                "max_dd_pct": 0.0, "longest_losing_streak": 0, "top5_share": float("nan")}
    net = df["net"]
    wins, losses = net[net > 0], net[net <= 0]
    daily = df.groupby(pd.to_datetime(df["exit_time"]).dt.normalize())["net"].sum()
    if days is not None and len(days):
        daily = daily.reindex(pd.DatetimeIndex(days), fill_value=0.0)
    eq = EQUITY + daily.cumsum()
    dd = (eq / eq.cummax().clip(lower=EQUITY) - 1).min()
    span = (pd.to_datetime(df["exit_time"]).max() - pd.to_datetime(df["entry_time"]).min()).days / 365.25
    total = float(net.sum())
    cagr = ((EQUITY + total) / EQUITY) ** (1 / span) - 1 if span > 0.2 and EQUITY + total > 0 else float("nan")
    sharpe = float(daily.mean() / daily.std() * np.sqrt(252)) if daily.std() > 0 else float("nan")
    streak = cur = 0
    for v in net:
        cur = cur + 1 if v <= 0 else 0
        streak = max(streak, cur)
    top5 = net.nlargest(5).sum() / total if total > 0 else float("nan")
    return {"trades": int(len(df)), "win_rate": round(float((net > 0).mean()), 3),
            "avg_win": round(float(wins.mean()), 2) if len(wins) else 0.0,
            "avg_loss": round(float(losses.mean()), 2) if len(losses) else 0.0,
            "expectancy_R": round(float(df["R"].mean()), 4),
            "profit_factor": round(float(wins.sum() / -losses.sum()), 3) if losses.sum() < 0 else float("inf"),
            "net": round(total, 2), "net_pct": round(total / EQUITY * 100, 2),
            "cagr": round(cagr * 100, 2) if math.isfinite(cagr) else float("nan"),
            "sharpe": round(sharpe, 3) if math.isfinite(sharpe) else float("nan"),
            "max_dd_pct": round(float(dd) * 100, 2), "longest_losing_streak": int(streak),
            "top5_share": round(float(top5), 3) if math.isfinite(top5) else float("nan")}


# ----------------------------------------------------------------------- baselines
def random_entry_totals(trades: Sequence[Trade], costs: Dict[str, CostModel], runs: int = 100,
                        seed: int = 7) -> np.ndarray:
    """Same entries/exit times and size, random direction, market fills both ways, costs x1.
    Returns the total net P&L of each run."""
    if not trades:
        return np.zeros(runs)
    rng = np.random.default_rng(seed)
    base = []
    for t in trades:
        ref = t.ref_exit if math.isfinite(t.ref_exit) else t.exit_price
        base.append(Trade(t.symbol, 1, t.entry_time, t.entry_price, "market", t.exit_time, ref,
                          "time", t.stop, t.spread_in, t.spread_out, weight=t.weight))
    long_ = price_trades(base, costs, 1.0)
    gross = long_["gross"].to_numpy()
    cost = long_["cost"].to_numpy()
    out = np.empty(runs)
    for k in range(runs):
        sides = rng.choice([-1.0, 1.0], size=len(gross))
        out[k] = float((sides * gross - cost).sum())
    return out


def in_out_split(start: pd.Timestamp, end: pd.Timestamp, frac: float = 0.7) -> pd.Timestamp:
    return start + frac * (end - start)


# ----------------------------------------------------------------------- sweep + selection
@dataclass
class SweepResult:
    params: Dict[str, object]
    trades: List[Trade]


def choose_best(results: Sequence[SweepResult], costs: Dict[str, CostModel], cut: pd.Timestamp,
                min_trades: int = 30) -> Tuple[Optional[int], pd.DataFrame]:
    """In-sample table of every combination (costs x1) and the index of the best one by
    in-sample expectancy (R) among those with >= min_trades in-sample trades."""
    rows = []
    for i, r in enumerate(results):
        p = price_trades([t for t in r.trades if t.entry_time < cut], costs, 1.0)
        s = stats(p)
        rows.append({**{k: v for k, v in r.params.items()}, "is_trades": s["trades"],
                     "is_exp_R": s["expectancy_R"], "is_pf": s["profit_factor"],
                     "is_net": s["net"]})
    table = pd.DataFrame(rows)
    ok = table[table["is_trades"] >= min_trades]
    best = int(ok["is_exp_R"].idxmax()) if len(ok) and ok["is_exp_R"].notna().any() else None
    return best, table


def walk_forward(results: Sequence[SweepResult], costs: Dict[str, CostModel],
                 start: pd.Timestamp, end: pd.Timestamp, train_years: float = 2.0,
                 test_months: int = 6, min_trades: int = 20) -> pd.DataFrame:
    """Rolling 2-year train / 6-month test: pick the best train combination, record the test."""
    priced = [price_trades(r.trades, costs, 1.0) for r in results]
    rows = []
    t0 = start
    while True:
        train_end = t0 + pd.DateOffset(months=int(train_years * 12))
        test_end = train_end + pd.DateOffset(months=test_months)
        if train_end >= end:
            break
        best, best_exp = None, -np.inf
        for i, p in enumerate(priced):
            tr = p[(p["entry_time"] >= t0) & (p["entry_time"] < train_end)]
            if len(tr) >= min_trades and tr["R"].mean() > best_exp:
                best, best_exp = i, tr["R"].mean()
        if best is not None:
            p = priced[best]
            te = p[(p["entry_time"] >= train_end) & (p["entry_time"] < min(test_end, end))]
            rows.append({"test_start": train_end.date(), "test_end": min(test_end, end).date(),
                         "chosen": str(results[best].params), "trades": len(te),
                         "exp_R": round(float(te["R"].mean()), 4) if len(te) else float("nan"),
                         "net": round(float(te["net"].sum()), 2)})
        t0 = t0 + pd.DateOffset(months=test_months)
    return pd.DataFrame(rows)
