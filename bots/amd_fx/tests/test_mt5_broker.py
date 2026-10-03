"""MT5Broker against a fake MetaTrader5 module (the real one is Windows-only)."""
import asyncio
import sys
import time as _time
from types import SimpleNamespace as NS

import numpy as np
import pandas as pd
import pytest

from bots.amd_fx.config import BrokerConfig
from bots.amd_fx.execution import MT5Broker

SERVER_OFFSET_H = 3   # broker server = UTC+3


class FakeMT5:
    TIMEFRAME_M1, TIMEFRAME_M5, TIMEFRAME_D1 = 1, 5, 16408
    TIMEFRAME_M15, TIMEFRAME_M30, TIMEFRAME_H1, TIMEFRAME_H4 = 15, 30, 16385, 16388
    ORDER_TYPE_BUY, ORDER_TYPE_SELL = 0, 1
    POSITION_TYPE_BUY, POSITION_TYPE_SELL = 0, 1
    ORDER_FILLING_FOK, ORDER_FILLING_IOC, ORDER_FILLING_RETURN = 0, 1, 2
    TRADE_ACTION_DEAL, TRADE_ACTION_SLTP = 1, 6
    ORDER_TIME_GTC = 0
    TRADE_RETCODE_DONE, TRADE_RETCODE_PLACED, TRADE_RETCODE_DONE_PARTIAL = 10009, 10008, 10010

    def __init__(self):
        self.sent = []
        self.responses = []          # queued order_send retcodes
        self.rates_args = None
        now = _time.time() + SERVER_OFFSET_H * 3600
        self.tick = NS(time=int(now), bid=1.10000, ask=1.10008)
        self._positions = [
            NS(ticket=11, symbol="EURUSD", type=0, volume=0.5, price_open=1.099, sl=1.098,
               tp=1.101, profit=5.0, comment="AMD:x:A", magic=260110),
            NS(ticket=99, symbol="EURUSD", type=1, volume=1.0, price_open=1.1, sl=0, tp=0,
               profit=-1.0, comment="manual", magic=0),
        ]

    def initialize(self, **kw): return True
    def last_error(self): return (0, "ok")
    def shutdown(self): return True
    def account_info(self):
        return NS(login=1, server="Demo", trade_mode=0, equity=10_000.0, balance=9_990.0,
                  currency="USD")
    def symbol_select(self, s, flag): return True
    def symbol_info(self, s):
        return NS(digits=5, point=0.00001, trade_tick_size=0.00001, trade_tick_value=1.0,
                  volume_min=0.01, volume_max=100.0, volume_step=0.01, filling_mode=1 | 2)
    def symbol_info_tick(self, s): return self.tick

    def copy_rates_from_pos(self, s, tf, start, count):
        self.rates_args = (s, tf, start, count)
        base = int(pd.Timestamp("2024-03-05 10:00").timestamp())   # server time
        dt = np.dtype([("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"),
                       ("close", "f8"), ("tick_volume", "i8"), ("spread", "i4"),
                       ("real_volume", "i8")])
        return np.array([(base + i * 300, 1.1, 1.2, 1.0, 1.1, 10, 8, 0) for i in range(count)],
                        dtype=dt)

    def positions_get(self, symbol=None, ticket=None):
        ps = self._positions
        if ticket is not None:
            ps = [p for p in ps if p.ticket == ticket]
        return tuple(ps)

    def order_send(self, req):
        self.sent.append(dict(req))
        code = self.responses.pop(0) if self.responses else self.TRADE_RETCODE_DONE
        return NS(retcode=code, order=500 + len(self.sent), price=req.get("price", 0.0),
                  volume=req.get("volume", 0.0), comment=f"code {code}")

    def history_deals_get(self, position=None):
        return (NS(profit=10.0, commission=-3.5, swap=-0.5), NS(profit=5.0, commission=0, swap=0))


@pytest.fixture
def broker(monkeypatch):
    fake = FakeMT5()
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake)
    b = MT5Broker(BrokerConfig(retry_delay_seconds=0))
    asyncio.run(b.connect())
    return b, fake


def run(coro):
    return asyncio.run(coro)


def test_rates_skip_forming_bar_and_convert_to_utc(broker):
    b, fake = broker
    df = run(b.get_rates("EURUSD", "M5", 3))
    assert fake.rates_args == ("EURUSD", FakeMT5.TIMEFRAME_M5, 1, 3)   # start_pos=1
    assert df.index[0] == pd.Timestamp("2024-03-05 07:00", tz="UTC")   # 10:00 server - 3h
    assert list(df.columns) == ["open", "high", "low", "close", "volume", "spread"]


def test_offset_override_from_config(monkeypatch):
    fake = FakeMT5()
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake)
    b = MT5Broker(BrokerConfig(server_utc_offset_hours=2))
    run(b.connect())
    df = run(b.get_rates("EURUSD", "M5", 1))
    assert df.index[0] == pd.Timestamp("2024-03-05 08:00", tz="UTC")


def test_positions_filtered_by_magic(broker):
    b, _ = broker
    ps = run(b.positions())
    assert [p.ticket for p in ps] == [11] and ps[0].side == 1


def test_market_order_falls_back_on_unsupported_filling(broker):
    b, fake = broker
    fake.responses = [10030, FakeMT5.TRADE_RETCODE_DONE]
    res = run(b.market_order("EURUSD", 1, 0.25, 1.0975, 1.1, "AMD:t:A"))
    assert res.ok
    assert [r["type_filling"] for r in fake.sent] == [FakeMT5.ORDER_FILLING_FOK,
                                                       FakeMT5.ORDER_FILLING_IOC]
    assert fake.sent[-1]["price"] == 1.10008          # buys at the ask
    assert fake.sent[-1]["magic"] == 260110


def test_market_order_retries_requote_then_gives_up(broker):
    b, fake = broker
    fake.responses = [10004, 10004, 10004]
    res = run(b.market_order("EURUSD", -1, 0.25, 1.1025, 1.1, "AMD:t:A"))
    assert not res.ok and "10004" in res.message
    assert len(fake.sent) == 3                          # max_retries


def test_market_order_does_not_retry_hard_errors(broker):
    b, fake = broker
    fake.responses = [10019]                            # no money
    res = run(b.market_order("EURUSD", 1, 0.25, 1.0975, 1.1, "x"))
    assert not res.ok and len(fake.sent) == 1


def test_close_position_sends_opposite_deal(broker):
    b, fake = broker
    res = run(b.close_position(11))
    assert res.ok
    req = fake.sent[-1]
    assert req["type"] == FakeMT5.ORDER_TYPE_SELL and req["position"] == 11
    assert req["price"] == 1.10000                      # sells at the bid


def test_closed_pnl_includes_costs(broker):
    b, _ = broker
    assert run(b.closed_pnl(11)) == pytest.approx(11.0)


def test_account_and_symbol_info(broker):
    b, _ = broker
    assert run(b.account_equity()) == 10_000.0
    info = run(b.symbol_info("EURUSD"))
    assert info.tick_value == 1.0 and info.pip == 0.0001
