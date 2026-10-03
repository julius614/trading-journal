"""Async event loop for the triangular stat-arb bot (paper replay or live MT5).

Each loop: clock -> daily reset -> Prop Shield breaker -> new aligned M5 bar(s) ->
Kalman update -> exit checks for an open basket -> entry checks (news/rollover blackout,
|Z| > entry, fee gate) -> three-leg order.

    python -m bots.statarb_3leg.main --live                  # MT5 (demo first!)
    python -m bots.statarb_3leg.main --paper EURUSD=a.csv GBPUSD=b.csv EURGBP=c.csv
"""
from __future__ import annotations

import argparse
import asyncio
import math
import signal
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import pandas as pd
from loguru import logger

from .config import AppConfig, load_config
from .data_fetcher import TriangleFeed
from .execution import Basket, Broker, BrokerError, MT5Broker, MultiLegExecutor
from .fee_gate import evaluate, mids_from_ticks
from .kalman_statarb import KalmanOutput, LocalLevelKalman, deviation_pips
from .risk_manager import NewsCalendar, RiskManager, balance_legs


@dataclass(frozen=True)
class GateRecord:
    time: pd.Timestamp
    z: float
    direction: int
    passed: bool
    reason: str
    expected_pips: float
    cost_pips: float
    ratio: float


class StatArbBot:
    """Triangle stat-arb state machine. Broker-agnostic (paper or MT5)."""

    def __init__(self, cfg: AppConfig, broker: Broker, news: Optional[NewsCalendar] = None,
                 state_path: Optional[Path] = None) -> None:
        self.cfg = cfg
        self.broker = broker
        self.feed = TriangleFeed(broker, cfg)
        self.risk = RiskManager(cfg.risk, cfg.filters, news)
        self.executor = MultiLegExecutor(broker, cfg, state_path,
                                         retry_delay=0.5 if isinstance(broker, MT5Broker) else 0.0)
        s = cfg.strategy
        self.kalman = LocalLevelKalman(s.kalman_q_ratio, s.r_halflife_bars, s.warmup_bars,
                                       s.clip_sigma)
        self.last_bar: Optional[pd.Timestamp] = None
        self.last_output: Optional[KalmanOutput] = None
        self.gate_log: List[GateRecord] = []
        self.blocked: Counter = Counter()
        self.deviation_pips: List[float] = []
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def warmup(self) -> None:
        """Feed recent history to the filter without trading (live start-up)."""
        bars = await self.feed.closed_bars(self.cfg.strategy.history_bars)
        for ts, row in bars.iterrows():
            self.last_output = self.kalman.update(row["spread"])
            self.last_bar = ts
        logger.info("Warm-up: {} bars, filter warm={}, last bar {}", len(bars), self.kalman.warm,
                    self.last_bar)

    async def step(self, now: datetime) -> None:
        equity = await self.broker.account_equity()
        self.risk.update_day(now, equity)
        if self.risk.check_breaker(equity) and self.executor.basket is not None:
            await self.executor.close_basket("prop shield", now)
        # keep feeding the filter even while locked; entries are blocked in entry_block()
        bars = await self.feed.closed_bars(count=50)
        if self.last_bar is not None:
            bars = bars[bars.index > self.last_bar]
        for ts, row in bars.iterrows():
            out = self.kalman.update(row["spread"])
            self.last_bar, self.last_output = ts, out
            await self.on_bar(ts, row, out, now)

    async def on_bar(self, ts: pd.Timestamp, row: pd.Series, out: KalmanOutput,
                     now: datetime) -> None:
        s = self.cfg.strategy
        z = out.z
        if out.warm:
            self.deviation_pips.append(deviation_pips(out.deviation, row["EURGBP"]))
        b = self.executor.basket
        if b is not None:
            b.bars_held += 1
            reason = self._exit_reason(b, z)
            if reason:
                await self.executor.close_basket(reason, now, z)
            return
        if not out.warm or not math.isfinite(z) or abs(z) < s.entry_z:
            return
        direction = 1 if z < 0 else -1          # Z < -2: spread cheap -> long spread
        blocked, why = self.risk.entry_block(now)
        if blocked:
            self.blocked[why.split(":")[0]] += 1
            logger.info("Signal z={:+.2f} at {} blocked: {}", z, ts, why)
            return
        ticks = await self.feed.ticks()
        mids = mids_from_ticks(ticks)
        infos = {sym: await self.broker.symbol_info(self.cfg.broker_symbol(sym))
                 for sym in ("EURUSD", "GBPUSD", "EURGBP")}
        equity = await self.broker.account_equity()
        plans = balance_legs(direction, equity, mids, infos, self.cfg.risk)
        lots = {p.symbol: p.lots for p in plans} or None
        gate = evaluate(out.deviation, ticks, self.cfg.filters, self.cfg.risk.account_currency, lots)
        self.gate_log.append(GateRecord(ts, z, direction, gate.passed and bool(plans), gate.reason,
                                        gate.expected_reversion_pips, gate.total_cost_pips,
                                        gate.ratio))
        if not plans:
            logger.warning("Signal z={:+.2f}: equity too small for minimum lots", z)
            return
        if not gate.passed:
            logger.info("Signal z={:+.2f} at {} rejected by fee gate: {} (edge {:.2f} vs cost "
                        "{:.2f} pips)", z, ts, gate.reason, gate.expected_reversion_pips,
                        gate.total_cost_pips)
            return
        await self.executor.open_basket(plans, direction, z, gate, now)

    def _exit_reason(self, b: Basket, z: float) -> Optional[str]:
        s = self.cfg.strategy
        if s.max_hold_bars is not None and b.bars_held >= s.max_hold_bars:
            return "max hold"
        if not math.isfinite(z):
            return None
        if (b.direction == 1 and z >= -s.exit_z) or (b.direction == -1 and z <= s.exit_z):
            return "reverted"
        if s.stop_z_extra is not None:
            # relative to entry: a big dislocation entered at Z=17 that falls to 6 is
            # reverting, not failing; stop only if it widens past |entry Z| + extra
            limit = abs(b.entry_z) + s.stop_z_extra
            if (b.direction == 1 and z <= -limit) or (b.direction == -1 and z >= limit):
                return "stop z"
        return None

    async def run_live(self) -> None:
        await self.broker.connect()
        try:
            await self.warmup()
            while not self._stop.is_set():
                try:
                    await self.step(datetime.now(timezone.utc))
                except BrokerError as exc:
                    logger.error("Broker error: {}", exc)
                except Exception:   # keep running; an open basket is managed next loop
                    logger.exception("Unexpected error in the main loop")
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.cfg.poll_seconds)
                except asyncio.TimeoutError:
                    pass
        finally:
            await self.broker.shutdown()
            logger.info("Bot stopped")


def setup_logging(log_dir: str, level: str = "INFO") -> None:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(sys.stdout, level=level.upper(),
               format="{time:YYYY-MM-DD HH:mm:ss} {level:<8} {message}")
    logger.add(Path(log_dir) / "bot.log", level="DEBUG", rotation="10 MB", retention=10)


def load_news(cfg: AppConfig, live: bool) -> NewsCalendar:
    if cfg.news_csv:
        cal = NewsCalendar.from_csv(cfg.news_csv)
    else:
        cal = NewsCalendar()
    if live and cfg.require_news_calendar:
        last = cal.last_event_time()
        if last is None or last < datetime.now(timezone.utc):
            raise SystemExit("No current news calendar. Set STATARB_NEWS_CSV to a CSV of this "
                             "week's events (see bots/statarb_3leg/news_calendar.example.csv).")
    return cal


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="EURUSD/GBPUSD/EURGBP stat-arb bot")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--live", action="store_true", help="trade through MetaTrader 5")
    mode.add_argument("--paper", nargs=3, metavar="SYMBOL=CSV", help="replay three M5 CSVs")
    p.add_argument("--log-level", default="INFO")
    return p.parse_args(argv)


async def _amain(args: argparse.Namespace) -> None:
    cfg = load_config()
    setup_logging(cfg.log_dir, args.log_level)
    if args.paper:
        from .backtest import run_replay
        await run_replay(cfg, dict(x.split("=", 1) for x in args.paper),
                         news=load_news(cfg, live=False))
        return
    bot = StatArbBot(cfg, MT5Broker(cfg.broker), load_news(cfg, live=True),
                     Path(cfg.data_dir) / "basket_state.json")
    loop = asyncio.get_running_loop()
    for name in ("SIGINT", "SIGTERM"):
        try:
            loop.add_signal_handler(getattr(signal, name), bot.stop)
        except (NotImplementedError, AttributeError):   # Windows: Ctrl+C raises instead
            pass
    await bot.run_live()


def main(argv: Optional[List[str]] = None) -> None:
    try:
        asyncio.run(_amain(parse_args(argv)))
    except KeyboardInterrupt:
        logger.info("Interrupted")


if __name__ == "__main__":
    main()
