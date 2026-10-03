import pytest

from bots.amd_fx.execution import SymbolInfo
from bots.statarb_3leg.config import RiskConfig
from bots.statarb_3leg.risk_manager import balance_legs, currency_exposure

EU, GU = 1.1000, 1.2700
MIDS = {"EURUSD": EU, "GBPUSD": GU, "EURGBP": EU / GU}
INFO = {s: SymbolInfo(s, 5, 1e-5, 1e-5, 1.0, 0.01, 100.0, 0.01) for s in MIDS}


def plan(direction=1, equity=110_000.0, **risk):
    return {p.symbol: p for p in balance_legs(direction, equity, MIDS, INFO, RiskConfig(**risk))}


def test_long_spread_sides_and_sizes():
    p = plan(1)
    # $110k equity x 1.0 = EUR 100k = 1.00 lot of EUR on both EUR legs
    assert (p["EURGBP"].side, p["EURUSD"].side, p["GBPUSD"].side) == (1, -1, 1)
    assert p["EURGBP"].lots == p["EURUSD"].lots == pytest.approx(1.00)
    assert p["GBPUSD"].lots == pytest.approx(round(EU / GU, 2))      # 0.87


def test_short_spread_is_mirror():
    p = plan(-1)
    assert (p["EURGBP"].side, p["EURUSD"].side, p["GBPUSD"].side) == (-1, 1, -1)


def test_book_is_currency_neutral():
    plans = balance_legs(1, 1_000_000.0, MIDS, INFO, RiskConfig())   # big: rounding small
    exp = currency_exposure(plans, MIDS, "USD")
    notional = 1_000_000.0
    assert abs(exp["EUR"]) < 1e-6                                     # exactly zero
    assert abs(exp["GBP"]) / notional < 0.001                        # lot rounding only
    assert abs(exp["USD"]) / notional < 0.001


def test_notional_multiplier_and_cap():
    assert plan(1, notional_equity_mult=0.5)["EURGBP"].lots == pytest.approx(0.50)
    assert plan(1, equity=1e9, max_lots_per_leg=5.0)["EURUSD"].lots == pytest.approx(5.0)


def test_lots_round_down_to_step():
    p = plan(1, equity=12_345.0)                                       # EUR 11,222.7
    assert p["EURGBP"].lots == pytest.approx(0.11)


def test_too_small_returns_nothing():
    assert balance_legs(1, 500.0, MIDS, INFO, RiskConfig()) == []


def test_eur_account():
    p = plan(1, equity=100_000.0, account_currency="EUR")
    assert p["EURGBP"].lots == pytest.approx(1.00)


def test_invalid_direction():
    with pytest.raises(ValueError):
        balance_legs(0, 1000.0, MIDS, INFO, RiskConfig())
