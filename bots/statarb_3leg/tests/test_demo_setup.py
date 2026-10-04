"""Demo-readiness: non-USD accounts, optional news calendar, and the --check preflight."""
import asyncio
import dataclasses
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from bots.amd_fx.execution import BrokerError, SymbolInfo, Tick
from bots.statarb_3leg import main as m
from bots.statarb_3leg.config import AppConfig, RiskConfig, load_config, validate_pair
from bots.statarb_3leg.fee_gate import evaluate, mids_from_ticks
from bots.statarb_3leg.risk_manager import balance_legs

AU, NZ, EU = 0.6600, 0.6000, 1.1000
INFO = SymbolInfo("X", 5, 1e-5, 1e-5, 1.0, 0.01, 100.0, 0.01)


def test_eur_account_needs_eurusd_and_sizes_in_usd():
    cfg = AppConfig(risk=RiskConfig(account_currency="EUR"))
    assert cfg.conversion_symbol == "EURUSD"
    assert cfg.price_symbols == ("AUDUSD", "NZDUSD", "EURUSD")
    mids = {"AUDUSD": AU, "NZDUSD": NZ, "EURUSD": EU}
    plans = {p.symbol: p for p in balance_legs(1, 100_000.0, mids, {"AUDUSD": INFO, "NZDUSD": INFO},
                                               cfg.risk, "AUDUSD", "NZDUSD", 0.8)}
    # EUR 100k = USD 110k of AUDUSD notional = 110k / 0.66 / 100k lots
    assert plans["AUDUSD"].lots == pytest.approx(round(110_000 / AU / 100_000 - 0.005, 2), abs=0.01)
    assert AppConfig(risk=RiskConfig(account_currency="USD")).conversion_symbol is None
    assert AppConfig(risk=RiskConfig(account_currency="AUD")).conversion_symbol is None
    assert AppConfig(risk=RiskConfig(account_currency="JPY")).conversion_symbol == "USDJPY"
    with pytest.raises(ValueError):
        validate_pair(("AUDUSD", "NZDUSD"), "EU")


def test_fee_gate_on_eur_account():
    t = datetime(2026, 1, 5, tzinfo=timezone.utc)
    ticks = {"AUDUSD": Tick(t, AU, AU + 0.00003), "NZDUSD": Tick(t, NZ, NZ + 0.00007),
             "EURUSD": Tick(t, EU, EU + 0.00002)}
    cfg = AppConfig(risk=RiskConfig(account_currency="EUR"))
    cfg = dataclasses.replace(cfg, filters=dataclasses.replace(cfg.filters, commission_per_lot=0))
    usd = evaluate(0.004, ticks, cfg.filters, "AUDUSD", "NZDUSD", 0.8, "USD")
    eur = evaluate(0.004, ticks, cfg.filters, "AUDUSD", "NZDUSD", 0.8, "EUR")
    assert eur.ratio == pytest.approx(usd.ratio, rel=1e-3)          # ratio is currency-free
    assert eur.cost_account == pytest.approx(usd.cost_account / EU, rel=1e-3)


def test_env_eur_account_and_optional_news(monkeypatch):
    monkeypatch.setenv("STATARB_ACCOUNT_CCY", "EUR")
    monkeypatch.setenv("STATARB_SYMBOL_SUFFIX", ".m")
    monkeypatch.setenv("STATARB_REQUIRE_NEWS_CALENDAR", "0")
    cfg = load_config()
    assert cfg.broker_symbol("EURUSD") == "EURUSD.m" and not cfg.require_news_calendar
    assert m.load_news(cfg, live=True) is not None                # no SystemExit
    monkeypatch.setenv("STATARB_REQUIRE_NEWS_CALENDAR", "1")
    monkeypatch.delenv("STATARB_NEWS_CSV", raising=False)
    with pytest.raises(SystemExit):
        m.load_news(load_config(), live=True)


class FakeBroker:
    """Enough of MT5Broker for the preflight."""

    def __init__(self, currency="EUR", demo=True, missing=()):
        self.currency, self.demo, self.missing = currency, demo, set(missing)
        rng = np.random.default_rng(0)
        n = 1600
        lx = np.log(NZ) + np.cumsum(rng.normal(0, 0.001, n))
        ly = 0.8 * lx + (np.log(AU) - 0.8 * np.log(NZ)) + rng.normal(0, 0.0005, n)
        idx = pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC")
        self.frames = {"AUDUSD": np.exp(ly), "NZDUSD": np.exp(lx)}
        self.idx = idx

    async def connect(self): pass
    async def shutdown(self): pass

    async def account_summary(self):
        return {"login": 1, "server": "MetaQuotes-Demo", "demo": self.demo,
                "currency": self.currency, "balance": 100_000.0, "equity": 100_000.0}

    async def symbol_info(self, s):
        if s in self.missing:
            raise BrokerError(f"symbol_select({s}) failed")
        return INFO

    async def get_tick(self, s):
        px = {"AUDUSD": AU, "NZDUSD": NZ, "EURUSD": EU}[s]
        return Tick(datetime.now(timezone.utc), px, px + 0.00005)

    async def get_rates(self, s, tf, count):
        c = self.frames[s][-count:]
        return pd.DataFrame({"open": c, "high": c, "low": c, "close": c}, index=self.idx[-count:])

    async def account_equity(self):
        return 100_000.0


def _check(cfg, broker):
    lines = []
    ok = asyncio.run(m.preflight(cfg, broker, echo=lines.append))
    return ok, "\n".join(lines)


def test_preflight_ready_on_eur_demo():
    cfg = dataclasses.replace(AppConfig(risk=RiskConfig(account_currency="EUR")),
                              require_news_calendar=False)
    ok, out = _check(cfg, FakeBroker())
    assert ok, out
    assert "READY" in out and "EURUSD" in out and "lots AUDUSD (BUY)" in out
    assert "blackouts OFF" in out


def test_preflight_lists_problems():
    cfg = AppConfig(risk=RiskConfig(account_currency="USD"))      # wrong currency, news needed
    ok, out = _check(cfg, FakeBroker(demo=False))
    assert not ok
    assert "REAL-money" in out and "STATARB_ACCOUNT_CCY=EUR" in out
    ok2, out2 = _check(dataclasses.replace(AppConfig(risk=RiskConfig(account_currency="EUR")),
                                           require_news_calendar=False),
                       FakeBroker(missing={"NZDUSD"}))
    assert not ok2 and "symbol NZDUSD" in out2
