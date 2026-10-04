import pytest

from bots.amd_fx.execution import SymbolInfo
from bots.statarb_3leg.config import AppConfig, RiskConfig, validate_pair
from bots.statarb_3leg.risk_manager import balance_legs, currency_exposure

EU, GU = 1.1000, 1.2700
MIDS = {"EURUSD": EU, "GBPUSD": GU}
INFO = {s: SymbolInfo(s, 5, 1e-5, 1e-5, 1.0, 0.01, 100.0, 0.01) for s in MIDS}


def plan(direction=1, equity=110_000.0, beta=0.6, **risk):
    legs = balance_legs(direction, equity, MIDS, INFO, RiskConfig(**risk), "EURUSD", "GBPUSD", beta)
    return {p.symbol: p for p in legs}


def test_long_spread_buys_y_sells_x():
    p = plan(1)
    assert (p["EURUSD"].side, p["GBPUSD"].side) == (1, -1)
    assert p["EURUSD"].lots == pytest.approx(1.00)                   # $110k notional
    assert p["GBPUSD"].lots == pytest.approx(round(0.6 * EU / GU, 2))   # beta-weighted: 0.52


def test_short_spread_is_mirror():
    p = plan(-1)
    assert (p["EURUSD"].side, p["GBPUSD"].side) == (-1, 1)


def test_negative_beta_trades_both_legs_same_way():
    p = plan(1, beta=-0.5)
    assert (p["EURUSD"].side, p["GBPUSD"].side) == (1, 1)


def test_notionals_follow_beta():
    p = plan(1, equity=1_000_000.0, beta=0.8)
    y_usd = p["EURUSD"].lots * 100_000 * EU
    x_usd = p["GBPUSD"].lots * 100_000 * GU
    assert x_usd / y_usd == pytest.approx(0.8, rel=0.005)


def test_exposure_is_long_eur_short_gbp():
    legs = balance_legs(1, 110_000.0, MIDS, INFO, RiskConfig(), "EURUSD", "GBPUSD", 0.6)
    exp = currency_exposure(legs, MIDS)
    assert exp["EUR"] == pytest.approx(110_000.0)
    assert exp["GBP"] == pytest.approx(-0.52 * 100_000 * GU)


def test_rounding_cap_and_minimum():
    assert plan(1, equity=12_345.0)["EURUSD"].lots == pytest.approx(0.11)
    assert plan(1, equity=1e9, max_lots_per_leg=5.0)["EURUSD"].lots == pytest.approx(5.0)
    assert balance_legs(1, 500.0, MIDS, INFO, RiskConfig(), "EURUSD", "GBPUSD", 0.6) == []


def test_eur_account():
    assert plan(1, equity=100_000.0, account_currency="EUR")["EURUSD"].lots == pytest.approx(1.0)


def test_invalid_inputs():
    with pytest.raises(ValueError):
        balance_legs(0, 1000.0, MIDS, INFO, RiskConfig(), "EURUSD", "GBPUSD", 0.6)
    with pytest.raises(ValueError):
        balance_legs(1, 1000.0, MIDS, INFO, RiskConfig(), "EURUSD", "GBPUSD", 0.0)


def test_pair_validation():
    validate_pair(("AUDUSD", "NZDUSD"), "USD")
    with pytest.raises(ValueError):
        validate_pair(("EURUSD", "EURGBP"), "USD")       # EURGBP isn't quoted in USD
    validate_pair(("EURUSD", "GBPUSD"), "JPY")          # any account currency (via USDJPY)
    with pytest.raises(ValueError):
        validate_pair(("EURUSD", "GBPUSD"), "JP")
    with pytest.raises(ValueError):
        AppConfig(pair=("EURUSD", "EURUSD"))
