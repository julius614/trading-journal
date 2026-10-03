"""Main event loop for the AMD session-sweep bot.

Each loop:  clock -> daily reset -> Prop Shield breaker -> rollover -> new closed bar per
symbol -> strategy -> risk checks -> orders -> trade management.

Run (from the repo root):
    python -m bots.amd_fx.main --paper --replay EURUSD=data/EURUSD_M5.csv   # replay
    python -m bots.amd_fx.main --live                                       # MT5 (demo first!)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from .config import AppConfig, load_config, pip_size
from .data_fetcher import DataFetcher
from .execution import Broker, BrokerError, MT5Broker, Trade, TradeManager
from .risk_manager import RiskManager, position_size
from .strategy_amd import AMDStrategy, Signal

log = logging.getLogger("amd_fx")


class Bot:
    """Wires data, strategy, risk and execution together. Broker-agnostic."""

    def __init__(self, cfg: AppConfig, broker: Broker, state_path: Optional[Path] = None) -> None:
        self.cfg = cfg
        self.broker = broker
        self.data = DataFetcher(broker, cfg)
        self.risk = RiskManager(cfg.risk, cfg.session)
        self.trades = TradeManager(broker, cfg, state_path)
        self.strategies: Dict[str, AMDStrategy] = {
            s: AMDStrategy(s, cfg) for s in cfg.strategy.symbols
        }
        self._last_bar: Dict[str, pd.Timestamp] = {}
        self._flattened_for: Optional[str] = None
        self.signals: List[Signal] = []
        self.closed_trades: List[Trade] = []
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def step(self, now: datetime) -> None:
        """One pass of the state machine at time `now` (UTC)."""
        equity = await self.broker.account_equity()
        self.risk.update_day(now, equity)

        # 1. Prop Shield: daily loss breaker (realized + unrealized via equity)
        if self.risk.check_breaker(equity):
            day_key = f"breaker-{self.risk.state.trading_day}"
            if self.cfg.risk.flatten_on_breaker and self._flattened_for != day_key:
                await self.trades.close_all(self.risk.state.lock_reason)
                self._flattened_for = day_key
            self.closed_trades += await self.trades.manage(now)
            return

        # 2. rollover window: optionally flatten; entries are blocked in can_open()
        if self.risk.in_rollover(now) and self.cfg.risk.flatten_at_rollover:
            day_key = f"rollover-{now:%Y-%m-%d}"
            if self._flattened_for != day_key and self.trades.open_trade_count:
                await self.trades.close_all("rollover window")
                self._flattened_for = day_key

        # 3. new closed bars -> strategy -> execution
        for symbol, strat in self.strategies.items():
            try:
                bars = await self.data.closed_bars(symbol)
            except BrokerError as exc:
                log.error("%s: bars unavailable: %s", symbol, exc)
                continue
            if bars.empty or self._last_bar.get(symbol) == bars.index[-1]:
                continue
            self._last_bar[symbol] = bars.index[-1]
            atr_value = await self.data.current_atr(symbol, bars.index[-1].date())
            sig = strat.on_bar(bars, atr_value)
            if sig is not None:
                self.signals.append(sig)
                await self.execute_signal(sig, now)

        # 4. manage open trades (TP1 -> break-even, trailing, closed-trade bookkeeping)
        self.closed_trades += await self.trades.manage(now)

    async def execute_signal(self, sig: Signal, now: datetime) -> Optional[Trade]:
        """Run risk checks, size the trade, and place it."""
        if self.trades.has_open_trade(sig.symbol):
            log.info("%s: already in a trade, signal ignored", sig.symbol)
            return None
        tick = await self.data.latest_tick(sig.symbol)
        pip = pip_size(sig.symbol)
        ok, reason = self.risk.can_open(now, self.trades.open_trade_count, tick.spread() / pip)
        if not ok:
            log.warning("%s signal blocked: %s", sig.symbol, reason)
            return None
        entry = tick.ask if sig.side == 1 else tick.bid
        # re-validate against the live price: stop on the right side, TP1 still ahead
        if sig.side == 1 and not (sig.stop_loss < entry < sig.tp1):
            log.warning("%s long no longer valid at %.5f (SL %.5f, TP1 %.5f)", sig.symbol,
                        entry, sig.stop_loss, sig.tp1)
            return None
        if sig.side == -1 and not (sig.tp1 < entry < sig.stop_loss):
            log.warning("%s short no longer valid at %.5f (SL %.5f, TP1 %.5f)", sig.symbol,
                        entry, sig.stop_loss, sig.tp1)
            return None
        info = await self.broker.symbol_info(sig.symbol)
        equity = await self.broker.account_equity()
        lots = position_size(equity, self.cfg.risk.risk_per_trade, entry, sig.stop_loss,
                             info.tick_size, info.tick_value, info.volume_step,
                             info.volume_min, info.volume_max)
        if lots <= 0:
            log.warning("%s: minimum lot would risk more than %.2f%% - skipped", sig.symbol,
                        self.cfg.risk.risk_per_trade * 100)
            return None
        risk_amount = abs(entry - sig.stop_loss) / info.tick_size * info.tick_value * lots
        log.info("%s %s %.2f lots, risk %.2f (%.2f%% of %.2f)", sig.symbol, sig.direction,
                 lots, risk_amount, risk_amount / equity * 100, equity)
        return await self.trades.open_trade(sig, lots, info, risk_amount, now)

    async def run_live(self) -> None:
        """Poll the broker until stopped."""
        await self.broker.connect()
        try:
            while not self._stop.is_set():
                try:
                    await self.step(datetime.now(timezone.utc))
                except BrokerError as exc:
                    log.error("Broker error: %s", exc)
                except Exception:  # keep the loop alive; positions have broker-side SL/TP
                    log.exception("Unexpected error in the main loop")
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.cfg.poll_seconds)
                except asyncio.TimeoutError:
                    pass
        finally:
            await self.broker.shutdown()
            log.info("Bot stopped")


def setup_logging(log_dir: str, level: str = "INFO") -> None:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    fmt = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO), format=fmt,
        handlers=[logging.StreamHandler(sys.stdout),
                  logging.FileHandler(Path(log_dir) / "bot.log", encoding="utf-8")],
        force=True,
    )


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="AMD session-sweep FX bot")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--live", action="store_true", help="trade through MetaTrader 5")
    mode.add_argument("--paper", action="store_true", help="replay CSV data on a paper broker")
    p.add_argument("--replay", nargs="+", default=[], metavar="SYMBOL=CSV",
                   help="paper mode: historical M5/M1 bars per symbol")
    p.add_argument("--log-level", default="INFO")
    return p.parse_args(argv)


async def _amain(args: argparse.Namespace) -> None:
    cfg = load_config()
    setup_logging(cfg.log_dir, args.log_level)
    if args.paper:
        from .backtest import run_replay   # local import: backtest imports this module
        if not args.replay:
            raise SystemExit("--paper needs --replay SYMBOL=CSV ...")
        await run_replay(cfg, dict(item.split("=", 1) for item in args.replay))
        return
    bot = Bot(cfg, MT5Broker(cfg.broker), Path(cfg.data_dir) / "trades_state.json")
    loop = asyncio.get_running_loop()
    for sig_name in ("SIGINT", "SIGTERM"):
        try:
            loop.add_signal_handler(getattr(signal, sig_name), bot.stop)
        except (NotImplementedError, AttributeError):   # Windows: Ctrl+C raises instead
            pass
    await bot.run_live()


def main(argv: Optional[List[str]] = None) -> None:
    try:
        asyncio.run(_amain(parse_args(argv)))
    except KeyboardInterrupt:
        log.info("Interrupted")


if __name__ == "__main__":
    main()
