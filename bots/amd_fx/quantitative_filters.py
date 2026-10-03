"""Statistical filters: 1-D Kalman filter, Kalman Z-score, ATR and a volatility-spike check.

Every function is causal: a value at bar t uses only bars up to t, so the filters give the
same answer in a backtest as they would live.
"""
from __future__ import annotations

from typing import Optional, Tuple, Union

import numpy as np
import pandas as pd

ArrayLike = Union[np.ndarray, pd.Series, list]


def kalman_filter_1d(
    prices: ArrayLike,
    q_ratio: float = 0.01,
    measurement_var: Optional[float] = None,
) -> np.ndarray:
    """Local-level (random-walk) Kalman filter.

    State: x_t = x_{t-1} + w,  w ~ N(0, Q).  Observation: z_t = x_t + v,  v ~ N(0, R).
    R defaults to the variance of price changes in the input; Q = q_ratio * R.
    A smaller q_ratio gives a smoother, slower estimate.

    Returns the filtered estimate for every bar.
    """
    z = np.asarray(prices, dtype=float)
    if z.ndim != 1 or len(z) == 0:
        raise ValueError("prices must be a non-empty 1-D sequence")
    if q_ratio <= 0:
        raise ValueError("q_ratio must be positive")
    r = measurement_var
    if r is None:
        diffs = np.diff(z)
        r = float(np.var(diffs)) if len(diffs) > 1 else 0.0
    r = max(r, 1e-12)
    q = q_ratio * r

    out = np.empty_like(z)
    x, p = z[0], r
    for i, obs in enumerate(z):
        p += q                      # predict
        k = p / (p + r)             # Kalman gain
        x += k * (obs - x)          # update
        p *= 1.0 - k
        out[i] = x
    return out


def kalman_zscore(
    close: pd.Series,
    window: int = 50,
    q_ratio: float = 0.01,
) -> pd.Series:
    """Z-score of price against its Kalman estimate.

    z_t = (close_t - kalman_t) / std(residuals over the last `window` bars).
    NaN until `window` residuals exist, or where the residual std is zero.
    """
    if window < 2:
        raise ValueError("window must be at least 2")
    est = kalman_filter_1d(close.to_numpy(dtype=float), q_ratio=q_ratio)
    resid = close.astype(float) - est
    std = resid.rolling(window, min_periods=window).std()
    z = resid / std.replace(0.0, np.nan)
    return z.rename("zscore")


def atr(bars: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range with Wilder smoothing. Needs high/low/close columns."""
    prev_close = bars["close"].shift(1)
    tr = pd.concat(
        [
            bars["high"] - bars["low"],
            (bars["high"] - prev_close).abs(),
            (bars["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean().rename("atr")


def volatility_spike(
    close: pd.Series,
    short: int = 3,
    long: int = 20,
    mult: float = 1.3,
) -> Tuple[bool, float]:
    """Check whether recent volatility is expanding.

    Compares the std of the last `short` log returns with the std of the `long` returns
    before them. Returns (spike, ratio); spike is True when ratio > mult.
    """
    rets = np.log(close.astype(float)).diff().dropna()
    if len(rets) < short + long or short < 2:
        return False, float("nan")
    recent = rets.iloc[-short:].std()
    base = rets.iloc[-(short + long):-short].std()
    if not np.isfinite(base) or base == 0:
        return False, float("nan")
    ratio = float(recent / base)
    return ratio > mult, ratio


def range_within_atr(range_size: float, atr_value: Optional[float], mult: float = 2.0) -> bool:
    """True when the range is no wider than `mult` x ATR.

    Fails safe: returns False when the ATR isn't available, so the day is skipped.
    """
    if atr_value is None or not np.isfinite(atr_value) or atr_value <= 0:
        return False
    return range_size <= mult * atr_value
