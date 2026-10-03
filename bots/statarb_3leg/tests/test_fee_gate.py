from datetime import datetime, timezone

import pytest

from bots.amd_fx.execution import Tick
from bots.statarb_3leg.config import FilterConfig
from bots.statarb_3leg.fee_gate import convert, evaluate, neutral_lots

T = datetime(2024, 3, 4, 10, tzinfo=timezone.utc)
EU, GU = 1.1000, 1.2700
EG = EU / GU                                   # 0.866142


def ticks(eu_spr=0.2, gu_spr=0.5, eg_spr=0.6):
    return {
        "EURUSD": Tick(T, EU, EU + eu_spr * 1e-4),
        "GBPUSD": Tick(T, GU, GU + gu_spr * 1e-4),
        "EURGBP": Tick(T, EG, EG + eg_spr * 1e-4),
    }


def test_cost_in_eurgbp_pips_matches_hand_calculation():
    cfg = FilterConfig(commission_per_lot=7.0)
    g = evaluate(5e-4, ticks(), cfg, "USD")
    # per 1 EURGBP lot (pip value = 10 GBP = 12.70 USD):
    #   EURGBP 0.6 pip -> 0.60 pips; EURUSD 1 lot x 0.2 pip = $2 -> 0.157;
    #   GBPUSD 0.866 lot x 0.5 pip = $4.33 -> 0.341; commission 7 x 2.866 = $20.06 -> 1.580
    assert g.leg_cost_pips["EURGBP"] == pytest.approx(0.6, rel=1e-6)
    assert g.leg_cost_pips["EURUSD"] == pytest.approx(2.0 / 12.7, rel=1e-4)
    assert g.leg_cost_pips["GBPUSD"] == pytest.approx(EG * 5 / 12.7, rel=1e-4)
    assert g.leg_cost_pips["commission"] == pytest.approx(7 * (2 + EG) / 12.7, rel=1e-4)
    assert g.total_cost_pips == pytest.approx(sum(g.leg_cost_pips.values()), rel=1e-9)
    # expected reversion = |dev| x EURGBP / pip (mid-price based)
    assert g.expected_reversion_pips == pytest.approx(5e-4 * EG / 1e-4, rel=1e-3)


def test_gate_threshold():
    cfg = FilterConfig(commission_per_lot=7.0, min_edge_to_cost=2.5)
    cost = evaluate(1e-4, ticks(), cfg).total_cost_pips          # ~2.68 pips
    needed_log = 2.5 * cost * 1e-4 / EG
    assert not evaluate(needed_log * 0.98, ticks(), cfg).passed
    assert evaluate(needed_log * 1.02, ticks(), cfg).passed
    small = evaluate(1e-5, ticks(), cfg)                          # a typical 0.1-pip wobble
    assert not small.passed and "edge/cost" in small.reason


def test_ratio_does_not_depend_on_size():
    cfg = FilterConfig()
    a = evaluate(8e-4, ticks(), cfg, lots=neutral_lots(1.0, EG))
    b = evaluate(8e-4, ticks(), cfg, lots=neutral_lots(7.0, EG))
    assert a.ratio == pytest.approx(b.ratio, rel=1e-9)
    assert b.cost_account == pytest.approx(7 * a.cost_account, rel=1e-9)


def test_wide_leg_spread_rejects():
    g = evaluate(5e-3, ticks(eg_spr=4.0), FilterConfig(max_leg_spread_pips=3.0))
    assert not g.passed and "EURGBP" in g.reason


def test_account_currency_does_not_change_ratio():
    cfg = FilterConfig(commission_per_lot=0.0)
    usd = evaluate(8e-4, ticks(), cfg, "USD")
    eur = evaluate(8e-4, ticks(), cfg, "EUR")
    assert usd.ratio == pytest.approx(eur.ratio, rel=1e-9)
    assert eur.cost_account == pytest.approx(usd.cost_account / EU, rel=1e-3)


def test_convert_round_trip():
    mids = {"EURUSD": EU, "GBPUSD": GU, "EURGBP": EG}
    assert convert(100, "EUR", "USD", mids) == pytest.approx(110.0)
    assert convert(convert(100, "GBP", "EUR", mids), "EUR", "GBP", mids) == pytest.approx(100.0)
    with pytest.raises(ValueError):
        convert(1, "JPY", "USD", mids)
