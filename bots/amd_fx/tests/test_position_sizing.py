import pytest

from bots.amd_fx.risk_manager import pip_value_per_lot, position_size

EURUSD = dict(tick_size=0.00001, tick_value=1.0, volume_step=0.01, volume_min=0.01, volume_max=100.0)


def test_one_percent_risk_over_20_pips():
    # $10,000 x 1% = $100; 20 pips x $10/pip/lot = $200 per lot -> 0.50 lots
    assert position_size(10_000, 0.01, 1.1000, 1.0980, **EURUSD) == pytest.approx(0.50)


def test_risk_never_exceeds_target_after_rounding():
    lots = position_size(10_000, 0.01, 1.1000, 1.09781, **EURUSD)   # 21.9 pips
    assert lots == pytest.approx(0.45)   # 0.4566 rounded DOWN
    assert lots * 21.9 * 10 <= 100.0


def test_short_side_uses_absolute_distance():
    assert position_size(10_000, 0.01, 1.0980, 1.1000, **EURUSD) == pytest.approx(0.50)


def test_below_minimum_lot_returns_zero():
    # $100 account, 1% = $1; 50 pips at 0.01 lot = $5 -> can't trade
    assert position_size(100, 0.01, 1.1000, 1.0950, **EURUSD) == 0.0


def test_capped_at_volume_max():
    lots = position_size(10_000_000, 0.01, 1.1000, 1.0999, **EURUSD)
    assert lots == 100.0


def test_respects_volume_step():
    lots = position_size(10_000, 0.01, 1.1000, 1.0980, tick_size=0.00001, tick_value=1.0,
                         volume_step=0.1, volume_min=0.1, volume_max=50)
    assert lots == pytest.approx(0.5)
    lots = position_size(10_000, 0.01, 1.1000, 1.0970, tick_size=0.00001, tick_value=1.0,
                         volume_step=0.1, volume_min=0.1, volume_max=50)
    assert lots == pytest.approx(0.3)   # 0.333 -> 0.3


def test_jpy_style_contract():
    # USDJPY-like: tick 0.001, tick_value ~0.67 USD; 20 pips = 0.20
    lots = position_size(10_000, 0.01, 150.00, 149.80, tick_size=0.001, tick_value=0.67)
    assert lots == pytest.approx(0.74)   # 100 / (200 ticks * 0.67) = 0.746


@pytest.mark.parametrize("kwargs", [
    dict(equity=0, risk_fraction=0.01, entry=1.1, stop=1.09),
    dict(equity=1000, risk_fraction=0.0, entry=1.1, stop=1.09),
    dict(equity=1000, risk_fraction=0.01, entry=1.1, stop=1.1),
])
def test_invalid_inputs_raise(kwargs):
    with pytest.raises(ValueError):
        position_size(**kwargs, tick_size=0.00001, tick_value=1.0)


def test_pip_value():
    assert pip_value_per_lot(0.0001, 0.00001, 1.0) == pytest.approx(10.0)
