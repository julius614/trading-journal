import asyncio
import dataclasses
from datetime import datetime, time, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from bots.statarb_3leg.backtest import run_replay
from bots.statarb_3leg.config import AppConfig, FilterConfig, RiskConfig, StrategyConfig
from bots.statarb_3leg.data_fetcher import load_leg_csv
from bots.statarb_3leg.execution import Basket, PaperBroker
from bots.statarb_3leg.main import PairsBot
from bots.statarb_3leg.risk_manager import NewsCalendar, NewsEvent, RiskManager
from bots.statarb_3leg.tests.conftest import make_pair

RAW = {"EURUSD": 0.2, "GBPUSD": 0.5}
CFG = AppConfig(strategy=StrategyConfig(warmup_bars=300), pair=("EURUSD", "GBPUSD"))
HOUR = timedelta(hours=1)


def replay(frames, cfg=CFG, spreads=RAW, commission=7.0, news=None):
    return asyncio.run(run_replay(cfg, {}, spread_pips=spreads, commission_per_lot=commission,
                                  news=news, frames=frames, verbose=False))


def make_bot(frames, cfg=CFG, spreads=RAW, commission=7.0):
    broker = PaperBroker(10_000.0, "USD", spreads, commission, "H1")
    for s, df in frames.items():
        broker.load_bars(s, df)
    return broker, PairsBot(cfg, broker)


async def drive(broker, bot, index):
    for ts in index:
        broker.advance(ts)
        await bot.step((ts + HOUR).to_pydatetime())


def test_mean_reverting_pair_is_profitable_after_costs(pair):
    res = replay(pair)
    baskets = res["baskets"]
    assert len(baskets) >= 10
    assert all(len(b.legs) == 2 for b in baskets)
    assert res["stats"]["total_pnl"] > 0
    reasons = pd.Series([b.exit_reason for b in baskets]).value_counts()
    assert reasons.get("reverted", 0) > len(baskets) / 2
    gates = res["gates"]
    assert gates.passed.all()                       # 40-pip swings dwarf ~1.5 pips of cost
    assert gates.ratio.median() > 10


def test_entry_sides_match_z_sign(pair):
    for b in replay(pair)["baskets"]:
        sides = {leg.symbol: leg.side for leg in b.legs}
        if b.entry_z < 0:                           # y cheap -> long spread
            assert b.direction == 1 and sides == {"EURUSD": 1, "GBPUSD": -1}
        else:
            assert b.direction == -1 and sides == {"EURUSD": -1, "GBPUSD": 1}
        assert abs(b.entry_z) > 2
        assert b.entry_beta == pytest.approx(0.6, abs=0.15)


def test_fee_gate_blocks_tiny_swings():
    tiny = make_pair(swing_pips=0.4)                # spread sd 0.4 pips: below ~3.8 needed
    res = replay(tiny)
    assert len(res["baskets"]) == 0
    assert len(res["gates"]) > 20 and not res["gates"].passed.any()


def test_news_blackout_blocks_entries(pair):
    first = replay(pair)["baskets"][0]
    t = datetime.fromisoformat(first.opened_at)
    news = NewsCalendar([NewsEvent(t + timedelta(minutes=5), "USD", "high", "NFP")])
    res = replay(pair, news=news)
    assert res["bot"].blocked["news"] >= 1
    assert res["baskets"][0].opened_at != first.opened_at


def test_other_currency_or_low_impact_news_ignored(pair):
    first = replay(pair)["baskets"][0]
    t = datetime.fromisoformat(first.opened_at)
    news = NewsCalendar([NewsEvent(t, "JPY", "high", "BoJ"), NewsEvent(t, "USD", "low", "x")])
    assert replay(pair, news=news)["baskets"][0].opened_at == first.opened_at


def test_rollover_window_blocks_entries(pair):
    always = dataclasses.replace(CFG, filters=FilterConfig(
        rollover_anchor="utc", rollover_start=time(0, 0), rollover_end=time(23, 59, 59)))
    res = replay(pair, cfg=always)
    assert len(res["baskets"]) == 0
    assert res["bot"].blocked["rollover window"] > 10


def test_failed_second_leg_rolls_back_first(pair):
    async def go():
        broker, bot = make_bot(pair)
        broker.fail_orders = {"GBPUSD": 1}
        await drive(broker, bot, pair["EURUSD"].index)
        return broker, bot
    broker, bot = asyncio.run(go())
    rolled = [f for f in broker.fills if f.open_time == f.close_time]
    assert [f.symbol for f in rolled] == ["EURUSD"]   # the filled y leg was closed at once
    assert len(bot.executor.history) >= 10            # later signals traded normally
    assert not broker._pos


def test_prop_shield_closes_basket_and_halts(pair):
    async def go():
        broker, bot = make_bot(pair)
        idx = pair["EURUSD"].index
        i = 0
        while bot.executor.basket is None:
            broker.advance(idx[i])
            await bot.step((idx[i] + HOUR).to_pydatetime())
            i += 1
        broker.balance -= 300.0                       # a 3% loss elsewhere today
        broker.advance(idx[i])
        await bot.step((idx[i] + HOUR).to_pydatetime())
        return bot
    bot = asyncio.run(go())
    assert bot.executor.basket is None
    assert bot.executor.history[-1].exit_reason == "prop shield"
    assert bot.risk.state.locked


def test_exit_rules_with_entry_relative_stop():
    bot = PairsBot(AppConfig(), PaperBroker())
    long_b = Basket("x", 1, "", -2.5, 40.0, 1.5)
    short_b = Basket("y", -1, "", 2.5, 40.0, 1.5)
    assert bot._exit_reason(long_b, -0.05) == "reverted"
    assert bot._exit_reason(long_b, 0.8) == "reverted"           # crossed zero
    assert bot._exit_reason(long_b, -1.0) is None
    assert bot._exit_reason(long_b, -4.4) is None                # Z_stop = -2.5 - 2.0 = -4.5
    assert bot._exit_reason(long_b, -4.6) == "stop z"
    assert bot._exit_reason(short_b, 0.09) == "reverted"
    assert bot._exit_reason(short_b, 4.4) is None                # Z_stop = +4.5
    assert bot._exit_reason(short_b, 4.6) == "stop z"
    big = Basket("z", -1, "", 6.0, 90.0, 1.5)
    assert bot._exit_reason(big, 5.0) is None                    # reverting, not failing
    assert bot._exit_reason(big, 8.5) == "stop z"
    long_b.bars_held = 47
    assert bot._exit_reason(long_b, -1.0) is None
    long_b.bars_held = 48                                        # 48 H1 bars ~ 2 days
    assert bot._exit_reason(long_b, -1.0) == "max hold"


def _utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


def test_risk_manager_breaker_and_day_reset():
    rm = RiskManager(RiskConfig(), FilterConfig())
    t = _utc(2024, 3, 5, 0, 5)
    rm.update_day(t, 10_000)
    assert not rm.check_breaker(9_801)
    assert rm.check_breaker(9_800)
    assert rm.entry_block(t.replace(hour=9))[0]
    assert rm.update_day(t + timedelta(days=1), 9_800) and not rm.state.locked


def test_rollover_follows_new_york_close():
    rm = RiskManager(RiskConfig(), FilterConfig())
    assert rm.in_rollover(_utc(2026, 7, 7, 21, 5))        # summer: 21:00 UTC
    assert not rm.in_rollover(_utc(2026, 7, 7, 20, 45))
    assert rm.in_rollover(_utc(2026, 1, 15, 22, 0))       # winter: 22:00 UTC
    assert not rm.in_rollover(_utc(2026, 1, 15, 21, 5))
    assert not rm.in_rollover(_utc(2026, 3, 6, 21, 0))    # DST switch Sun 8 Mar 2026
    assert rm.in_rollover(_utc(2026, 3, 9, 21, 0))
    assert rm.in_rollover(_utc(2026, 10, 30, 21, 0))      # back on Sun 1 Nov 2026
    assert not rm.in_rollover(_utc(2026, 11, 2, 21, 0))
    utc_rm = RiskManager(RiskConfig(), FilterConfig(rollover_anchor="utc"))
    assert not utc_rm.in_rollover(_utc(2026, 7, 7, 21, 5))
    with pytest.raises(ValueError):
        RiskManager(RiskConfig(), FilterConfig(rollover_anchor="london"))


def test_news_calendar_csv(tmp_path):
    p = tmp_path / "news.csv"
    p.write_text("datetime_utc,currency,impact,title\n2024-03-05T13:30:00Z,USD,High,CPI\n")
    cal = NewsCalendar.from_csv(p)
    f = FilterConfig()
    assert cal.blackout(_utc(2024, 3, 5, 13, 14), f) is None          # 16 min before
    assert cal.blackout(_utc(2024, 3, 5, 13, 15), f).title == "CPI"
    assert cal.blackout(_utc(2024, 3, 5, 13, 45), f) is not None


def test_mt5_csv_spread_column_converted(tmp_path):
    p = tmp_path / "EURUSD_H1.csv"
    p.write_text("datetime,open,high,low,close,volume,spread\n"
                 "2024-03-05 08:00:00+00:00,1.08,1.081,1.079,1.0805,100,7\n")
    df = load_leg_csv(p)
    assert df["spread_pips"].iat[0] == pytest.approx(0.7)
    assert df.index[0] == pd.Timestamp("2024-03-05 08:00", tz="UTC")


def test_default_config_is_audusd_nzdusd_with_48_bar_stop():
    cfg = AppConfig()
    assert cfg.pair == ("AUDUSD", "NZDUSD")
    assert cfg.strategy.max_hold_bars == 48 and cfg.strategy.use_coint_gate
    assert cfg.strategy.coint_window == 250 and cfg.strategy.coint_max_half_life == 48
    assert {"AUD", "NZD", "USD"} <= set(cfg.filters.news_currencies)


def test_gate_blocks_a_drifting_relationship():
    # add a random walk to the y leg: the relationship drifts and stops being cointegrated
    drifting = make_pair(seed=11)
    rng = np.random.default_rng(12)
    walk = np.exp(np.cumsum(rng.normal(0, 0.0015, len(drifting["EURUSD"]))))
    for col in ("open", "high", "low", "close"):
        drifting["EURUSD"][col] = drifting["EURUSD"][col] * walk
    res = replay(drifting)
    gated_off = replay(drifting, cfg=dataclasses.replace(
        CFG, strategy=dataclasses.replace(CFG.strategy, use_coint_gate=False)))
    assert res["bot"].blocked["cointegration"] > 0
    assert len(res["baskets"]) < len(gated_off["baskets"]) / 2


def test_gate_lets_a_mean_reverting_pair_trade(pair):
    res = replay(pair)
    checks = pd.DataFrame(res["coint_checks"], columns=["t", "passed", "p", "hl"])
    assert checks.passed.mean() > 0.6
    assert (checks.loc[checks.passed, "hl"] < 48).all()
