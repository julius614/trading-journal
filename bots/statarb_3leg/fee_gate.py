"""Real-time 3-leg cost gate and currency conversion helpers.

The gate compares the profit expected if the spread reverts to its Kalman mean with the
full round-trip cost of trading all three legs:

    Expected_Reversion_Pips = |Spread - Mean| in EURGBP pips
    Total_Cost_Pips         = (spread cost of each leg + commissions), in EURGBP pips
    pass if Expected_Reversion_Pips / Total_Cost_Pips >= min_edge_to_cost (2.5)

Pips of different pairs are different amounts of money, so a raw sum of the three leg
spreads would mix currencies. Each cost is priced in the account currency for the actual
position sizes and converted to "EURGBP-pip equivalents" (money / value of one pip on the
EURGBP leg). For the dollar-neutral book (EURGBP N, EURUSD N, GBPUSD N x EURGBP lots) the
book's P&L for a spread change d is N x 100,000 EUR x d, so expected reversion in those
units is exactly |d| x EURGBP / 0.0001.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Mapping, Optional

from ..amd_fx.execution import Tick
from .config import CONTRACT_SIZE, PIP, FilterConfig

CURRENCIES = ("USD", "EUR", "GBP")


def mids_from_ticks(ticks: Mapping[str, Tick]) -> Dict[str, float]:
    return {s: (t.bid + t.ask) / 2.0 for s, t in ticks.items()}


def usd_per_unit(ccy: str, mids: Mapping[str, float]) -> float:
    """Value of 1 unit of `ccy` in USD, from the triangle's mid prices."""
    if ccy == "USD":
        return 1.0
    if ccy == "EUR":
        return mids["EURUSD"]
    if ccy == "GBP":
        return mids["GBPUSD"]
    raise ValueError(f"unsupported currency {ccy}")


def convert(amount: float, from_ccy: str, to_ccy: str, mids: Mapping[str, float]) -> float:
    """Convert between USD, EUR and GBP using the triangle's mids."""
    if from_ccy == to_ccy:
        return amount
    return amount * usd_per_unit(from_ccy, mids) / usd_per_unit(to_ccy, mids)


def quote_ccy(symbol: str) -> str:
    return symbol[3:6]


def base_ccy(symbol: str) -> str:
    return symbol[:3]


def neutral_lots(n: float, eurgbp: float) -> Dict[str, float]:
    """Unrounded dollar-neutral lot sizes for a book of n EURGBP lots."""
    return {"EURGBP": n, "EURUSD": n, "GBPUSD": n * eurgbp}


@dataclass(frozen=True)
class GateResult:
    passed: bool
    reason: str
    expected_reversion_pips: float
    total_cost_pips: float
    ratio: float
    expected_account: float
    cost_account: float
    leg_cost_pips: Dict[str, float] = field(default_factory=dict)
    leg_spread_pips: Dict[str, float] = field(default_factory=dict)


def evaluate(
    deviation_log: float,
    ticks: Mapping[str, Tick],
    cfg: FilterConfig,
    account_ccy: str = "USD",
    lots: Optional[Mapping[str, float]] = None,
) -> GateResult:
    """Decide whether a signal's expected reversion covers 3-leg costs by the margin.

    `deviation_log` is Spread - Kalman mean (log units). `ticks` holds live bid/ask for
    EURUSD, GBPUSD and EURGBP. `lots` are the planned sizes; by default a 1-lot neutral
    book is assumed (the ratio does not depend on size, apart from lot rounding).
    """
    mids = mids_from_ticks(ticks)
    sizes = dict(lots) if lots else neutral_lots(1.0, mids["EURGBP"])
    spreads = {s: (ticks[s].ask - ticks[s].bid) / PIP for s in ticks}

    eg_pip_value = convert(sizes["EURGBP"] * CONTRACT_SIZE * PIP, "GBP", account_ccy, mids)
    leg_cost_account = {
        s: convert(sizes[s] * CONTRACT_SIZE * (ticks[s].ask - ticks[s].bid), quote_ccy(s),
                   account_ccy, mids)
        for s in ("EURUSD", "GBPUSD", "EURGBP")
    }
    commission = cfg.commission_per_lot * sum(sizes.values())
    cost_account = sum(leg_cost_account.values()) + commission
    expected_account = convert(sizes["EURGBP"] * CONTRACT_SIZE * abs(deviation_log), "EUR",
                               account_ccy, mids)

    leg_cost_pips = {s: v / eg_pip_value for s, v in leg_cost_account.items()}
    leg_cost_pips["commission"] = commission / eg_pip_value
    total_cost_pips = cost_account / eg_pip_value
    expected_pips = expected_account / eg_pip_value
    ratio = expected_pips / total_cost_pips if total_cost_pips > 0 else float("inf")

    wide = [s for s, sp in spreads.items() if sp > cfg.max_leg_spread_pips]
    if wide:
        reason = f"spread too wide on {', '.join(wide)}"
        passed = False
    elif ratio < cfg.min_edge_to_cost:
        reason = f"edge/cost {ratio:.2f} < {cfg.min_edge_to_cost:.2f}"
        passed = False
    else:
        reason, passed = "ok", True
    return GateResult(passed, reason, expected_pips, total_cost_pips, ratio,
                      expected_account, cost_account, leg_cost_pips, spreads)
