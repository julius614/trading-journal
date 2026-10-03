"""Real-time 2-leg cost gate and currency conversion helpers.

For a pair book (y leg notional V, x leg notional beta x V, opposite sides) the P&L for a
spread change d is V x d, so if the spread reverts to its fair value the expected profit is
|spread| x V. The gate compares that with the full round-trip cost of both legs:

    Expected_Reversion_Pips = |spread| in y-leg pips
    Total_Cost_Pips         = (spread cost of each leg + commissions), in y-leg pips
    pass if Expected_Reversion_Pips / Total_Cost_Pips >= min_edge_to_cost (2.5)

Costs are priced in the account currency for the actual lot sizes, then divided by the
value of one pip on the y leg ("y-pip equivalents"), so the two legs' pips - which are
different amounts of money - are added correctly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Mapping, Optional

from ..amd_fx.execution import Tick
from .config import CONTRACT_SIZE, PIP, FilterConfig


def mids_from_ticks(ticks: Mapping[str, Tick]) -> Dict[str, float]:
    return {s: (t.bid + t.ask) / 2.0 for s, t in ticks.items()}


def quote_ccy(symbol: str) -> str:
    return symbol[3:6]


def base_ccy(symbol: str) -> str:
    return symbol[:3]


def usd_per_unit(ccy: str, mids: Mapping[str, float]) -> float:
    """Value of 1 unit of `ccy` in USD, from any XXXUSD or USDXXX price in `mids`."""
    if ccy == "USD":
        return 1.0
    if f"{ccy}USD" in mids:
        return mids[f"{ccy}USD"]
    if f"USD{ccy}" in mids:
        return 1.0 / mids[f"USD{ccy}"]
    raise ValueError(f"no price available to convert {ccy}")


def convert(amount: float, from_ccy: str, to_ccy: str, mids: Mapping[str, float]) -> float:
    if from_ccy == to_ccy:
        return amount
    return amount * usd_per_unit(from_ccy, mids) / usd_per_unit(to_ccy, mids)


def hedge_lots(n_y: float, beta: float, y_price: float, x_price: float) -> float:
    """Unrounded x-leg lots for n_y lots of y: x notional = beta x y notional (in USD)."""
    return n_y * beta * y_price / x_price


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
    spread_log: float,
    ticks: Mapping[str, Tick],
    cfg: FilterConfig,
    y: str,
    x: str,
    beta: float,
    account_ccy: str = "USD",
    lots: Optional[Mapping[str, float]] = None,
) -> GateResult:
    """Decide whether the expected reversion covers both legs' costs by the margin.

    `spread_log` is the Kalman innovation (y - beta x - alpha, log units). `lots` are the
    planned sizes; by default 1 lot of y and the beta-weighted x lots (the ratio does not
    depend on size, apart from lot rounding).
    """
    mids = mids_from_ticks(ticks)
    sizes = dict(lots) if lots else {y: 1.0, x: hedge_lots(1.0, abs(beta), mids[y], mids[x])}
    spreads = {s: (ticks[s].ask - ticks[s].bid) / PIP for s in (y, x)}

    y_pip_value = convert(sizes[y] * CONTRACT_SIZE * PIP, quote_ccy(y), account_ccy, mids)
    leg_cost_account = {
        s: convert(sizes[s] * CONTRACT_SIZE * (ticks[s].ask - ticks[s].bid), quote_ccy(s),
                   account_ccy, mids)
        for s in (y, x)
    }
    commission = cfg.commission_per_lot * (sizes[y] + sizes[x])
    cost_account = sum(leg_cost_account.values()) + commission
    y_notional = sizes[y] * CONTRACT_SIZE * mids[y]          # in y's quote currency
    expected_account = convert(y_notional * abs(spread_log), quote_ccy(y), account_ccy, mids)

    leg_cost_pips = {s: v / y_pip_value for s, v in leg_cost_account.items()}
    leg_cost_pips["commission"] = commission / y_pip_value
    total_cost_pips = cost_account / y_pip_value
    expected_pips = expected_account / y_pip_value
    ratio = expected_pips / total_cost_pips if total_cost_pips > 0 else float("inf")

    wide = [s for s, sp in spreads.items() if sp > cfg.max_leg_spread_pips]
    if wide:
        reason, passed = f"spread too wide on {', '.join(wide)}", False
    elif ratio < cfg.min_edge_to_cost:
        reason, passed = f"edge/cost {ratio:.2f} < {cfg.min_edge_to_cost:.2f}", False
    else:
        reason, passed = "ok", True
    return GateResult(passed, reason, expected_pips, total_cost_pips, ratio,
                      expected_account, cost_account, leg_cost_pips, spreads)
