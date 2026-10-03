"""Beta-weighted 2-leg sizing, the daily-loss circuit breaker, and entry blackouts
(news calendar and rollover)."""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

from loguru import logger

from ..amd_fx.execution import SymbolInfo
from ..amd_fx.risk_manager import in_time_window
from .config import CONTRACT_SIZE, FilterConfig, RiskConfig
from .fee_gate import base_ccy, convert, quote_ccy

NEW_YORK = ZoneInfo("America/New_York")

@dataclass(frozen=True)
class LegPlan:
    symbol: str
    side: int       # +1 buy, -1 sell
    lots: float


def _floor_step(x: float, step: float) -> float:
    return round(math.floor(x / step + 1e-9) * step, 8)


def _round_step(x: float, step: float) -> float:
    return round(round(x / step) * step, 8)


def balance_legs(
    direction: int,
    equity: float,
    mids: Mapping[str, float],
    infos: Mapping[str, SymbolInfo],
    risk: RiskConfig,
    y: str,
    x: str,
    beta: float,
) -> List[LegPlan]:
    """Lot sizes for a beta-weighted pair book.

    Long spread (direction +1) = BUY y, SELL beta x of x (BUY x if beta < 0); short spread is
    the mirror. The y-leg notional is notional_equity_mult x equity; the x-leg notional is
    |beta| x that (both valued in USD), so P&L tracks the spread y - beta x.
    Returns [] if either leg rounds below its minimum lot.
    """
    if direction not in (1, -1):
        raise ValueError("direction must be +1 (long spread) or -1 (short spread)")
    if equity <= 0:
        raise ValueError("equity must be positive")
    if not math.isfinite(beta) or beta == 0:
        raise ValueError("hedge ratio must be finite and non-zero")
    notional = convert(equity * risk.notional_equity_mult, risk.account_currency,
                       quote_ccy(y), mids)
    n_y = min(_floor_step(notional / (CONTRACT_SIZE * mids[y]), infos[y].volume_step),
              risk.max_lots_per_leg)
    if n_y < infos[y].volume_min:
        return []
    n_x = min(_round_step(n_y * abs(beta) * mids[y] / mids[x], infos[x].volume_step),
              risk.max_lots_per_leg)
    if n_x < infos[x].volume_min:
        return []
    x_side = -direction if beta > 0 else direction
    return [LegPlan(y, direction, n_y), LegPlan(x, x_side, n_x)]


def currency_exposure(plans: Sequence[LegPlan], mids: Mapping[str, float],
                      account_ccy: str = "USD") -> Dict[str, float]:
    """Net exposure per currency, in the account currency. A pairs book is deliberately
    long one currency and short another; this shows how much."""
    exp: Dict[str, float] = {}
    for p in plans:
        units = p.side * p.lots * CONTRACT_SIZE
        exp[base_ccy(p.symbol)] = exp.get(base_ccy(p.symbol), 0.0) + units
        exp[quote_ccy(p.symbol)] = exp.get(quote_ccy(p.symbol), 0.0) - units * mids[p.symbol]
    return {c: convert(v, c, account_ccy, mids) for c, v in exp.items()}


# ---------------------------------------------------------------------- news calendar

@dataclass(frozen=True)
class NewsEvent:
    time: datetime    # UTC
    currency: str
    impact: str
    title: str


class NewsCalendar:
    """Economic calendar loaded from CSV: columns datetime_utc, currency, impact, title.

    Export one from your calendar provider (e.g. Forex Factory / Investing.com) for the
    weeks you trade; times must be UTC.
    """

    def __init__(self, events: Iterable[NewsEvent] = ()) -> None:
        self.events: List[NewsEvent] = sorted(events, key=lambda e: e.time)

    @classmethod
    def from_csv(cls, path: str | Path) -> "NewsCalendar":
        events = []
        with open(path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                t = datetime.fromisoformat(row["datetime_utc"].strip().replace("Z", "+00:00"))
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
                events.append(NewsEvent(t.astimezone(timezone.utc), row["currency"].strip().upper(),
                                        row["impact"].strip().lower(), row.get("title", "").strip()))
        logger.info("Loaded {} calendar events from {}", len(events), path)
        return cls(events)

    def __len__(self) -> int:
        return len(self.events)

    def last_event_time(self) -> Optional[datetime]:
        return self.events[-1].time if self.events else None

    def blackout(self, now: datetime, cfg: FilterConfig) -> Optional[NewsEvent]:
        """The event that puts `now` inside its +- buffer window, if any."""
        buf = timedelta(minutes=cfg.news_buffer_minutes)
        for e in self.events:
            if e.time - buf > now:
                break
            if (e.currency in cfg.news_currencies and e.impact in cfg.news_impacts
                    and abs(e.time - now) <= buf):
                return e
        return None


# ---------------------------------------------------------------------- risk manager

@dataclass
class RiskState:
    trading_day: Optional[date] = None
    day_start_equity: float = 0.0
    locked: bool = False
    lock_reason: str = ""


class RiskManager:
    """Prop Shield (daily loss breaker), rollover pause, and news blackout."""

    def __init__(self, risk: RiskConfig, filters: FilterConfig,
                 news: Optional[NewsCalendar] = None) -> None:
        if filters.rollover_anchor not in ("ny_close", "utc"):
            raise ValueError(f"rollover_anchor must be 'ny_close' or 'utc', "
                             f"got {filters.rollover_anchor!r}")
        self.risk = risk
        self.filters = filters
        self.news = news or NewsCalendar()
        self.state = RiskState()

    def trading_day(self, now: datetime) -> date:
        r = self.risk.day_reset
        return (now - timedelta(hours=r.hour, minutes=r.minute)).date()

    def update_day(self, now: datetime, equity: float) -> bool:
        day = self.trading_day(now)
        if day == self.state.trading_day:
            return False
        self.state = RiskState(trading_day=day, day_start_equity=equity)
        logger.info("Trading day {} starts with equity {:.2f}", day, equity)
        return True

    def daily_loss_fraction(self, equity: float) -> float:
        start = self.state.day_start_equity
        return (start - equity) / start if start > 0 else 0.0

    def check_breaker(self, equity: float) -> bool:
        """Lock for the rest of the day once realized + floating loss hits the limit."""
        if self.state.locked:
            return True
        loss = self.daily_loss_fraction(equity)
        if loss >= self.risk.daily_loss_limit:
            self.state.locked = True
            self.state.lock_reason = f"daily loss {loss:.2%} >= {self.risk.daily_loss_limit:.2%}"
            logger.error("PROP SHIELD: {} - closing all legs, trading halted until next day",
                         self.state.lock_reason)
        return self.state.locked

    def in_rollover(self, now: datetime) -> bool:
        f = self.filters
        if f.rollover_anchor == "ny_close":
            if now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)
            ny = now.astimezone(NEW_YORK).time()
            return in_time_window(ny, f.rollover_ny_start, f.rollover_ny_end)
        return in_time_window(now.time(), f.rollover_start, f.rollover_end)

    def entry_block(self, now: datetime) -> Tuple[bool, str]:
        """(blocked, reason) for opening a new basket right now."""
        if self.state.locked:
            return True, f"locked: {self.state.lock_reason}"
        if self.in_rollover(now):
            return True, "rollover window"
        event = self.news.blackout(now, self.filters)
        if event is not None:
            return True, f"news: {event.currency} {event.title} at {event.time:%H:%M}"
        return False, "ok"
