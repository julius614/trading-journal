"""Triangle log-spread and an adaptive 1-D local-level Kalman filter (pure numpy).

Spread_t = ln(EURGBP) - ln(EURUSD / GBPUSD)

Model (local level):   mean_t = mean_{t-1} + w,  w ~ N(0, Q)
                       spread_t = mean_t + v,     v ~ N(0, R)

Z_t = (Spread_t - Mean_{t|t-1}) / sqrt(P_{t|t-1} + R_t)

The Z-score uses the *predicted* mean and the forecast-error variance (state uncertainty
plus observation noise). Using the state variance P alone would be wrong: P measures how
sure the filter is about the mean, shrinks towards zero, and would blow Z up. R is
estimated online (cumulative mean during warm-up, then an exponentially weighted mean of
squared innovations), and Q = q_ratio * R, so the filter adapts to changing noise.
Innovations are clipped at `clip_sigma` standard deviations for the noise estimate only, so
a single large dislocation doesn't inflate R for hundreds of bars and mute later signals;
the Z-score itself always uses the full innovation.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Optional, Union

import numpy as np
import pandas as pd

from .config import PIP

Number = Union[float, np.ndarray, pd.Series]


def synthetic_eurgbp(eurusd: Number, gbpusd: Number) -> Number:
    """EURGBP implied by the two USD pairs."""
    return eurusd / gbpusd


def log_spread(eurgbp: Number, eurusd: Number, gbpusd: Number) -> Number:
    """ln(EURGBP actual) - ln(synthetic EURGBP). Zero when the triangle is consistent."""
    return np.log(eurgbp) - np.log(synthetic_eurgbp(eurusd, gbpusd))


def deviation_pips(dev_log: float, eurgbp: float) -> float:
    """A log-spread deviation expressed in EURGBP pips."""
    return abs(dev_log) * eurgbp / PIP


@dataclass(frozen=True)
class KalmanOutput:
    spread: float
    mean: float          # predicted mean (before this observation)
    std: float           # forecast-error standard deviation
    z: float             # NaN during warm-up
    warm: bool

    @property
    def deviation(self) -> float:
        return self.spread - self.mean


class LocalLevelKalman:
    """Adaptive local-level Kalman filter with an online noise estimate."""

    def __init__(self, q_ratio: float = 1e-4, r_halflife: int = 288, warmup: int = 288,
                 clip_sigma: Optional[float] = 4.0) -> None:
        if q_ratio <= 0:
            raise ValueError("q_ratio must be positive")
        if r_halflife < 1 or warmup < 2:
            raise ValueError("r_halflife must be >= 1 and warmup >= 2")
        self.q_ratio = q_ratio
        self.alpha = 1.0 - 0.5 ** (1.0 / r_halflife)
        self.warmup = warmup
        self.clip_sigma = clip_sigma
        self.reset()

    def reset(self) -> None:
        self.mean = float("nan")
        self.p = 0.0
        self.r = 0.0
        self.n = 0
        self._sq_sum = 0.0

    @property
    def warm(self) -> bool:
        return self.n >= self.warmup

    def update(self, x: float) -> KalmanOutput:
        """Feed one spread observation; returns the Z-score computed BEFORE learning it."""
        x = float(x)
        if not math.isfinite(x):
            raise ValueError("spread observation must be finite")
        if self.n == 0:
            self.mean, self.p, self.n = x, 0.0, 1
            return KalmanOutput(x, x, float("nan"), float("nan"), False)

        q = self.q_ratio * self.r
        p_pred = self.p + q
        innov = x - self.mean
        s = p_pred + self.r
        std = math.sqrt(s) if s > 0 else float("nan")
        z = innov / std if self.warm and std and std > 0 else float("nan")
        out = KalmanOutput(x, self.mean, std, z, self.warm)

        # noise estimate: cumulative during warm-up, EWMA afterwards
        sq = innov * innov
        if self.clip_sigma is not None and self.n > 10 and s > 0:
            sq = min(sq, self.clip_sigma ** 2 * s)   # robust: cap outliers for the R update
        self._sq_sum += sq
        if self.n < self.warmup:
            self.r = self._sq_sum / self.n
        else:
            self.r = (1 - self.alpha) * self.r + self.alpha * max(sq - p_pred, 0.0)
        self.r = max(self.r, 1e-18)

        # Kalman update of the mean
        if self.n == 1:
            p_pred = self.r   # first mean (= first observation) is as uncertain as one obs
        s_new = p_pred + self.r
        k = p_pred / s_new if s_new > 0 else 0.0
        self.mean += k * innov
        self.p = (1 - k) * p_pred
        self.n += 1
        return out

    def run(self, spreads: Iterable[float]) -> pd.DataFrame:
        """Batch helper: feed a sequence; returns spread, mean, std, z per step."""
        rows = [self.update(x) for x in spreads]
        return pd.DataFrame({"spread": [r.spread for r in rows], "mean": [r.mean for r in rows],
                             "std": [r.std for r in rows], "z": [r.z for r in rows]})
