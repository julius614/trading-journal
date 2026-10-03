"""Rolling cointegration gate: Engle-Granger test and mean-reversion half-life
(pure numpy, no statsmodels).

Entries are allowed only while the recent relationship actually behaves like a
mean-reverting one: Engle-Granger p-value < max_pvalue AND half-life < max_half_life bars.

Engle-Granger over the last `window` bars: regress y on x (with a constant) to get the
window's hedge ratio, then ADF-test the residuals using MacKinnon's cointegration p-values
(N=2), which are stricter than plain ADF because the hedge ratio was estimated.
Not used: the Kalman filter's current beta (it wanders, and a small error mixes the
random-walking x leg into the spread, so a genuinely cointegrated pair fails) and the
Kalman innovations (biased towards "stationary", because the adaptive fair value absorbs
drift by construction).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

# MacKinnon (1994) p-value surfaces for the tau statistic, constant term; N = number of
# variables (1 = plain ADF, 2 = Engle-Granger residuals of a 2-variable regression).
# Same coefficients as statsmodels.tsa.adfvalues.mackinnonp (regression "c").
_TABLES = {
    1: dict(tau_max=2.74, tau_min=-18.83, tau_star=-1.61,
            small=(2.1659, 1.4412, 0.038269), large=(1.7339, 0.93202, -0.12745, -0.010368)),
    2: dict(tau_max=0.92, tau_min=-18.86, tau_star=-2.62,
            small=(2.92, 1.5012, 0.039796), large=(2.1945, 0.64695, -0.29198, -0.042377)),
}


def _norm_cdf(v: float) -> float:
    return 0.5 * (1.0 + math.erf(v / math.sqrt(2.0)))


def mackinnon_pvalue(tau: float, n_vars: int = 1) -> float:
    """Approximate p-value of a tau statistic (constant, no trend) for N = n_vars."""
    t = _TABLES[n_vars]
    if not math.isfinite(tau):
        return float("nan")
    if tau > t["tau_max"]:
        return 1.0
    if tau < t["tau_min"]:
        return 0.0
    coef = t["small"] if tau <= t["tau_star"] else t["large"]
    return _norm_cdf(sum(c * tau ** i for i, c in enumerate(coef)))


@dataclass(frozen=True)
class ADFResult:
    stat: float
    pvalue: float
    lags: int
    nobs: int


def adf_test(series: np.ndarray, max_lags: Optional[int] = None, constant: bool = True,
             n_vars: int = 1) -> ADFResult:
    """ADF test: dx_t = [a +] g x_{t-1} + sum_i phi_i dx_{t-i} + e.

    The lag count is chosen by AIC up to max_lags (default: Schwert's
    12 * (n/100)^(1/4)). Returns the t-statistic of g and its MacKinnon p-value.
    """
    x = np.asarray(series, dtype=float)
    if x.ndim != 1 or len(x) < 20 or not np.all(np.isfinite(x)):
        raise ValueError("need a finite 1-D series of at least 20 points")
    n = len(x)
    if max_lags is None:
        max_lags = int(math.ceil(12.0 * (n / 100.0) ** 0.25))
    max_lags = max(0, min(max_lags, n // 4))
    dx = np.diff(x)

    def fit(k: int, start: int):
        y = dx[start:]
        cols = ([np.ones_like(y)] if constant else []) + [x[start:-1]]
        for i in range(1, k + 1):
            cols.append(dx[start - i:-i])
        X = np.column_stack(cols)
        coef, _, rank, _ = np.linalg.lstsq(X, y, rcond=None)
        if rank < X.shape[1]:
            return None
        resid = y - X @ coef
        return X, coef, resid

    # choose the lag by AIC on a common sample, then re-fit that lag on all usable data
    best_k, best_aic = None, None
    for k in range(max_lags + 1):
        res = fit(k, max_lags)
        if res is None:
            continue
        X, _, resid = res
        m, p = X.shape
        aic = m * math.log(resid @ resid / m) + 2 * p
        if best_aic is None or aic < best_aic:
            best_k, best_aic = k, aic
    if best_k is None:
        raise ValueError("ADF regression is singular (constant series?)")
    res = fit(best_k, best_k)
    if res is None:
        raise ValueError("ADF regression is singular (constant series?)")
    X, coef, resid = res
    m, p = X.shape
    g = 1 if constant else 0                          # column of x_{t-1}
    sigma2 = resid @ resid / (m - p)
    var_g = sigma2 * np.linalg.inv(X.T @ X)[g, g]
    stat = coef[g] / math.sqrt(var_g) if var_g > 0 else float("nan")
    return ADFResult(float(stat), mackinnon_pvalue(float(stat), n_vars), best_k, m)


def half_life(series: np.ndarray) -> float:
    """Mean-reversion half-life in bars from an AR(1) fit: dx_t = a + b x_{t-1}.

    half-life = -ln 2 / ln(1 + b); infinite if the series doesn't revert (b >= 0).
    """
    x = np.asarray(series, dtype=float)
    if len(x) < 10:
        raise ValueError("need at least 10 points")
    dx = np.diff(x)
    X = np.column_stack([np.ones(len(dx)), x[:-1]])
    (a, b), *_ = np.linalg.lstsq(X, dx, rcond=None)
    if b <= -1:
        return 0.0
    lb = math.log1p(b) if b < 0 else 0.0
    if lb >= 0.0:                     # b >= 0, or so close to 0 that it rounds away
        return float("inf")
    return float(-math.log(2.0) / lb)


@dataclass(frozen=True)
class EngleGranger:
    beta: float
    alpha: float
    stat: float
    pvalue: float
    residuals: np.ndarray


def engle_granger(log_y: np.ndarray, log_x: np.ndarray) -> EngleGranger:
    """Two-step Engle-Granger: OLS y = alpha + beta x, then ADF on the residuals (no
    constant, AIC lags) with MacKinnon N=2 p-values - as statsmodels.tsa.stattools.coint."""
    y = np.asarray(log_y, dtype=float)
    x = np.asarray(log_x, dtype=float)
    X = np.column_stack([np.ones(len(x)), x])
    (alpha, beta), *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - alpha - beta * x
    adf = adf_test(resid, constant=False, n_vars=2)
    return EngleGranger(float(beta), float(alpha), adf.stat, adf.pvalue, resid)


@dataclass(frozen=True)
class GateCheck:
    passed: bool
    pvalue: float
    half_life: float
    beta: float
    reason: str


def stationarity_gate(log_y: np.ndarray, log_x: np.ndarray, max_pvalue: float,
                      max_half_life: float) -> GateCheck:
    """Engle-Granger p-value and residual half-life over the given window."""
    try:
        eg = engle_granger(log_y, log_x)
        hl = half_life(eg.residuals)
    except (ValueError, np.linalg.LinAlgError) as exc:
        return GateCheck(False, float("nan"), float("nan"), float("nan"),
                         f"cointegration test failed: {exc}")
    if not eg.pvalue < max_pvalue:
        return GateCheck(False, eg.pvalue, hl, eg.beta,
                         f"not cointegrated (Engle-Granger p={eg.pvalue:.3f} >= {max_pvalue})")
    if not hl < max_half_life:
        return GateCheck(False, eg.pvalue, hl, eg.beta,
                         f"half-life {hl:.0f} bars >= {max_half_life:.0f}")
    return GateCheck(True, eg.pvalue, hl, eg.beta, "ok")
