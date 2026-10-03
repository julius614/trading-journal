import asyncio
import dataclasses
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from bots.statarb_3leg.backtest import run_replay
from bots.statarb_3leg.config import AppConfig, FilterConfig, RiskConfig
from bots.statarb_3leg.data_fetcher import load_leg_csv
from bots.statarb_3leg.execution import Basket, PaperBroker
from bots.statarb_3leg.main import StatArbBot
from bots.statarb_3leg.risk_manager import NewsCalendar, NewsEvent, RiskManager
from bots.statarb_3leg.tests.conftest import make_triangle

ZERO = {"EURUSD": 0.0, "GBPUSD": 0.0, "EURGBP": 0.0}
RAW = {"EURUSD": 0.2, "GBPUSD": 0.5, "EURGBP": 0.6}
CFG = AppConfig()


def replay(frames, cfg=CFG, spreads=RAW, commission=7.0, news=None):
    """Raw-account costs by default: the gate then filters out noise (|Z| > 2 on ~5% of
    bars) and only the planted dislocations trade."""
    return asyncio.run(run_replay(cfg, {}, spread_pips=spreads, commission_per_lot=commission,
                                  news=news, frames=frames, verbose=False))


def test_dislocations_are_traded_and_close_on_reversion(triangle):
    res = replay(triangle)
    baskets = res["baskets"]
    # jumps at bars 500, 750, ..., 1750 come after the 288-bar warm-up (bar 250 doesn't)
    assert len(baskets) == 6
    assert all(b.exit_reason == "reverted" for b in baskets)
    assert [b.direction for b in baskets] == [1, -1, 1, -1, 1, -1]   # jumps alternate +,-
    assert all(b.pnl > 0 for b in baskets)
    assert all(len(b.legs) == 3 for b in baskets)


def test_entry_direction_matches_spec(triangle):
    baskets = replay(triangle)["baskets"]
    long_b, short_b = baskets[0], baskets[1]     # bar-500 jump is negative, bar-750 positive
    assert long_b.entry_z < -2
    assert {l.symbol: l.side for l in long_b.legs} == {"EURGBP": 1, "EURUSD": -1, "GBPUSD": 1}
    assert short_b.entry_z > 2
    assert {l.symbol: l.side for l in short_b.legs} == {"EURGBP": -1, "EURUSD": 1, "GBPUSD": -1}


def test_fee_gate_blocks_small_dislocations():
    small = make_triangle(jump_pips=2.0)        # z is huge, but 2 pips < 2.5 x ~2.7 pips cost
    res = replay(small)
    gates = res["gates"]
    assert len(res["baskets"]) == 0
    assert len(gates) >= 6 and not gates.passed.any()
    assert (gates.cost_pips > 2.0).all()


def test_fee_gate_allows_large_dislocations_with_costs():
    big = make_triangle(jump_pips=15.0)
    res = replay(big)
    assert len(res["baskets"]) == 6
    assert res["gates"].passed.sum() == 6


def test_news_blackout_blocks_entries(triangle):
    jump_time = triangle["EURUSD"].index[500].to_pydatetime() + timedelta(minutes=5)
    news = NewsCalendar([NewsEvent(jump_time + timedelta(minutes=10), "USD", "high", "CPI")])
    res = replay(triangle, news=news)
    assert res["bot"].blocked["news"] >= 1
    assert len(res["baskets"]) == 5


def test_low_impact_or_other_currency_news_ignored(triangle):
    t = triangle["EURUSD"].index[500].to_pydatetime() + timedelta(minutes=5)
    news = NewsCalendar([NewsEvent(t, "JPY", "high", "BoJ"), NewsEvent(t, "USD", "low", "x")])
    assert len(replay(triangle, news=news)["baskets"]) == 6


def test_rollover_blocks_entries():
    # start chosen so the bar-500 jump closes at 22:00 UTC
    tri = make_triangle(start="2024-03-04 04:15")
    res = replay(tri)
    assert res["bot"].blocked["rollover window"] >= 1
    assert len(res["baskets"]) == 5


def test_failed_leg_rolls_back_filled_legs(triangle):
    async def go():
        broker = PaperBroker(10_000.0, "USD", RAW, 7.0)
        for s, df in triangle.items():
            broker.load_bars(s, df)
        broker.fail_orders = {"GBPUSD": 1}       # the third leg of the first basket fails
        bot = StatArbBot(CFG, broker)
        for ts in triangle["EURUSD"].index:
            broker.advance(ts)
            await bot.step((ts + timedelta(minutes=5)).to_pydatetime())
        return broker, bot
    broker, bot = asyncio.run(go())
    # the first attempt is rolled back; the next bar is still a valid signal and fills
    assert len(bot.executor.history) == 6
    assert bot.executor.history[0].opened_at.endswith("17:50:00+00:00")
    rolled = [f for f in broker.fills if f.open_time == f.close_time]
    assert {f.symbol for f in rolled} == {"EURGBP", "EURUSD"}
    assert not broker._pos                       # nothing left open


def test_prop_shield_closes_basket_and_halts(triangle):
    async def go():
        broker = PaperBroker(10_000.0, "USD", RAW, 7.0)
        for s, df in triangle.items():
            broker.load_bars(s, df)
        bot = StatArbBot(CFG, broker)
        idx = triangle["EURUSD"].index
        for ts in idx[:501]:                     # up to and including the bar-500 entry
            broker.advance(ts)
            await bot.step((ts + timedelta(minutes=5)).to_pydatetime())
        assert bot.executor.basket is not None
        broker.balance -= 300.0                  # simulate a 3% loss elsewhere today
        broker.advance(idx[501])
        await bot.step((idx[501] + timedelta(minutes=5)).to_pydatetime())
        return bot
    bot = asyncio.run(go())
    assert bot.executor.basket is None
    assert bot.executor.history[-1].exit_reason == "prop shield"
    assert bot.risk.state.locked


def test_exit_rules():
    bot = StatArbBot(AppConfig(), PaperBroker())
    long_b = Basket("x", 1, "", -2.5, 5.0, 2.0)
    short_b = Basket("y", -1, "", 2.5, 5.0, 2.0)
    assert bot._exit_reason(long_b, -0.05) == "reverted"
    assert bot._exit_reason(long_b, 0.8) == "reverted"           # crossed zero
    assert bot._exit_reason(long_b, -1.0) is None
    assert bot._exit_reason(long_b, -4.4) is None                # entry -2.5, stop at -4.5
    assert bot._exit_reason(long_b, -4.6) == "stop z"
    big = Basket("z", -1, "", 17.0, 15.0, 2.7)
    assert bot._exit_reason(big, 6.5) is None                    # reverting, not failing
    assert bot._exit_reason(big, 19.5) == "stop z"
    assert bot._exit_reason(short_b, 0.09) == "reverted"
    assert bot._exit_reason(short_b, 1.0) is None
    long_b.bars_held = 288
    assert bot._exit_reason(long_b, -1.0) == "max hold"


def test_risk_manager_rollover_and_breaker():
    rm = RiskManager(RiskConfig(), FilterConfig())
    t = datetime(2024, 3, 5, 0, 5, tzinfo=timezone.utc)
    rm.update_day(t, 10_000)
    assert rm.entry_block(t.replace(hour=22, minute=0)) == (True, "rollover window")
    assert not rm.check_breaker(9_801)
    assert rm.check_breaker(9_800)
    assert rm.entry_block(t.replace(hour=9))[0]
    assert rm.update_day(t + timedelta(days=1), 9_800) and not rm.state.locked


def test_news_calendar_csv(tmp_path):
    p = tmp_path / "news.csv"
    p.write_text("datetime_utc,currency,impact,title\n2024-03-05T13:30:00Z,USD,High,CPI\n")
    cal = NewsCalendar.from_csv(p)
    f = FilterConfig()
    assert cal.blackout(datetime(2024, 3, 5, 13, 14, tzinfo=timezone.utc), f) is None   # 16 min before
    assert cal.blackout(datetime(2024, 3, 5, 13, 15, tzinfo=timezone.utc), f).title == "CPI"
    assert cal.blackout(datetime(2024, 3, 5, 13, 45, tzinfo=timezone.utc), f) is not None


def test_mt5_csv_spread_column_converted(tmp_path):
    p = tmp_path / "EURGBP_M5.csv"
    p.write_text("datetime,open,high,low,close,volume,spread\n"
                 "2024-03-05 08:00:00+00:00,0.86,0.861,0.859,0.8605,100,7\n")
    df = load_leg_csv(p)
    assert df["spread_pips"].iat[0] == pytest.approx(0.7)
    assert df.index[0] == pd.Timestamp("2024-03-05 08:00", tz="UTC")


def test_without_costs_noise_gets_traded(triangle):
    """Why the gate matters: at zero cost, ordinary noise beyond |Z| = 2 is traded too."""
    res = replay(triangle, spreads=ZERO, commission=0.0)
    assert len(res["baskets"]) > 6               # more than the 6 planted dislocations


def _utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def test_rollover_follows_new_york_close_in_summer_and_winter():
    rm = RiskManager(RiskConfig(), FilterConfig())
    # summer (US daylight saving): rollover 17:00 NY = 21:00 UTC
    assert rm.in_rollover(_utc(2026, 7, 7, 21, 5))
    assert rm.in_rollover(_utc(2026, 7, 7, 20, 50))
    assert not rm.in_rollover(_utc(2026, 7, 7, 20, 45))
    assert not rm.in_rollover(_utc(2026, 7, 7, 21, 20))
    # winter: rollover 17:00 NY = 22:00 UTC (the original 21:50-22:15 UTC window)
    assert rm.in_rollover(_utc(2026, 1, 15, 22, 0))
    assert rm.in_rollover(_utc(2026, 1, 15, 21, 50))
    assert not rm.in_rollover(_utc(2026, 1, 15, 21, 5))
    assert not rm.in_rollover(_utc(2026, 1, 15, 22, 15))


def test_rollover_dst_switch_days():
    rm = RiskManager(RiskConfig(), FilterConfig())
    # US clocks go forward Sun 8 Mar 2026 and back Sun 1 Nov 2026
    assert not rm.in_rollover(_utc(2026, 3, 6, 21, 0))     # Fri before: winter
    assert rm.in_rollover(_utc(2026, 3, 9, 21, 0))         # Mon after: summer
    assert rm.in_rollover(_utc(2026, 10, 30, 21, 0))       # Fri before: summer
    assert not rm.in_rollover(_utc(2026, 11, 2, 21, 0))    # Mon after: winter
    assert rm.in_rollover(_utc(2026, 11, 2, 22, 0))


def test_rollover_utc_mode_keeps_fixed_window():
    rm = RiskManager(RiskConfig(), FilterConfig(rollover_anchor="utc"))
    assert not rm.in_rollover(_utc(2026, 7, 7, 21, 5))
    assert rm.in_rollover(_utc(2026, 7, 7, 22, 0))
    with pytest.raises(ValueError):
        RiskManager(RiskConfig(), FilterConfig(rollover_anchor="london"))
