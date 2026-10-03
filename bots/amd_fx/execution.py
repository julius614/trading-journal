"""Broker interface, MetaTrader 5 adapter, paper broker, and trade management.

Every trade is placed as two legs with broker-side stops and targets:
  leg A (tp1_fraction of size) -> TP1 at the Asian midpoint
  leg B (the rest)             -> TP2 at the opposite Asian boundary
When leg A is gone (TP1 filled), leg B's stop moves to break-even +0.5 pip. Keeping SL/TP
on the broker means positions stay protected if the bot disconnects. If the size is too
small to split, a single leg targets TP2 and its stop moves to break-even when price
reaches TP1.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from .config import AppConfig, BrokerConfig, pip_size
from .strategy_amd import Signal

log = logging.getLogger(__name__)


class BrokerError(RuntimeError):
    """Raised when the broker connection or a request fails irrecoverably."""


# ---------------------------------------------------------------------- data types

@dataclass(frozen=True)
class SymbolInfo:
    name: str
    digits: int
    point: float
    tick_size: float
    tick_value: float
    volume_min: float
    volume_max: float
    volume_step: float

    @property
    def pip(self) -> float:
        return pip_size(self.name)


@dataclass(frozen=True)
class Tick:
    time: datetime
    bid: float
    ask: float

    def spread(self) -> float:
        return self.ask - self.bid


@dataclass(frozen=True)
class Position:
    ticket: int
    symbol: str
    side: int
    volume: float
    price_open: float
    sl: float
    tp: float
    profit: float
    comment: str


@dataclass(frozen=True)
class OrderResult:
    ok: bool
    ticket: int = 0
    price: float = 0.0
    volume: float = 0.0
    message: str = ""


# ---------------------------------------------------------------------- interface

class Broker(ABC):
    """Async broker interface. All times are UTC; get_rates returns CLOSED bars only."""

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def shutdown(self) -> None: ...

    @abstractmethod
    async def account_equity(self) -> float: ...

    @abstractmethod
    async def account_balance(self) -> float: ...

    @abstractmethod
    async def symbol_info(self, symbol: str) -> SymbolInfo: ...

    @abstractmethod
    async def get_rates(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        """Closed OHLC bars, UTC DatetimeIndex of bar open times, oldest first."""

    @abstractmethod
    async def get_tick(self, symbol: str) -> Tick: ...

    @abstractmethod
    async def positions(self, symbol: Optional[str] = None) -> List[Position]: ...

    @abstractmethod
    async def market_order(self, symbol: str, side: int, volume: float, sl: float,
                           tp: float, comment: str) -> OrderResult: ...

    @abstractmethod
    async def modify_sl(self, ticket: int, sl: float, tp: float) -> bool: ...

    @abstractmethod
    async def close_position(self, ticket: int, volume: Optional[float] = None) -> OrderResult: ...

    @abstractmethod
    async def closed_pnl(self, ticket: int) -> float:
        """Realized P&L (incl. commission and swap) of a closed position."""


# ---------------------------------------------------------------------- MetaTrader 5

_MT5_TIMEFRAMES = {"M1": "TIMEFRAME_M1", "M5": "TIMEFRAME_M5", "M15": "TIMEFRAME_M15",
                   "M30": "TIMEFRAME_M30", "H1": "TIMEFRAME_H1", "H4": "TIMEFRAME_H4",
                   "D1": "TIMEFRAME_D1"}
_RETRYABLE = {10004, 10020, 10021, 10024, 10031}   # requote, price changed, off quotes,
                                                     # too frequent, no connection
_FILLING_UNSUPPORTED = 10030


class MT5Broker(Broker):
    """MetaTrader 5 adapter (official `MetaTrader5` package; Windows with a terminal running).

    The MT5 API is blocking, so every call runs in a worker thread via asyncio.to_thread.
    Bar and tick times are converted from broker server time to UTC.
    """

    def __init__(self, cfg: BrokerConfig) -> None:
        self.cfg = cfg
        self._mt5: Any = None
        self._offset: Optional[timedelta] = (
            timedelta(hours=cfg.server_utc_offset_hours)
            if cfg.server_utc_offset_hours is not None else None
        )
        self._lock = asyncio.Lock()   # the MT5 library is not thread-safe

    async def _call(self, fn_name: str, *args: Any, **kwargs: Any) -> Any:
        if self._mt5 is None:
            raise BrokerError("not connected")
        fn = getattr(self._mt5, fn_name)
        async with self._lock:
            return await asyncio.to_thread(fn, *args, **kwargs)

    async def _last_error(self) -> str:
        return str(await self._call("last_error"))

    async def connect(self) -> None:
        try:
            import MetaTrader5 as mt5  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - depends on platform
            raise BrokerError(
                "The MetaTrader5 package is not installed. It runs on Windows with the MT5 "
                "terminal: pip install MetaTrader5"
            ) from exc
        self._mt5 = mt5
        kwargs: Dict[str, Any] = {}
        if self.cfg.terminal_path:
            kwargs["path"] = self.cfg.terminal_path
        if self.cfg.login is not None:
            kwargs.update(login=self.cfg.login, password=self.cfg.password or "",
                          server=self.cfg.server or "")
        if not await self._call("initialize", **kwargs):
            err = await self._last_error()
            self._mt5 = None
            raise BrokerError(f"MT5 initialize failed: {err}")
        info = await self._call("account_info")
        if info is None:
            raise BrokerError(f"MT5 account_info failed: {await self._last_error()}")
        log.info("Connected to MT5 account %s on %s (%s), equity %.2f %s",
                 info.login, info.server, "demo" if info.trade_mode == 0 else "REAL",
                 info.equity, info.currency)

    async def shutdown(self) -> None:
        if self._mt5 is not None:
            await self._call("shutdown")
            self._mt5 = None

    async def account_equity(self) -> float:
        info = await self._call("account_info")
        if info is None:
            raise BrokerError(f"account_info failed: {await self._last_error()}")
        return float(info.equity)

    async def account_balance(self) -> float:
        info = await self._call("account_info")
        if info is None:
            raise BrokerError(f"account_info failed: {await self._last_error()}")
        return float(info.balance)

    async def _ensure_symbol(self, symbol: str) -> Any:
        if not await self._call("symbol_select", symbol, True):
            raise BrokerError(f"symbol_select({symbol}) failed: {await self._last_error()}")
        info = await self._call("symbol_info", symbol)
        if info is None:
            raise BrokerError(f"symbol_info({symbol}) failed: {await self._last_error()}")
        return info

    async def symbol_info(self, symbol: str) -> SymbolInfo:
        i = await self._ensure_symbol(symbol)
        return SymbolInfo(name=symbol, digits=int(i.digits), point=float(i.point),
                          tick_size=float(i.trade_tick_size), tick_value=float(i.trade_tick_value),
                          volume_min=float(i.volume_min), volume_max=float(i.volume_max),
                          volume_step=float(i.volume_step))

    async def _server_offset(self, symbol: str) -> timedelta:
        if self._offset is not None:
            return self._offset
        tick = await self._call("symbol_info_tick", symbol)
        if tick is None:
            raise BrokerError(f"symbol_info_tick({symbol}) failed: {await self._last_error()}")
        diff = tick.time - datetime.now(timezone.utc).timestamp()
        hours = round(diff / 3600)
        if abs(diff - hours * 3600) > 600:
            raise BrokerError("Could not detect the server UTC offset (stale tick - market "
                              "closed?). Set MT5_SERVER_UTC_OFFSET.")
        self._offset = timedelta(hours=hours)
        log.info("Detected broker server time = UTC%+d", hours)
        return self._offset

    async def get_rates(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        await self._ensure_symbol(symbol)
        tf = getattr(self._mt5, _MT5_TIMEFRAMES[timeframe])
        # start_pos=1 skips the bar that is still forming
        rates = await self._call("copy_rates_from_pos", symbol, tf, 1, count)
        if rates is None or len(rates) == 0:
            raise BrokerError(f"copy_rates_from_pos({symbol},{timeframe}) failed: "
                              f"{await self._last_error()}")
        offset = await self._server_offset(symbol)
        df = pd.DataFrame(rates)
        df.index = pd.to_datetime(df["time"], unit="s", utc=True) - offset
        df = df.rename(columns={"tick_volume": "volume"})
        return df[["open", "high", "low", "close", "volume", "spread"]].astype(float)

    async def get_tick(self, symbol: str) -> Tick:
        tick = await self._call("symbol_info_tick", symbol)
        if tick is None:
            raise BrokerError(f"symbol_info_tick({symbol}) failed: {await self._last_error()}")
        offset = await self._server_offset(symbol)
        t = datetime.fromtimestamp(tick.time, tz=timezone.utc) - offset
        return Tick(time=t, bid=float(tick.bid), ask=float(tick.ask))

    async def positions(self, symbol: Optional[str] = None) -> List[Position]:
        raw = await (self._call("positions_get", symbol=symbol) if symbol
                     else self._call("positions_get"))
        if raw is None:
            raise BrokerError(f"positions_get failed: {await self._last_error()}")
        buy = self._mt5.POSITION_TYPE_BUY
        return [
            Position(ticket=int(p.ticket), symbol=p.symbol, side=1 if p.type == buy else -1,
                     volume=float(p.volume), price_open=float(p.price_open), sl=float(p.sl),
                     tp=float(p.tp), profit=float(p.profit), comment=str(p.comment))
            for p in raw if p.magic == self.cfg.magic
        ]

    def _filling_modes(self, info: Any) -> List[int]:
        m = self._mt5
        modes = []
        if info.filling_mode & 1:
            modes.append(m.ORDER_FILLING_FOK)
        if info.filling_mode & 2:
            modes.append(m.ORDER_FILLING_IOC)
        modes.append(m.ORDER_FILLING_RETURN)
        return modes

    async def _send(self, request: Dict[str, Any], symbol: str) -> OrderResult:
        """Send a deal request with retries on requotes and a filling-mode fallback."""
        m = self._mt5
        info = await self._ensure_symbol(symbol)
        last_msg = ""
        for attempt in range(1, self.cfg.max_retries + 1):
            tick = await self._call("symbol_info_tick", symbol)
            if tick is None:
                last_msg = f"no tick: {await self._last_error()}"
                await asyncio.sleep(self.cfg.retry_delay_seconds)
                continue
            request["price"] = tick.ask if request["type"] == m.ORDER_TYPE_BUY else tick.bid
            retry = False
            for filling in self._filling_modes(info):
                request["type_filling"] = filling
                res = await self._call("order_send", request)
                if res is None:
                    last_msg = f"order_send returned None: {await self._last_error()}"
                    retry = True
                    break
                if res.retcode in (m.TRADE_RETCODE_DONE, m.TRADE_RETCODE_PLACED,
                                   m.TRADE_RETCODE_DONE_PARTIAL):
                    return OrderResult(ok=True, ticket=int(res.order), price=float(res.price),
                                       volume=float(res.volume), message=str(res.comment))
                last_msg = f"retcode {res.retcode}: {res.comment}"
                if res.retcode == _FILLING_UNSUPPORTED:
                    continue
                retry = res.retcode in _RETRYABLE
                break
            if not retry:
                break
            log.warning("%s order attempt %d failed (%s), retrying", symbol, attempt, last_msg)
            await asyncio.sleep(self.cfg.retry_delay_seconds)
        return OrderResult(ok=False, message=last_msg)

    async def market_order(self, symbol: str, side: int, volume: float, sl: float,
                           tp: float, comment: str) -> OrderResult:
        m = self._mt5
        info = await self._ensure_symbol(symbol)
        request = {
            "action": m.TRADE_ACTION_DEAL, "symbol": symbol, "volume": float(volume),
            "type": m.ORDER_TYPE_BUY if side == 1 else m.ORDER_TYPE_SELL,
            "sl": round(sl, info.digits), "tp": round(tp, info.digits),
            "deviation": self.cfg.deviation_points, "magic": self.cfg.magic,
            "comment": comment[:31], "type_time": m.ORDER_TIME_GTC,
        }
        return await self._send(request, symbol)

    async def modify_sl(self, ticket: int, sl: float, tp: float) -> bool:
        m = self._mt5
        pos = await self._call("positions_get", ticket=ticket)
        if not pos:
            return False
        info = await self._ensure_symbol(pos[0].symbol)
        res = await self._call("order_send", {
            "action": m.TRADE_ACTION_SLTP, "position": ticket, "symbol": pos[0].symbol,
            "sl": round(sl, info.digits), "tp": round(tp, info.digits), "magic": self.cfg.magic,
        })
        ok = res is not None and res.retcode == m.TRADE_RETCODE_DONE
        if not ok:
            log.error("modify_sl(%s) failed: %s", ticket,
                      res.comment if res is not None else await self._last_error())
        return ok

    async def close_position(self, ticket: int, volume: Optional[float] = None) -> OrderResult:
        m = self._mt5
        pos = await self._call("positions_get", ticket=ticket)
        if not pos:
            return OrderResult(ok=False, message=f"position {ticket} not found")
        p = pos[0]
        request = {
            "action": m.TRADE_ACTION_DEAL, "symbol": p.symbol, "position": ticket,
            "volume": float(volume or p.volume),
            "type": m.ORDER_TYPE_SELL if p.type == m.POSITION_TYPE_BUY else m.ORDER_TYPE_BUY,
            "deviation": self.cfg.deviation_points, "magic": self.cfg.magic,
            "comment": "AMD close", "type_time": m.ORDER_TIME_GTC,
        }
        return await self._send(request, p.symbol)

    async def closed_pnl(self, ticket: int) -> float:
        deals = await self._call("history_deals_get", position=ticket)
        if deals is None:
            raise BrokerError(f"history_deals_get failed: {await self._last_error()}")
        return float(sum(d.profit + d.commission + d.swap for d in deals))


# ---------------------------------------------------------------------- paper broker

_TF_MINUTES = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}


@dataclass
class _PaperPos:
    ticket: int
    symbol: str
    side: int
    volume: float
    price_open: float
    sl: float
    tp: float
    comment: str
    open_time: datetime


@dataclass
class PaperDeal:
    ticket: int
    symbol: str
    side: int
    volume: float
    price_open: float
    price_close: float
    pnl: float
    reason: str
    comment: str
    open_time: datetime
    close_time: datetime


class PaperBroker(Broker):
    """In-memory broker for replay and dry runs.

    Prices come from historical bars (treated as BID); ask = bid + spread. Call
    `advance(ts)` after each bar closes: it moves the clock and fills stops and targets
    inside that bar. If a bar touches both, the stop is assumed to fill first.
    """

    def __init__(self, balance: float = 10_000.0, spread_pips: float = 0.8,
                 commission_per_lot: float = 0.0, base_timeframe: str = "M5",
                 symbols: Optional[Dict[str, SymbolInfo]] = None) -> None:
        self.balance = balance
        self.spread_pips = spread_pips
        self.commission_per_lot = commission_per_lot
        self.base_timeframe = base_timeframe
        self.data: Dict[str, pd.DataFrame] = {}
        self.infos: Dict[str, SymbolInfo] = dict(symbols or {})
        self.now: Optional[pd.Timestamp] = None     # open time of the last closed bar
        self._pos: Dict[int, _PaperPos] = {}
        self.deals: List[PaperDeal] = []
        self._next_ticket = 1

    # ---- setup / clock
    def load_bars(self, symbol: str, bars: pd.DataFrame) -> None:
        df = bars[["open", "high", "low", "close"]].astype(float).sort_index()
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        self.data[symbol] = df
        self.infos.setdefault(symbol, default_symbol_info(symbol))

    def _bar(self, symbol: str, ts: pd.Timestamp) -> Optional[pd.Series]:
        df = self.data.get(symbol)
        if df is None or ts not in df.index:
            return None
        return df.loc[ts]

    def _spread(self, symbol: str) -> float:
        return self.spread_pips * pip_size(symbol)

    def advance(self, ts: pd.Timestamp) -> None:
        """Mark bar `ts` as closed and process stops and targets inside it."""
        self.now = ts
        for pos in list(self._pos.values()):
            bar = self._bar(pos.symbol, ts)
            if bar is None or pos.open_time >= ts:
                continue
            spr = self._spread(pos.symbol)
            if pos.side == 1:   # long closes on the bid
                lo, hi, op = bar["low"], bar["high"], bar["open"]
                hit_sl = pos.sl > 0 and lo <= pos.sl
                hit_tp = pos.tp > 0 and hi >= pos.tp
                sl_px = min(op, pos.sl) if hit_sl else 0.0
                tp_px = max(op, pos.tp) if hit_tp else 0.0
            else:               # short closes on the ask
                lo, hi, op = bar["low"] + spr, bar["high"] + spr, bar["open"] + spr
                hit_sl = pos.sl > 0 and hi >= pos.sl
                hit_tp = pos.tp > 0 and lo <= pos.tp
                sl_px = max(op, pos.sl) if hit_sl else 0.0
                tp_px = min(op, pos.tp) if hit_tp else 0.0
            if hit_sl:
                self._close(pos, pos.volume, sl_px, "sl")
            elif hit_tp:
                self._close(pos, pos.volume, tp_px, "tp")

    def _pnl(self, pos: _PaperPos, volume: float, price: float) -> float:
        info = self.infos[pos.symbol]
        return (price - pos.price_open) * pos.side / info.tick_size * info.tick_value * volume

    def _close(self, pos: _PaperPos, volume: float, price: float, reason: str) -> None:
        pnl = self._pnl(pos, volume, price) - self.commission_per_lot * volume
        self.balance += pnl
        close_time = (self.now or pos.open_time)
        self.deals.append(PaperDeal(pos.ticket, pos.symbol, pos.side, volume, pos.price_open,
                                    price, pnl, reason, pos.comment, pos.open_time, close_time))
        remaining = round(pos.volume - volume, 8)
        if remaining <= 0:
            del self._pos[pos.ticket]
        else:
            pos.volume = remaining

    # ---- Broker interface
    async def connect(self) -> None:
        log.info("Paper broker ready, balance %.2f", self.balance)

    async def shutdown(self) -> None:
        return None

    async def account_balance(self) -> float:
        return self.balance

    async def account_equity(self) -> float:
        floating = 0.0
        for pos in self._pos.values():
            tick = await self.get_tick(pos.symbol)
            floating += self._pnl(pos, pos.volume, tick.bid if pos.side == 1 else tick.ask)
        return self.balance + floating

    async def symbol_info(self, symbol: str) -> SymbolInfo:
        return self.infos.setdefault(symbol, default_symbol_info(symbol))

    async def get_rates(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        if symbol not in self.data or self.now is None:
            raise BrokerError(f"no paper data for {symbol}")
        df = self.data[symbol].loc[: self.now]
        if timeframe != self.base_timeframe:
            minutes = _TF_MINUTES[timeframe]
            rule = "1D" if minutes == 1440 else f"{minutes}min"
            res = df.resample(rule, label="left", closed="left").agg(
                {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
            # drop the higher-timeframe bar that hasn't finished yet
            bar_end = self.now + pd.Timedelta(minutes=_TF_MINUTES[self.base_timeframe])
            res = res[res.index + pd.Timedelta(minutes=minutes) <= bar_end]
            df = res
        return df.iloc[-count:].copy()

    async def get_tick(self, symbol: str) -> Tick:
        if symbol not in self.data or self.now is None:
            raise BrokerError(f"no paper data for {symbol}")
        df = self.data[symbol].loc[: self.now]
        if df.empty:
            raise BrokerError(f"no paper price for {symbol} yet")
        bid = float(df["close"].iat[-1])
        return Tick(time=df.index[-1].to_pydatetime(), bid=bid, ask=bid + self._spread(symbol))

    async def positions(self, symbol: Optional[str] = None) -> List[Position]:
        out = []
        for p in self._pos.values():
            if symbol and p.symbol != symbol:
                continue
            tick = await self.get_tick(p.symbol)
            px = tick.bid if p.side == 1 else tick.ask
            out.append(Position(p.ticket, p.symbol, p.side, p.volume, p.price_open, p.sl,
                                p.tp, self._pnl(p, p.volume, px), p.comment))
        return out

    async def market_order(self, symbol: str, side: int, volume: float, sl: float,
                           tp: float, comment: str) -> OrderResult:
        if volume <= 0:
            return OrderResult(ok=False, message="volume must be positive")
        tick = await self.get_tick(symbol)
        price = tick.ask if side == 1 else tick.bid
        if (side == 1 and not sl < price) or (side == -1 and not sl > price):
            return OrderResult(ok=False, message="invalid stop loss for direction")
        ticket = self._next_ticket
        self._next_ticket += 1
        assert self.now is not None
        self._pos[ticket] = _PaperPos(ticket, symbol, side, volume, price, sl, tp, comment,
                                      self.now)
        return OrderResult(ok=True, ticket=ticket, price=price, volume=volume)

    async def modify_sl(self, ticket: int, sl: float, tp: float) -> bool:
        pos = self._pos.get(ticket)
        if pos is None:
            return False
        tick = await self.get_tick(pos.symbol)
        if (pos.side == 1 and sl >= tick.bid) or (pos.side == -1 and sl <= tick.ask):
            return False   # a broker would reject a stop on the wrong side of price
        pos.sl, pos.tp = sl, tp
        return True

    async def close_position(self, ticket: int, volume: Optional[float] = None) -> OrderResult:
        pos = self._pos.get(ticket)
        if pos is None:
            return OrderResult(ok=False, message=f"position {ticket} not found")
        tick = await self.get_tick(pos.symbol)
        price = tick.bid if pos.side == 1 else tick.ask
        vol = volume or pos.volume
        self._close(pos, vol, price, "manual")
        return OrderResult(ok=True, ticket=ticket, price=price, volume=vol)

    async def closed_pnl(self, ticket: int) -> float:
        return float(sum(d.pnl for d in self.deals if d.ticket == ticket))


def default_symbol_info(symbol: str) -> SymbolInfo:
    """Typical 5-digit FX contract (100k units) for a USD account.

    tick_value is exact for XXXUSD pairs; for other quote currencies it is only an
    approximation - pass real SymbolInfo values for those.
    """
    jpy = symbol.upper().endswith("JPY")
    tick = 0.001 if jpy else 0.00001
    return SymbolInfo(name=symbol, digits=3 if jpy else 5, point=tick, tick_size=tick,
                      tick_value=1.0 if not jpy else 0.67, volume_min=0.01,
                      volume_max=100.0, volume_step=0.01)


# ---------------------------------------------------------------------- trade manager

@dataclass
class Trade:
    trade_id: str
    symbol: str
    side: int
    entry: float
    stop: float
    tp1: float
    tp2: float
    volume: float
    risk_amount: float
    opened_at: str
    legs: Dict[str, int] = field(default_factory=dict)   # "A"/"B" -> ticket
    be_done: bool = False
    closed: bool = False
    pnl: float = 0.0
    closed_at: str = ""

    @property
    def r_multiple(self) -> float:
        return self.pnl / self.risk_amount if self.risk_amount else 0.0


def _round_down(volume: float, step: float) -> float:
    return round(math.floor(volume / step + 1e-9) * step, 8)


class TradeManager:
    """Opens two-leg trades, moves the stop to break-even after TP1, trails, and keeps
    trade state on disk so a restarted bot can pick up its open trades."""

    def __init__(self, broker: Broker, cfg: AppConfig, state_path: Optional[Path] = None) -> None:
        self.broker = broker
        self.cfg = cfg
        self.state_path = state_path
        self.trades: Dict[str, Trade] = {}
        self.history: List[Trade] = []
        self._load()

    # ---- persistence
    def _load(self) -> None:
        if self.state_path is None or not self.state_path.exists():
            return
        try:
            raw = json.loads(self.state_path.read_text())
            self.trades = {k: Trade(**v) for k, v in raw.get("open", {}).items()}
            log.info("Recovered %d open trade(s) from %s", len(self.trades), self.state_path)
        except (OSError, ValueError, TypeError) as exc:
            log.error("Could not read trade state %s: %s", self.state_path, exc)

    def _save(self) -> None:
        if self.state_path is None:
            return
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"open": {k: asdict(v) for k, v in self.trades.items()}},
                                      indent=2))
            tmp.replace(self.state_path)
        except OSError as exc:
            log.error("Could not save trade state: %s", exc)

    # ---- queries
    @property
    def open_trade_count(self) -> int:
        return len(self.trades)

    def has_open_trade(self, symbol: str) -> bool:
        return any(t.symbol == symbol for t in self.trades.values())

    # ---- actions
    async def open_trade(self, sig: Signal, volume: float, info: SymbolInfo,
                         risk_amount: float, now: datetime) -> Optional[Trade]:
        """Place the legs for a signal. Returns the Trade, or None if nothing filled."""
        part = _round_down(volume * self.cfg.strategy.tp1_fraction, info.volume_step)
        rest = round(volume - part, 8)
        if part >= info.volume_min and rest >= info.volume_min:
            plan = [("A", part, sig.tp1), ("B", rest, sig.tp2)]
        else:
            plan = [("B", volume, sig.tp2)]
        trade_id = f"{sig.symbol}{now:%y%m%d%H%M}"
        trade = Trade(trade_id=trade_id, symbol=sig.symbol, side=sig.side, entry=0.0,
                      stop=sig.stop_loss, tp1=sig.tp1, tp2=sig.tp2, volume=0.0,
                      risk_amount=risk_amount, opened_at=now.isoformat())
        fills = []
        for leg, vol, tp in plan:
            res = await self.broker.market_order(sig.symbol, sig.side, vol, sig.stop_loss, tp,
                                                 f"AMD:{trade_id}:{leg}")
            if res.ok:
                trade.legs[leg] = res.ticket
                trade.volume += vol
                fills.append((res.price, vol))
                log.info("%s leg %s filled: %.2f lots @ %.5f (ticket %d)", trade_id, leg, vol,
                         res.price, res.ticket)
            else:
                log.error("%s leg %s failed: %s", trade_id, leg, res.message)
        if not fills:
            return None
        trade.entry = sum(p * v for p, v in fills) / sum(v for _, v in fills)
        self.trades[trade_id] = trade
        self._save()
        return trade

    async def _move_to_breakeven(self, trade: Trade, ticket: int, pos: Position) -> None:
        offset = self.cfg.strategy.be_offset_pips * pip_size(trade.symbol)
        be = trade.entry + trade.side * offset
        better = be > pos.sl if trade.side == 1 else (pos.sl == 0 or be < pos.sl)
        if not better:
            trade.be_done = True
            return
        if await self.broker.modify_sl(ticket, be, pos.tp):
            log.info("%s stop moved to break-even %.5f", trade.trade_id, be)
            trade.be_done = True
            return
        # price is already through break-even: take what's left at market
        tick = await self.broker.get_tick(trade.symbol)
        px = tick.bid if trade.side == 1 else tick.ask
        if (trade.side == 1 and px <= be) or (trade.side == -1 and px >= be):
            log.warning("%s price beyond break-even, closing the runner", trade.trade_id)
            await self.broker.close_position(ticket)
            trade.be_done = True

    async def _trail(self, trade: Trade, ticket: int, pos: Position) -> None:
        dist = self.cfg.strategy.trail_pips * pip_size(trade.symbol)
        tick = await self.broker.get_tick(trade.symbol)
        if trade.side == 1:
            new_sl = tick.bid - dist
            if new_sl > pos.sl:
                await self.broker.modify_sl(ticket, new_sl, pos.tp)
        else:
            new_sl = tick.ask + dist
            if pos.sl == 0 or new_sl < pos.sl:
                await self.broker.modify_sl(ticket, new_sl, pos.tp)

    async def manage(self, now: datetime) -> List[Trade]:
        """Run once per loop. Returns trades that closed during this call."""
        if not self.trades:
            return []
        live = {p.ticket: p for p in await self.broker.positions()}
        closed: List[Trade] = []
        changed = False
        for trade in list(self.trades.values()):
            open_legs = {leg: t for leg, t in trade.legs.items() if t in live}
            if not open_legs:
                trade.pnl = 0.0
                for t in trade.legs.values():
                    trade.pnl += await self.broker.closed_pnl(t)
                trade.closed, trade.closed_at = True, now.isoformat()
                del self.trades[trade.trade_id]
                self.history.append(trade)
                closed.append(trade)
                changed = True
                log.info("%s closed: P&L %.2f (%.2fR)", trade.trade_id, trade.pnl,
                         trade.r_multiple)
                continue
            runner = open_legs.get("B")
            if runner is None:
                continue
            pos = live[runner]
            if not trade.be_done:
                tp1_hit = "A" in trade.legs and "A" not in open_legs
                if "A" not in trade.legs:   # single leg: watch price for TP1
                    tick = await self.broker.get_tick(trade.symbol)
                    px = tick.bid if trade.side == 1 else tick.ask
                    tp1_hit = px >= trade.tp1 if trade.side == 1 else px <= trade.tp1
                if tp1_hit:
                    await self._move_to_breakeven(trade, runner, pos)
                    changed = True
            elif self.cfg.strategy.trail_after_tp1:
                await self._trail(trade, runner, pos)
        if changed:
            self._save()
        return closed

    async def close_all(self, reason: str) -> None:
        """Close every position this bot owns (circuit breaker / rollover)."""
        for pos in await self.broker.positions():
            res = await self.broker.close_position(pos.ticket)
            if res.ok:
                log.warning("Closed %s ticket %d (%s)", pos.symbol, pos.ticket, reason)
            else:
                log.error("Failed to close ticket %d: %s", pos.ticket, res.message)
