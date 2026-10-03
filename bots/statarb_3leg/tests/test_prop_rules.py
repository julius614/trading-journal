"""Prop-firm features: fixed-risk sizing, emergency stops, flat-before-weekend, and
news-deferred exits."""
import asyncio
import dataclasses
from datetime import datetime, timedelta, timezone

import pytest

from bots.amd_fx.execution import SymbolInfo
from bots.statarb_3leg.config import FilterConfig, RiskConfig, StrategyConfig
from bots.statarb_3leg.execution import PaperBroker
from bots.statarb_3leg.main import PairsBot
from bots.statarb_3leg.risk_manager import (NewsCalendar, NewsEvent, balance_legs,
                                            weekend_phase)
from bots.statarb_3leg.tests.test_signals import CFG, replay

EU, GU = 1.1000, 1.2700
MIDS = {"EURUSD": EU, "GBPUSD": GU}
INFO = {s: SymbolInfo(s, 5, 1e-5, 1e-5, 1.0, 0.01, 100.0, 0.01) for s in MIDS}
UTC = timezone.utc


# ---- fixed-risk sizing
def test_fixed_risk_loss_at_stop_matches_risk():
    risk = RiskConfig(risk_per_trade=0.005)
    stop_move = 0.0020                                 # 2 sigma of a 10 bp spread
    p = {l.symbol: l for l in balance_legs(1, 100_000.0, MIDS, INFO, risk, "EURUSD", "GBPUSD",
                                           0.6, stop_move)}
    notional = p["EURUSD"].lots * 100_000 * EU
    assert notional * stop_move == pytest.approx(500.0, rel=0.01)   # 0.5% of 100k


def test_fixed_risk_is_capped():
    risk = RiskConfig(risk_per_trade=0.01, max_notional_mult=3.0)
    p = {l.symbol: l for l in balance_legs(1, 110_000.0, MIDS, INFO, risk, "EURUSD", "GBPUSD",
                                           0.6, 1e-5)}
    assert p["EURUSD"].lots == pytest.approx(3.0)       # 3 x $110k / $110k per lot


def test_fixed_risk_needs_stop_distance():
    with pytest.raises(ValueError):
        balance_legs(1, 1e5, MIDS, INFO, RiskConfig(risk_per_trade=0.005), "EURUSD", "GBPUSD",
                     0.6, None)


def test_without_risk_mode_stop_is_ignored():
    a = balance_legs(1, 110_000.0, MIDS, INFO, RiskConfig(), "EURUSD", "GBPUSD", 0.6)
    b = balance_legs(1, 110_000.0, MIDS, INFO, RiskConfig(), "EURUSD", "GBPUSD", 0.6, 0.001)
    assert a == b


# ---- weekend rule
ON = StrategyConfig(flat_before_weekend=True)


@pytest.mark.parametrize("utc_close", [
    datetime(2025, 7, 11, 20, 0, tzinfo=UTC),    # summer: 16:00 New York = 20:00 UTC
    datetime(2025, 1, 10, 21, 0, tzinfo=UTC),    # winter: 16:00 New York = 21:00 UTC
])
def test_weekend_close_tracks_new_york_time(utc_close):
    assert weekend_phase(utc_close, ON) == "close"
    assert weekend_phase(utc_close - timedelta(minutes=1), ON) == "no_entry"
    assert weekend_phase(utc_close - timedelta(hours=4, minutes=1), ON) is None
    assert weekend_phase(utc_close, StrategyConfig()) is None          # off by default


def test_weekend_reopens_sunday_evening_new_york():
    assert weekend_phase(datetime(2025, 7, 13, 20, 59, tzinfo=UTC), ON) == "close"
    assert weekend_phase(datetime(2025, 7, 13, 21, 0, tzinfo=UTC), ON) is None
    assert weekend_phase(datetime(2025, 7, 16, 12, 0, tzinfo=UTC), ON) is None


def test_flat_weekend_replay_holds_nothing_over_weekend(pair):
    cfg = dataclasses.replace(CFG, strategy=dataclasses.replace(CFG.strategy,
                                                                flat_before_weekend=True))
    baskets = replay(pair, cfg)["baskets"]
    assert baskets
    for b in baskets:
        opened = datetime.fromisoformat(b.opened_at)
        closed = datetime.fromisoformat(b.closed_at)
        assert weekend_phase(opened, cfg.strategy) is None
        t = opened                                  # never open across Friday 16:00 NY
        while t < closed:
            assert weekend_phase(t, cfg.strategy) != "close"
            t += timedelta(hours=1)


# ---- emergency stop and news-deferred exits
class _SLBroker(PaperBroker):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.sl = {}

    async def modify_sl(self, ticket, sl, tp):
        self.sl[ticket] = sl
        return True


def _bot(pair, cfg, news=None):
    broker = _SLBroker(10_000.0, "USD", {"EURUSD": 0.2, "GBPUSD": 0.5}, 7.0, "H1")
    for s, df in pair.items():
        broker.load_bars(s, df)
    return broker, PairsBot(cfg, broker, news)


def test_emergency_stop_set_on_every_leg(pair):
    broker, bot = _bot(pair, CFG)

    async def go():
        await broker.connect()
        for ts in pair["EURUSD"].index:
            broker.advance(ts)
            await bot.step((ts + timedelta(hours=1)).to_pydatetime())
            if bot.executor.basket is not None:
                return bot.executor.basket
    b = asyncio.run(go())
    assert b is not None
    for leg in b.legs:
        assert broker.sl[leg.ticket] == pytest.approx(leg.price - leg.side * 250 * 1e-4)


def test_news_window_defers_normal_exit_not_stop(pair):
    now = datetime(2024, 3, 1, 13, 30, tzinfo=UTC)
    news = NewsCalendar([NewsEvent(now, "USD", "high", "NFP")])
    cfg = dataclasses.replace(CFG, filters=FilterConfig(news_exit_buffer_minutes=2))
    _, bot = _bot(pair, cfg, news)
    assert bot._news_exit_hold(now + timedelta(minutes=1))
    assert not bot._news_exit_hold(now + timedelta(minutes=3))
    _, off = _bot(pair, CFG, news)
    assert not off._news_exit_hold(now)


def test_basket_closed_when_a_leg_disappears(pair):
    broker, bot = _bot(pair, CFG)

    async def go():
        await broker.connect()
        idx = pair["EURUSD"].index
        for i, ts in enumerate(idx):
            broker.advance(ts)
            await bot.step((ts + timedelta(hours=1)).to_pydatetime())
            if bot.executor.basket is not None:
                break
        leg = bot.executor.basket.legs[0]
        await broker.close_position(leg.ticket)          # e.g. its emergency stop fired
        broker.advance(idx[i + 1])
        await bot.step((idx[i + 1] + timedelta(hours=1)).to_pydatetime())
        return bot.executor
    ex = asyncio.run(go())
    assert ex.basket is None
    assert ex.history[-1].exit_reason == "leg closed outside bot"
    assert not asyncio.run(broker.positions())
