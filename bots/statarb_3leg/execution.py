"""Broker interface (shared with the AMD bot), MT5 adapter, a currency-aware paper broker,
and the three-leg basket executor.

Basket rules:
- Legs are sent one after another. If any leg fails, every leg already filled is closed
  at market straight away (rollback), so the bot never sits on an unhedged leg.
- Closing sends all three closes; a failed close is retried, and a leg that still can't be
  closed keeps the basket open and is logged as CRITICAL for manual attention.
- The open basket is saved to a JSON file so a restarted bot can pick it up.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Mapping, Optional

import pandas as pd
from loguru import logger

from ..amd_fx.execution import (Broker, BrokerError, MT5Broker, OrderResult, Position,  # noqa: F401
                                SymbolInfo, Tick)
from .config import CONTRACT_SIZE, PIP, AppConfig, TRIANGLE
from .fee_gate import GateResult, convert, quote_ccy
from .risk_manager import LegPlan

__all__ = ["Broker", "BrokerError", "MT5Broker", "PaperBroker", "Basket", "Leg",
           "MultiLegExecutor", "OrderResult", "Position", "SymbolInfo", "Tick"]


# ---------------------------------------------------------------------- paper broker

@dataclass
class _PaperPos:
    ticket: int
    symbol: str
    side: int
    volume: float
    price_open: float
    comment: str
    open_time: pd.Timestamp


@dataclass
class PaperFill:
    ticket: int
    symbol: str
    side: int
    volume: float
    price_open: float
    price_close: float
    pnl: float
    open_time: pd.Timestamp
    close_time: pd.Timestamp


class PaperBroker(Broker):
    """In-memory broker for replays. Bar closes are BID prices; ask = bid + spread.

    Spreads come from a per-bar `spread_pips` column when the data has one (MT5 exports
    do), otherwise from `spread_pips[symbol]`. P&L is valued in the account currency at
    the current triangle mids. Commission is charged per lot when a position closes.
    """

    def __init__(self, balance: float = 10_000.0, account_ccy: str = "USD",
                 spread_pips: Optional[Mapping[str, float]] = None,
                 commission_per_lot: float = 0.0, timeframe: str = "M5") -> None:
        self.balance = balance
        self.account_ccy = account_ccy
        self.spread_pips = dict(spread_pips or {})
        self.commission_per_lot = commission_per_lot
        self.timeframe = timeframe
        self.data: Dict[str, pd.DataFrame] = {}
        self.now: Optional[pd.Timestamp] = None
        self._pos: Dict[int, _PaperPos] = {}
        self.fills: List[PaperFill] = []
        self._next = 1
        self.fail_orders: Dict[str, int] = {}   # symbol -> number of orders to reject (tests)

    def load_bars(self, symbol: str, bars: pd.DataFrame) -> None:
        cols = [c for c in ("open", "high", "low", "close", "spread_pips") if c in bars.columns]
        df = bars[cols].astype(float).sort_index()
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        self.data[symbol] = df

    def advance(self, ts: pd.Timestamp) -> None:
        self.now = ts

    def _row(self, symbol: str) -> pd.Series:
        if symbol not in self.data or self.now is None:
            raise BrokerError(f"no paper data for {symbol}")
        df = self.data[symbol]
        pos = df.index.searchsorted(self.now, side="right") - 1
        if pos < 0:
            raise BrokerError(f"no paper price for {symbol} yet")
        return df.iloc[pos]

    def _tick_now(self, symbol: str) -> Tick:
        row = self._row(symbol)
        spr = row["spread_pips"] if "spread_pips" in row.index and pd.notna(row["spread_pips"]) \
            else self.spread_pips.get(symbol, 0.0)
        bid = float(row["close"])
        return Tick(time=row.name.to_pydatetime(), bid=bid, ask=bid + float(spr) * PIP)

    def _mids(self) -> Dict[str, float]:
        out = {}
        for s in TRIANGLE:
            t = self._tick_now(s)
            out[s] = (t.bid + t.ask) / 2
        return out

    def _pnl(self, pos: _PaperPos, volume: float, price: float, mids: Mapping[str, float]) -> float:
        quote_pnl = (price - pos.price_open) * pos.side * volume * CONTRACT_SIZE
        return convert(quote_pnl, quote_ccy(pos.symbol), self.account_ccy, mids)

    async def connect(self) -> None:
        logger.info("Paper broker ready: balance {:.2f} {}", self.balance, self.account_ccy)

    async def shutdown(self) -> None:
        return None

    async def account_balance(self) -> float:
        return self.balance

    async def account_equity(self) -> float:
        if not self._pos:
            return self.balance
        mids = self._mids()
        floating = 0.0
        for p in self._pos.values():
            t = self._tick_now(p.symbol)
            floating += self._pnl(p, p.volume, t.bid if p.side == 1 else t.ask, mids)
        return self.balance + floating

    async def symbol_info(self, symbol: str) -> SymbolInfo:
        tick_value = 1.0
        if self.data and self.now is not None and quote_ccy(symbol) != self.account_ccy:
            tick_value = convert(1.0, quote_ccy(symbol), self.account_ccy, self._mids())
        return SymbolInfo(name=symbol, digits=5, point=0.00001, tick_size=0.00001,
                          tick_value=tick_value, volume_min=0.01, volume_max=100.0,
                          volume_step=0.01)

    async def get_rates(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        if timeframe != self.timeframe:
            raise BrokerError(f"paper broker only serves {self.timeframe}")
        if symbol not in self.data or self.now is None:
            raise BrokerError(f"no paper data for {symbol}")
        df = self.data[symbol]
        end = df.index.searchsorted(self.now, side="right")
        return df.iloc[max(0, end - count):end].copy()

    async def get_tick(self, symbol: str) -> Tick:
        return self._tick_now(symbol)

    async def positions(self, symbol: Optional[str] = None) -> List[Position]:
        if not self._pos:
            return []
        mids = self._mids()
        out = []
        for p in self._pos.values():
            if symbol and p.symbol != symbol:
                continue
            t = self._tick_now(p.symbol)
            px = t.bid if p.side == 1 else t.ask
            out.append(Position(p.ticket, p.symbol, p.side, p.volume, p.price_open, 0.0, 0.0,
                                self._pnl(p, p.volume, px, mids), p.comment))
        return out

    async def market_order(self, symbol: str, side: int, volume: float, sl: float,
                           tp: float, comment: str) -> OrderResult:
        if self.fail_orders.get(symbol, 0) > 0:
            self.fail_orders[symbol] -= 1
            return OrderResult(ok=False, message="paper: simulated rejection")
        if volume <= 0:
            return OrderResult(ok=False, message="volume must be positive")
        t = self._tick_now(symbol)
        price = t.ask if side == 1 else t.bid
        ticket = self._next
        self._next += 1
        assert self.now is not None
        self._pos[ticket] = _PaperPos(ticket, symbol, side, volume, price, comment, self.now)
        return OrderResult(ok=True, ticket=ticket, price=price, volume=volume)

    async def modify_sl(self, ticket: int, sl: float, tp: float) -> bool:
        return ticket in self._pos   # baskets don't use broker-side stops

    async def close_position(self, ticket: int, volume: Optional[float] = None) -> OrderResult:
        pos = self._pos.get(ticket)
        if pos is None:
            return OrderResult(ok=False, message=f"position {ticket} not found")
        t = self._tick_now(pos.symbol)
        price = t.bid if pos.side == 1 else t.ask
        vol = volume or pos.volume
        pnl = self._pnl(pos, vol, price, self._mids()) - self.commission_per_lot * vol
        self.balance += pnl
        assert self.now is not None
        self.fills.append(PaperFill(ticket, pos.symbol, pos.side, vol, pos.price_open, price, pnl,
                                    pos.open_time, self.now))
        if vol >= pos.volume - 1e-9:
            del self._pos[ticket]
        else:
            pos.volume = round(pos.volume - vol, 8)
        return OrderResult(ok=True, ticket=ticket, price=price, volume=vol)

    async def closed_pnl(self, ticket: int) -> float:
        return float(sum(f.pnl for f in self.fills if f.ticket == ticket))


# ---------------------------------------------------------------------- baskets

@dataclass
class Leg:
    symbol: str
    side: int
    lots: float
    ticket: int = 0
    price: float = 0.0
    closed: bool = False


@dataclass
class Basket:
    basket_id: str
    direction: int                 # +1 long spread, -1 short spread
    opened_at: str
    entry_z: float
    entry_deviation_pips: float
    entry_cost_pips: float
    legs: List[Leg] = field(default_factory=list)
    bars_held: int = 0
    closed: bool = False
    closed_at: str = ""
    exit_reason: str = ""
    exit_z: float = float("nan")
    pnl: float = 0.0

    @property
    def label(self) -> str:
        return "LONG spread" if self.direction == 1 else "SHORT spread"


class MultiLegExecutor:
    """Opens and closes three-leg baskets as one unit."""

    def __init__(self, broker: Broker, cfg: AppConfig, state_path: Optional[Path] = None,
                 close_retries: int = 3, retry_delay: float = 0.5) -> None:
        self.broker = broker
        self.cfg = cfg
        self.state_path = state_path
        self.close_retries = close_retries
        self.retry_delay = retry_delay
        self.basket: Optional[Basket] = None
        self.history: List[Basket] = []
        self._load()

    # ---- persistence
    def _load(self) -> None:
        if self.state_path is None or not self.state_path.exists():
            return
        try:
            raw = json.loads(self.state_path.read_text())
            if raw.get("basket"):
                b = raw["basket"]
                b["legs"] = [Leg(**leg) for leg in b["legs"]]
                self.basket = Basket(**b)
                logger.warning("Recovered open basket {} from {}", self.basket.basket_id,
                               self.state_path)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            logger.error("Could not read basket state {}: {}", self.state_path, exc)

    def _save(self) -> None:
        if self.state_path is None:
            return
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"basket": asdict(self.basket) if self.basket else None},
                                      indent=2, default=str))
            tmp.replace(self.state_path)
        except OSError as exc:
            logger.error("Could not save basket state: {}", exc)

    # ---- open / close
    async def _rollback(self, filled: List[Leg]) -> None:
        for leg in filled:
            res = await self.broker.close_position(leg.ticket)
            if res.ok:
                logger.warning("Rolled back {} leg (ticket {})", leg.symbol, leg.ticket)
            else:
                logger.critical("ROLLBACK FAILED for {} ticket {}: {} - close it manually!",
                                leg.symbol, leg.ticket, res.message)

    async def open_basket(self, plans: List[LegPlan], direction: int, z: float,
                          gate: GateResult, now: datetime) -> Optional[Basket]:
        if self.basket is not None:
            raise RuntimeError("a basket is already open")
        basket_id = f"SA3{now:%y%m%d%H%M}"
        filled: List[Leg] = []
        for plan in plans:
            res = await self.broker.market_order(self.cfg.broker_symbol(plan.symbol), plan.side,
                                                 plan.lots, 0.0, 0.0,
                                                 f"{basket_id}:{plan.symbol}")
            if not res.ok:
                logger.error("{} {} leg failed ({}) - rolling back {} filled leg(s)",
                             basket_id, plan.symbol, res.message, len(filled))
                await self._rollback(filled)
                return None
            filled.append(Leg(plan.symbol, plan.side, plan.lots, res.ticket, res.price))
        self.basket = Basket(basket_id, direction, now.isoformat(), z,
                             gate.expected_reversion_pips, gate.total_cost_pips, filled)
        self._save()
        logger.info("OPEN {} {}: z={:+.2f} edge {:.2f} pips vs cost {:.2f} pips | {}",
                    basket_id, self.basket.label, z, gate.expected_reversion_pips,
                    gate.total_cost_pips,
                    ", ".join(f"{'BUY' if l.side == 1 else 'SELL'} {l.lots:.2f} {l.symbol}@{l.price:.5f}"
                              for l in filled))
        return self.basket

    async def floating_pnl(self) -> float:
        if self.basket is None:
            return 0.0
        tickets = {leg.ticket for leg in self.basket.legs if not leg.closed}
        return sum(p.profit for p in await self.broker.positions() if p.ticket in tickets)

    async def close_basket(self, reason: str, now: datetime, z: float = float("nan")) -> Optional[Basket]:
        """Close every open leg. Returns the closed basket, or None if a leg is stuck."""
        b = self.basket
        if b is None:
            return None
        live = {p.ticket for p in await self.broker.positions()}
        for leg in b.legs:
            if leg.closed:
                continue
            if leg.ticket not in live:          # closed outside the bot (or by the broker)
                leg.closed = True
                continue
            for attempt in range(1, self.close_retries + 1):
                res = await self.broker.close_position(leg.ticket)
                if res.ok:
                    leg.closed = True
                    break
                logger.warning("Close {} ticket {} attempt {} failed: {}", leg.symbol,
                               leg.ticket, attempt, res.message)
                if self.retry_delay:
                    await asyncio.sleep(self.retry_delay)
        stuck = [leg for leg in b.legs if not leg.closed]
        if stuck:
            self._save()
            logger.critical("Basket {}: could not close {} - CHECK THE TERMINAL", b.basket_id,
                            ", ".join(f"{l.symbol} #{l.ticket}" for l in stuck))
            return None
        b.pnl = 0.0
        for leg in b.legs:
            b.pnl += await self.broker.closed_pnl(leg.ticket)
        b.closed, b.closed_at, b.exit_reason, b.exit_z = True, now.isoformat(), reason, z
        self.history.append(b)
        self.basket = None
        self._save()
        logger.info("CLOSE {} ({}): P&L {:+.2f} after {} bars", b.basket_id, reason, b.pnl,
                    b.bars_held)
        return b
