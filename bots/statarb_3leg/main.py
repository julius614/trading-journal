"""Async event loop for the 2-leg H1 pairs bot (paper replay or live MT5).

Each loop: clock -> daily reset -> Prop Shield breaker -> new aligned H1 bar(s) ->
Kalman hedge-ratio update -> exit checks for an open basket -> entry checks (news/rollover
blackout, |Z| > entry, rolling ADF + half-life gate, fee gate) -> two-leg order.

    python -m bots.statarb_3leg.main --live                      # MT5 (demo first!)
    python -m bots.statarb_3leg.main --paper AUDUSD=a.csv NZDUSD=b.csv
"""
from __future__ import annotations

import argparse
import asyncio
import math
import signal
import sys
from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import pandas as pd
from loguru import logger

import numpy as np

from .cointegration import stationarity_gate
from .config import AppConfig, load_config
from .data_fetcher import PairFeed
from .execution import Basket, Broker, BrokerError, MT5Broker, MultiLegExecutor
from .fee_gate import evaluate, mids_from_ticks
from .kalman_statarb import HedgeOutput, KalmanHedgeRatio, spread_pips
from .risk_manager import NewsCalendar, RiskManager, balance_legs, weekend_phase


@dataclass(frozen=True)
class GateRecord:
    time: pd.Timestamp
    z: float
    direction: int
    beta: float
    passed: bool
    reason: str
    expected_pips: float
    cost_pips: float
    ratio: float


class PairsBot:
    """Pairs-trading state machine. Broker-agnostic (paper or MT5)."""

    def __init__(self, cfg: AppConfig, broker: Broker, news: Optional[NewsCalendar] = None,
                 state_path: Optional[Path] = None) -> None:
        self.cfg = cfg
        self.broker = broker
        self.feed = PairFeed(broker, cfg)
        self.risk = RiskManager(cfg.risk, cfg.filters, news)
        self.executor = MultiLegExecutor(broker, cfg, state_path,
                                         retry_delay=0.5 if isinstance(broker, MT5Broker) else 0.0)
        s = cfg.strategy
        self.kalman = KalmanHedgeRatio(s.q_beta, s.q_alpha, s.r_halflife_bars, s.warmup_bars,
                                       s.clip_sigma)
        self.last_bar: Optional[pd.Timestamp] = None
        self.last_output: Optional[HedgeOutput] = None
        self.gate_log: List[GateRecord] = []
        self.blocked: Counter = Counter()
        self.spread_pips: List[float] = []
        self.betas: List[float] = []
        self.window_y: deque = deque(maxlen=s.coint_window)
        self.window_x: deque = deque(maxlen=s.coint_window)
        self.coint_checks: List[tuple] = []          # (time, passed, pvalue, half_life)
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def warmup(self) -> None:
        """Feed recent history to the filter without trading (live start-up)."""
        bars = await self.feed.closed_bars(self.cfg.strategy.history_bars)
        for ts, row in bars.iterrows():
            self.last_output = self.kalman.update(row["log_y"], row["log_x"])
            self.window_y.append(row["log_y"])
            self.window_x.append(row["log_x"])
            self.last_bar = ts
        logger.info("Warm-up: {} bars, filter warm={}, beta={:.3f}, last bar {}", len(bars),
                    self.kalman.warm, self.kalman.beta, self.last_bar)

    async def step(self, now: datetime) -> None:
        equity = await self.broker.account_equity()
        self.risk.update_day(now, equity)
        if self.risk.check_breaker(equity) and self.executor.basket is not None:
            await self.executor.close_basket("prop shield", now)
        broken = await self.executor.broken_leg()
        if broken is not None:
            logger.error("{} leg is no longer open (emergency stop or manual close) - closing "
                         "the other leg", broken)
            await self.executor.close_basket("leg closed outside bot", now)
        if weekend_phase(now, self.cfg.strategy) == "close" and self.executor.basket is not None:
            await self.executor.close_basket("weekend", now)
        # keep feeding the filter even while locked; entries are blocked in entry_block()
        bars = await self.feed.closed_bars(count=50)
        if self.last_bar is not None:
            bars = bars[bars.index > self.last_bar]
        for ts, row in bars.iterrows():
            out = self.kalman.update(row["log_y"], row["log_x"])
            self.window_y.append(row["log_y"])
            self.window_x.append(row["log_x"])
            self.last_bar, self.last_output = ts, out
            await self.on_bar(ts, row, out, now)

    async def on_bar(self, ts: pd.Timestamp, row: pd.Series, out: HedgeOutput,
                     now: datetime) -> None:
        s = self.cfg.strategy
        y, x = self.cfg.y, self.cfg.x
        z = out.z
        if out.warm:
            self.spread_pips.append(spread_pips(out.spread, row[y]))
            self.betas.append(out.beta)
        b = self.executor.basket
        if b is not None:
            b.bars_held += 1
            reason = self._exit_reason(b, z)
            if reason in ("reverted", "max hold") and self._news_exit_hold(now):
                logger.info("Exit '{}' deferred: inside the news window", reason)
                return
            if reason:
                await self.executor.close_basket(reason, now, z)
            return
        if not out.warm or not math.isfinite(z) or abs(z) < s.entry_z:
            return
        direction = 1 if z < 0 else -1          # Z < -2: y cheap vs x -> long spread
        blocked, why = self.risk.entry_block(now)
        if not blocked and weekend_phase(now, s) is not None:
            blocked, why = True, "weekend: flat before the weekend"
        if blocked:
            self.blocked[why.split(":")[0]] += 1
            logger.info("Signal z={:+.2f} at {} blocked: {}", z, ts, why)
            return
        if s.use_coint_gate:
            if len(self.window_y) < s.coint_window:
                self.blocked["cointegration window filling"] += 1
                return
            check = stationarity_gate(np.fromiter(self.window_y, float),
                                      np.fromiter(self.window_x, float),
                                      s.coint_max_pvalue, s.coint_max_half_life)
            self.coint_checks.append((ts, check.passed, check.pvalue, check.half_life))
            if not check.passed:
                self.blocked["cointegration"] += 1
                logger.info("Signal z={:+.2f} at {} blocked: {}", z, ts, check.reason)
                return
        ticks = await self.feed.ticks()
        mids = mids_from_ticks(ticks)
        infos = {sym: await self.broker.symbol_info(self.cfg.broker_symbol(sym))
                 for sym in self.cfg.pair}
        equity = await self.broker.account_equity()
        stop_move = (s.stop_z_extra * out.std if s.stop_z_extra is not None
                     else 2.0 * out.std)   # fixed-risk sizing without a Z stop: assume 2 sigma
        plans = balance_legs(direction, equity, mids, infos, self.cfg.risk, y, x, out.beta,
                             stop_move)
        lots = {p.symbol: p.lots for p in plans} or None
        gate = evaluate(out.spread, ticks, self.cfg.filters, y, x, out.beta,
                        self.cfg.risk.account_currency, lots)
        self.gate_log.append(GateRecord(ts, z, direction, out.beta, gate.passed and bool(plans),
                                        gate.reason, gate.expected_reversion_pips,
                                        gate.total_cost_pips, gate.ratio))
        if not plans:
            logger.warning("Signal z={:+.2f}: equity too small for minimum lots", z)
            return
        if not gate.passed:
            logger.info("Signal z={:+.2f} at {} rejected by fee gate: {} (edge {:.1f} vs cost "
                        "{:.1f} pips)", z, ts, gate.reason, gate.expected_reversion_pips,
                        gate.total_cost_pips)
            return
        await self.executor.open_basket(plans, direction, z, gate, now, out.beta)

    def _news_exit_hold(self, now: datetime) -> bool:
        buf = self.cfg.filters.news_exit_buffer_minutes
        return buf is not None and self.risk.news.blackout(now, self.cfg.filters, buf) is not None

    def _exit_reason(self, b: Basket, z: float) -> Optional[str]:
        s = self.cfg.strategy
        if s.max_hold_bars is not None and b.bars_held >= s.max_hold_bars:
            return "max hold"
        if not math.isfinite(z):
            return None
        if (b.direction == 1 and z >= -s.exit_z) or (b.direction == -1 and z <= s.exit_z):
            return "reverted"
        if s.stop_z_extra is not None:
            # entry-relative stop: long at Z_entry stops at Z_entry - extra; short at + extra
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


# Backwards-compatible name for code that imported the 3-leg bot class.
StatArbBot = PairsBot


def setup_logging(log_dir: str, level: str = "INFO") -> None:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(sys.stdout, level=level.upper(),
               format="{time:YYYY-MM-DD HH:mm:ss} {level:<8} {message}")
    logger.add(Path(log_dir) / "bot.log", level="DEBUG", rotation="10 MB", retention=10)


def load_news(cfg: AppConfig, live: bool) -> NewsCalendar:
    cal = NewsCalendar.from_csv(cfg.news_csv) if cfg.news_csv else NewsCalendar()
    if live and not cfg.require_news_calendar:
        last = cal.last_event_time()
        if last is None or last < datetime.now(timezone.utc):
            logger.warning("NEWS BLACKOUTS ARE OFF (STATARB_REQUIRE_NEWS_CALENDAR=0, no current "
                           "calendar). Fine for a demo; turn it on before a prop or real account.")
        return cal
    if live and cfg.require_news_calendar:
        last = cal.last_event_time()
        if last is None or last < datetime.now(timezone.utc):
            raise SystemExit("No current news calendar. Set STATARB_NEWS_CSV to a CSV of this "
                             "week's events (see bots/statarb_3leg/news_calendar.example.csv).")
    return cal


async def preflight(cfg: AppConfig, broker: Broker, echo=print) -> bool:
    """Read-only start-up check for a live/demo account. Places no orders."""
    problems: List[str] = []
    await broker.connect()
    try:
        acct = await broker.account_summary()
        echo(f"Account {acct['login']} on {acct['server']} ({'DEMO' if acct['demo'] else 'REAL'})"
             f", currency {acct['currency']}, balance {acct['balance']:.2f}, "
             f"equity {acct['equity']:.2f}")
        if not acct["demo"]:
            problems.append("this is a REAL-money account - use a demo first")
        if acct["currency"] and acct["currency"] != cfg.risk.account_currency:
            problems.append(f"account currency is {acct['currency']} but STATARB_ACCOUNT_CCY="
                            f"{cfg.risk.account_currency} - set STATARB_ACCOUNT_CCY="
                            f"{acct['currency']} in .env")
        infos, spreads = {}, {}
        for sym in cfg.price_symbols:
            try:
                info = await broker.symbol_info(cfg.broker_symbol(sym))
                tick = await broker.get_tick(cfg.broker_symbol(sym))
            except BrokerError as exc:
                problems.append(f"symbol {cfg.broker_symbol(sym)}: {exc}")
                continue
            infos[sym] = info
            spreads[sym] = (tick.ask - tick.bid) / 0.0001
            echo(f"  {cfg.broker_symbol(sym)}: bid {tick.bid} ask {tick.ask}, spread "
                 f"{spreads[sym]:.1f} pips, lots {info.volume_min}-{info.volume_max} "
                 f"step {info.volume_step}")
        if problems:
            return _report(problems, echo)
        bot = PairsBot(cfg, broker, NewsCalendar())
        await bot.warmup()
        out = bot.last_output
        n = cfg.strategy.history_bars
        echo(f"History: warm-up loaded, Kalman warm={bot.kalman.warm}, beta "
             f"{bot.kalman.beta:.3f}, last bar {bot.last_bar}, current Z "
             f"{out.z if out else float('nan'):+.2f} (trades when |Z| > {cfg.strategy.entry_z})")
        if not bot.kalman.warm:
            problems.append(f"not enough H1 history for warm-up (asked for {n} bars)")
        mids = mids_from_ticks(await bot.feed.ticks())
        equity = acct["equity"]
        stop_move = (cfg.strategy.stop_z_extra or 2.0) * (out.std if out else 0.0)
        try:
            plans = balance_legs(1, equity, mids, infos, cfg.risk, cfg.y, cfg.x,
                                 bot.kalman.beta, stop_move or None)
            echo("Size if a trade opened now: " + ", ".join(
                f"{p.lots:.2f} lots {p.symbol} ({'BUY' if p.side == 1 else 'SELL'})"
                for p in plans) if plans else "Size: below the minimum lot - equity too small")
        except (ValueError, KeyError) as exc:
            problems.append(f"sizing failed: {exc}")
        r, s = cfg.risk, cfg.strategy
        echo(f"Risk: notional x{r.notional_equity_mult:g}"
             + (f", fixed risk {r.risk_per_trade:.2%}" if r.risk_per_trade else "")
             + f", emergency stop {r.emergency_sl_pips or 'off'} pips/leg, Prop Shield "
               f"{r.daily_loss_limit:.0%}/day, flat before weekend: "
               f"{'yes' if s.flat_before_weekend else 'no'}")
        cal = NewsCalendar.from_csv(cfg.news_csv) if cfg.news_csv else NewsCalendar()
        last = cal.last_event_time()
        current = last is not None and last >= datetime.now(timezone.utc)
        echo(f"News calendar: {'current, ' + str(len(cal)) + ' events' if current else 'none'}"
             + ("" if current or cfg.require_news_calendar
                else " - blackouts OFF (allowed: STATARB_REQUIRE_NEWS_CALENDAR=0)"))
        if not current and cfg.require_news_calendar:
            problems.append("no current news calendar - add one (STATARB_NEWS_CSV) or, for a "
                            "demo only, set STATARB_REQUIRE_NEWS_CALENDAR=0")
    finally:
        await broker.shutdown()
    return _report(problems, echo)


def _report(problems: List[str], echo) -> bool:
    if problems:
        echo("\nNOT READY:")
        for p in problems:
            echo(f"  - {p}")
        return False
    echo("\nREADY - start the bot with:  python -m bots.statarb_3leg.main --live")
    return True


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="2-leg H1 pairs-trading bot")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--live", action="store_true", help="trade through MetaTrader 5")
    mode.add_argument("--paper", nargs=2, metavar="SYMBOL=CSV", help="replay two H1 CSVs")
    mode.add_argument("--check", action="store_true",
                      help="check the MT5 setup and show what the bot would trade (no orders)")
    p.add_argument("--log-level", default="INFO")
    return p.parse_args(argv)


async def _amain(args: argparse.Namespace) -> None:
    cfg = load_config()
    setup_logging(cfg.log_dir, args.log_level)
    if args.check:
        ok = await preflight(cfg, MT5Broker(cfg.broker))
        if not ok:
            raise SystemExit(1)
        return
    if args.paper:
        from .backtest import run_replay
        await run_replay(cfg, dict(x.split("=", 1) for x in args.paper),
                         news=load_news(cfg, live=False))
        return
    bot = PairsBot(cfg, MT5Broker(cfg.broker), load_news(cfg, live=True),
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
