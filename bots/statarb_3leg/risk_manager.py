"""Dollar-neutral 3-leg sizing, the daily-loss circuit breaker, and entry blackouts
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

# Leg directions for a LONG spread (buy EURGBP, sell EURUSD, buy GBPUSD); short = negated.
LONG_SPREAD_SIDES: Dict[str, int] = {"EURGBP": 1, "EURUSD": -1, "GBPUSD": 1}


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
) -> List[LegPlan]:
    """Lot sizes for a dollar-neutral triangle book.

    EUR notional of the EURGBP and EURUSD legs = notional_equity_mult x equity (converted
    to EUR). EURGBP and EURUSD trade the same N lots, so EUR exposure cancels exactly;
    GBPUSD trades N x EURGBP lots, so GBP cancels (to lot rounding), and USD is left with
    N x 100k x (EURUSD - EURGBP x GBPUSD), i.e. the spread itself - near zero.
    Returns [] if N rounds below the minimum lot.
    """
    if direction not in (1, -1):
        raise ValueError("direction must be +1 (long spread) or -1 (short spread)")
    if equity <= 0:
        raise ValueError("equity must be positive")
    eur_notional = convert(equity * risk.notional_equity_mult, risk.account_currency, "EUR", mids)
    step = max(infos["EURGBP"].volume_step, infos["EURUSD"].volume_step)
    n = min(_floor_step(eur_notional / CONTRACT_SIZE, step), risk.max_lots_per_leg)
    if n < max(infos["EURGBP"].volume_min, infos["EURUSD"].volume_min):
        return []
    m = min(_round_step(n * mids["EURGBP"], infos["GBPUSD"].volume_step), risk.max_lots_per_leg)
    if m < infos["GBPUSD"].volume_min:
        return []
    lots = {"EURGBP": n, "EURUSD": n, "GBPUSD": m}
    return [LegPlan(s, direction * LONG_SPREAD_SIDES[s], lots[s])
            for s in ("EURGBP", "EURUSD", "GBPUSD")]


def currency_exposure(plans: Sequence[LegPlan], mids: Mapping[str, float],
                      account_ccy: str = "USD") -> Dict[str, float]:
    """Net exposure per currency, expressed in the account currency."""
    exp: Dict[str, float] = {"USD": 0.0, "EUR": 0.0, "GBP": 0.0}
    for p in plans:
        units = p.side * p.lots * CONTRACT_SIZE
        exp[base_ccy(p.symbol)] += units
        exp[quote_ccy(p.symbol)] -= units * mids[p.symbol]
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
