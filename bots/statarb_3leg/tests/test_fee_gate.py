from datetime import datetime, timezone

import pytest

from bots.amd_fx.execution import Tick
from bots.statarb_3leg.config import FilterConfig
from bots.statarb_3leg.fee_gate import convert, evaluate, hedge_lots

T = datetime(2024, 3, 4, 10, tzinfo=timezone.utc)
EU, GU, BETA = 1.1000, 1.2700, 0.6


def ticks(eu_spr=0.2, gu_spr=0.5):
    return {"EURUSD": Tick(T, EU, EU + eu_spr * 1e-4), "GBPUSD": Tick(T, GU, GU + gu_spr * 1e-4)}


def gate(spread_log, cfg=FilterConfig(), **kw):
    return evaluate(spread_log, kw.pop("t", ticks()), cfg, "EURUSD", "GBPUSD", BETA, **kw)


def test_cost_in_y_pip_equivalents_matches_hand_calculation():
    g = gate(0.004, FilterConfig(commission_per_lot=7.0))
    x_lots = 0.6 * 1.1 / 1.27                                  # 0.5197 lots of GBPUSD
    # 1 lot EURUSD: pip value $10. EURUSD 0.2 pip -> $2 -> 0.2;
    # GBPUSD 0.5197 lot x 0.5 pip -> $2.60 -> 0.26; commission 7 x 1.5197 -> 1.064
    assert g.leg_cost_pips["EURUSD"] == pytest.approx(0.2, rel=1e-6)
    assert g.leg_cost_pips["GBPUSD"] == pytest.approx(x_lots * 0.5, rel=1e-4)
    assert g.leg_cost_pips["commission"] == pytest.approx(0.7 * (1 + x_lots), rel=1e-4)
    assert g.total_cost_pips == pytest.approx(sum(g.leg_cost_pips.values()), rel=1e-9)
    assert g.expected_reversion_pips == pytest.approx(0.004 * EU / 1e-4, rel=1e-3)   # ~44 pips
    assert g.passed and g.ratio > 25


def test_threshold():
    cfg = FilterConfig(min_edge_to_cost=2.5)
    cost = gate(0.001, cfg).total_cost_pips                       # ~1.52 pips
    needed = 2.5 * cost * 1e-4 / EU
    assert not gate(needed * 0.98, cfg).passed
    assert gate(needed * 1.02, cfg).passed


def test_ratio_does_not_depend_on_size():
    a = gate(0.003, lots={"EURUSD": 1.0, "GBPUSD": hedge_lots(1.0, BETA, EU, GU)})
    b = gate(0.003, lots={"EURUSD": 6.0, "GBPUSD": hedge_lots(6.0, BETA, EU, GU)})
    assert a.ratio == pytest.approx(b.ratio, rel=1e-9)
    assert b.cost_account == pytest.approx(6 * a.cost_account, rel=1e-9)


def test_wide_spread_rejects():
    g = gate(0.01, FilterConfig(max_leg_spread_pips=3.0), t=ticks(gu_spr=4.0))
    assert not g.passed and "GBPUSD" in g.reason


def test_account_currency_does_not_change_ratio():
    # commission is set in the account currency (EUR 7 != USD 7), so compare without it
    cfg = FilterConfig(commission_per_lot=0.0)
    usd = gate(0.003, cfg, account_ccy="USD")
    eur = gate(0.003, cfg, account_ccy="EUR")
    assert usd.ratio == pytest.approx(eur.ratio, rel=1e-9)
    assert eur.cost_account == pytest.approx(usd.cost_account / EU, rel=1e-3)


def test_convert_is_generic_over_usd_pairs():
    mids = {"EURUSD": 1.10, "GBPUSD": 1.27, "AUDUSD": 0.66, "USDJPY": 150.0}
    assert convert(100, "EUR", "USD", mids) == pytest.approx(110.0)
    assert convert(100, "AUD", "EUR", mids) == pytest.approx(60.0)
    assert convert(150, "JPY", "USD", mids) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        convert(1, "CHF", "USD", mids)
