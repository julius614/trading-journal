"""Position sizing and the "Prop Shield" circuit breakers."""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional, Tuple

from .config import RiskConfig, SessionConfig

log = logging.getLogger(__name__)


def _step_decimals(step: float) -> int:
    text = f"{step:.10f}".rstrip("0")
    return len(text.split(".")[1]) if "." in text else 0


def position_size(
    equity: float,
    risk_fraction: float,
    entry: float,
    stop: float,
    tick_size: float,
    tick_value: float,
    volume_step: float = 0.01,
    volume_min: float = 0.01,
    volume_max: float = 100.0,
) -> float:
    """Lots that risk `risk_fraction` of `equity` between `entry` and `stop`.

    tick_value is the account-currency value of one tick_size move for 1.0 lot
    (MT5 `symbol_info.trade_tick_value` / `trade_tick_size`). The result is rounded DOWN
    to volume_step, so actual risk never exceeds the target, and capped at volume_max.
    Returns 0.0 when even the minimum lot would risk too much.
    """
    if equity <= 0 or risk_fraction <= 0:
        raise ValueError("equity and risk_fraction must be positive")
    if tick_size <= 0 or tick_value <= 0 or volume_step <= 0:
        raise ValueError("tick_size, tick_value and volume_step must be positive")
    distance = abs(entry - stop)
    if distance <= 0:
        raise ValueError("entry and stop must differ")
    loss_per_lot = distance / tick_size * tick_value
    raw = equity * risk_fraction / loss_per_lot
    lots = math.floor(raw / volume_step + 1e-9) * volume_step
    lots = round(min(lots, volume_max), _step_decimals(volume_step))
    return lots if lots >= volume_min else 0.0


def pip_value_per_lot(pip: float, tick_size: float, tick_value: float) -> float:
    """Account-currency value of one pip for 1.0 lot."""
    return pip / tick_size * tick_value


def in_time_window(t: time, start: time, end: time) -> bool:
    """True if t is in [start, end); handles windows that cross midnight."""
    return start <= t < end if start <= end else (t >= start or t < end)


@dataclass
class RiskState:
    trading_day: Optional[date] = None
    day_start_equity: float = 0.0
    locked: bool = False
    lock_reason: str = ""


class RiskManager:
    """Daily loss breaker, open-trade cap, rollover pause and spread check."""

    def __init__(self, risk: RiskConfig, session: SessionConfig) -> None:
        self.risk = risk
        self.session = session
        self.state = RiskState()

    def trading_day(self, now: datetime) -> date:
        reset = self.session.day_reset
        shift = timedelta(hours=reset.hour, minutes=reset.minute)
        return (now - shift).date()

    def update_day(self, now: datetime, equity: float) -> bool:
        """Start a new trading day if needed. Returns True when a new day began."""
        day = self.trading_day(now)
        if day == self.state.trading_day:
            return False
        if self.state.locked:
            log.info("New trading day %s: breaker reset", day)
        self.state = RiskState(trading_day=day, day_start_equity=equity)
        log.info("Trading day %s starts with equity %.2f", day, equity)
        return True

    def daily_loss_fraction(self, equity: float) -> float:
        start = self.state.day_start_equity
        return (start - equity) / start if start > 0 else 0.0

    def check_breaker(self, equity: float) -> bool:
        """Lock trading for the day once realized + unrealized loss hits the limit.

        `equity` must be account equity (balance + floating P&L). Returns True if locked.
        """
        if self.state.locked:
            return True
        loss = self.daily_loss_fraction(equity)
        if loss >= self.risk.daily_loss_limit:
            self.state.locked = True
            self.state.lock_reason = (
                f"daily loss {loss:.2%} >= limit {self.risk.daily_loss_limit:.2%}"
            )
            log.error("PROP SHIELD: %s - trading disabled until next day", self.state.lock_reason)
        return self.state.locked

    def in_rollover(self, now: datetime) -> bool:
        return in_time_window(now.time(), self.session.rollover_start, self.session.rollover_end)

    def can_open(self, now: datetime, open_trades: int, spread_pips: Optional[float] = None) -> Tuple[bool, str]:
        """Whether a new trade may be opened right now, and why not if it may not."""
        if self.state.locked:
            return False, f"locked: {self.state.lock_reason}"
        if self.in_rollover(now):
            return False, "rollover window"
        if open_trades >= self.risk.max_open_trades:
            return False, f"max open trades ({self.risk.max_open_trades}) reached"
        if spread_pips is not None and spread_pips > self.risk.max_spread_pips:
            return False, f"spread {spread_pips:.1f} pips > {self.risk.max_spread_pips:.1f}"
        return True, "ok"
