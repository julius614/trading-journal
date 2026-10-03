"""Fast single-symbol backtest for research and tuning.

Signals come from the real AMDStrategy.on_bar. The trade simulator follows the same rules
as PaperBroker + TradeManager: entry at the signal bar's close (ask for longs), stops and
targets checked from the next bar with the stop first on ambiguous bars, two legs, and the
runner moved to break-even after TP1. A test checks it matches backtest.py trade for trade.

Simplifications vs the full Bot: one symbol at a time, so the cross-pair max-open-trades
cap and the daily loss breaker are not applied (they change *which* trades are taken, not
the per-trade R).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from ..config import AppConfig, pip_size
from ..execution import default_symbol_info
from ..quantitative_filters import atr
from ..risk_manager import position_size
from ..strategy_amd import AMDStrategy, Signal


@dataclass(frozen=True)
class Costs:
    spread_pips: float = 0.0          # fixed spread (ask = bid + spread)
    commission_per_lot: float = 0.0   # round trip, charged per closed lot
    slippage_pips: float = 0.0        # adverse slippage on market entries and stop fills

    def scaled(self, k: float) -> "Costs":
        return Costs(self.spread_pips * k, self.commission_per_lot * k, self.slippage_pips * k)


RAW_ACCOUNT = {   # typical raw-spread account during London/NY hours
    "EURUSD": Costs(spread_pips=0.2, commission_per_lot=7.0, slippage_pips=0.2),
    "GBPUSD": Costs(spread_pips=0.5, commission_per_lot=7.0, slippage_pips=0.2),
}


def daily_atr_by_day(bars: pd.DataFrame, period: int) -> Dict[date, Optional[float]]:
    """ATR available at the start of each day, computed exactly like DataFetcher.current_atr:
    the last (3*period+1) completed daily bars, Wilder ATR, last value."""
    daily = bars.resample("1D", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    days = sorted(set(bars.index.date))
    window = period * 3 + 1
    out: Dict[date, Optional[float]] = {}
    for d in days:
        prior = daily[daily.index.date < d].iloc[-window:]
        series = atr(prior, period).dropna() if len(prior) else pd.Series(dtype=float)
        out[d] = float(series.iloc[-1]) if len(series) else None
    return out


def generate_signals(bars: pd.DataFrame, symbol: str, cfg: AppConfig,
                     atr_by_day: Optional[Dict[date, Optional[float]]] = None) -> List[Signal]:
    """Run the real strategy over closed bars. Only bars from the end of the Asian session to
    the end of the last trade window are evaluated; on other bars on_bar does nothing."""
    strat_log = logging.getLogger("bots.amd_fx.strategy_amd")
    old_level = strat_log.level
    strat_log.setLevel(logging.WARNING)
    try:
        if atr_by_day is None:
            atr_by_day = daily_atr_by_day(bars, cfg.strategy.atr_period)
        s = cfg.session
        first = s.asian_end
        last = max(w[1] for w in s.trade_windows)
        times = bars.index.time
        active = np.flatnonzero((times >= first) & (times <= last))
        strat = AMDStrategy(symbol, cfg)
        n = cfg.strategy.history_bars
        signals = []
        for i in active:
            window = bars.iloc[max(0, i - n + 1): i + 1]
            sig = strat.on_bar(window, atr_by_day.get(bars.index[i].date()))
            if sig is not None:
                signals.append(sig)
        return signals
    finally:
        strat_log.setLevel(old_level)


@dataclass
class _Leg:
    name: str
    volume: float
    tp: float
    sl: float
    open: bool = True
    exit_price: float = 0.0
    reason: str = ""


@dataclass
class SimTrade:
    symbol: str
    time: pd.Timestamp
    side: int
    window: str
    entry: float
    stop: float
    tp1: float
    tp2: float
    lots: float
    risk_amount: float
    zscore: float
    vol_ratio: float
    legs: List[_Leg] = field(default_factory=list)
    be_done: bool = False
    exit_time: Optional[pd.Timestamp] = None
    pnl: float = 0.0

    @property
    def r(self) -> float:
        return self.pnl / self.risk_amount if self.risk_amount else 0.0


def _round_down(v: float, step: float) -> float:
    return round(math.floor(v / step + 1e-9) * step, 8)


def simulate(bars: pd.DataFrame, signals: List[Signal], symbol: str, cfg: AppConfig,
             costs: Costs, balance: float = 10_000.0, compound: bool = False) -> List[SimTrade]:
    """Simulate trades for one symbol. With compound=False every trade is sized on the
    starting balance (cleaner R statistics); compound=True mirrors the live bot."""
    if cfg.strategy.trail_after_tp1:
        raise NotImplementedError("trailing stops are not simulated")
    info = default_symbol_info(symbol)
    pip = pip_size(symbol)
    spr, slip = costs.spread_pips * pip, costs.slippage_pips * pip
    be_off = cfg.strategy.be_offset_pips * pip
    o = bars["open"].to_numpy()
    h = bars["high"].to_numpy()
    lo = bars["low"].to_numpy()
    c = bars["close"].to_numpy()
    pos = {t: i for i, t in enumerate(bars.index)}
    trades: List[SimTrade] = []
    busy_until = -1
    for sig in signals:
        i = pos[pd.Timestamp(sig.time)]
        if i <= busy_until:
            continue                                  # already in a trade on this symbol
        side = sig.side
        entry = (c[i] + spr + slip) if side == 1 else (c[i] - slip)
        if side == 1 and not (sig.stop_loss < entry < sig.tp1):
            continue
        if side == -1 and not (sig.tp1 < entry < sig.stop_loss):
            continue
        equity = balance
        lots = position_size(equity, cfg.risk.risk_per_trade, entry, sig.stop_loss,
                             info.tick_size, info.tick_value, info.volume_step,
                             info.volume_min, info.volume_max)
        if lots <= 0:
            continue
        risk = abs(entry - sig.stop_loss) / info.tick_size * info.tick_value * lots
        part = _round_down(lots * cfg.strategy.tp1_fraction, info.volume_step)
        rest = round(lots - part, 8)
        if part >= info.volume_min and rest >= info.volume_min:
            legs = [_Leg("A", part, sig.tp1, sig.stop_loss), _Leg("B", rest, sig.tp2, sig.stop_loss)]
        else:
            legs = [_Leg("B", lots, sig.tp2, sig.stop_loss)]
        tr = SimTrade(symbol, pd.Timestamp(sig.time), side, sig.window, entry, sig.stop_loss,
                      sig.tp1, sig.tp2, lots, risk, sig.zscore, sig.vol_ratio, legs)
        two_legs = len(legs) == 2
        k = i
        for k in range(i + 1, len(c)):
            for leg in tr.legs:
                if not leg.open:
                    continue
                if side == 1:      # long closes on the bid
                    hit_sl = lo[k] <= leg.sl
                    hit_tp = h[k] >= leg.tp
                    if hit_sl:
                        leg.exit_price, leg.reason = min(o[k], leg.sl) - slip, "sl"
                    elif hit_tp:
                        leg.exit_price, leg.reason = max(o[k], leg.tp), "tp"
                else:              # short closes on the ask
                    hit_sl = h[k] + spr >= leg.sl
                    hit_tp = lo[k] + spr <= leg.tp
                    if hit_sl:
                        leg.exit_price, leg.reason = max(o[k] + spr, leg.sl) + slip, "sl"
                    elif hit_tp:
                        leg.exit_price, leg.reason = min(o[k] + spr, leg.tp), "tp"
                if hit_sl or hit_tp:
                    leg.open = False
            runner = tr.legs[-1]
            if not any(leg.open for leg in tr.legs):
                break
            if not tr.be_done and runner.open:
                bid, ask = c[k], c[k] + spr
                if two_legs:
                    tp1_hit = not tr.legs[0].open
                else:
                    tp1_hit = bid >= tr.tp1 if side == 1 else ask <= tr.tp1
                if tp1_hit:
                    be = tr.entry + side * be_off
                    better = be > runner.sl if side == 1 else be < runner.sl
                    valid = be < bid if side == 1 else be > ask
                    if not better:
                        tr.be_done = True
                    elif valid:
                        runner.sl, tr.be_done = be, True
                    else:
                        px = bid if side == 1 else ask
                        if (side == 1 and px <= be) or (side == -1 and px >= be):
                            runner.open, runner.exit_price, runner.reason = False, px, "manual"
                            tr.be_done = True
                            break
        for leg in tr.legs:   # still open at the end of the data: close at the last price
            if leg.open:
                leg.exit_price = c[-1] if side == 1 else c[-1] + spr
                leg.reason, leg.open = "end", False
        tr.exit_time = bars.index[k]
        tr.pnl = sum((leg.exit_price - tr.entry) * side / info.tick_size * info.tick_value
                     * leg.volume - costs.commission_per_lot * leg.volume for leg in tr.legs)
        busy_until = k
        if compound:
            balance += tr.pnl
        trades.append(tr)
    return trades


def trades_frame(trades: List[SimTrade]) -> pd.DataFrame:
    rows = [{
        "symbol": t.symbol, "time": t.time, "year": t.time.year, "side": t.side,
        "window": t.window, "entry": t.entry, "stop": t.stop, "tp1": t.tp1, "tp2": t.tp2,
        "lots": t.lots, "risk": t.risk_amount, "pnl": t.pnl, "r": t.r, "zscore": t.zscore,
        "vol_ratio": t.vol_ratio, "be_done": t.be_done, "exit_time": t.exit_time,
        "exits": "+".join(f"{leg.name}:{leg.reason}" for leg in t.legs),
    } for t in trades]
    return pd.DataFrame(rows)


def stats(r: pd.Series) -> Dict[str, float]:
    """R statistics with a t-stat for the mean."""
    r = pd.Series(r, dtype=float)
    if r.empty:
        return {"trades": 0, "exp_r": np.nan, "pf": np.nan, "win": np.nan, "total_r": 0.0,
                "max_dd_r": 0.0, "t": np.nan}
    wins, losses = r[r > 0], r[r <= 0]
    eq = r.cumsum()
    sd = r.std(ddof=1) if len(r) > 1 else np.nan
    return {
        "trades": int(len(r)),
        "exp_r": float(r.mean()),
        "pf": float(wins.sum() / -losses.sum()) if losses.sum() < 0 else np.inf,
        "win": float(len(wins) / len(r)),
        "total_r": float(r.sum()),
        "max_dd_r": float((eq - eq.cummax().clip(lower=0)).min()),
        "t": float(r.mean() / (sd / np.sqrt(len(r)))) if sd and sd > 0 else np.nan,
    }
