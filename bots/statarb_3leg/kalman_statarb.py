"""Dynamic hedge ratio for a 2-leg pair: an adaptive 2-state Kalman filter (pure numpy).

Model on log prices, y = ln(Y), x = ln(X):

    state   theta_t = [beta_t, alpha_t]      theta_t = theta_{t-1} + w,  w ~ N(0, Q)
    obs     y_t = beta_t * x_t + alpha_t + v,                            v ~ N(0, R)

Each bar:  H = [x_t, 1],  P_pred = P + Q,  e = y_t - H theta,  S = H P_pred H' + R
           Z_t = e / sqrt(S)

e is the spread (how far Y is from its hedge-ratio fair value) and S is the full forecast
variance: state uncertainty projected through H plus observation noise, i.e. the
sqrt(P + R) form. Using P alone would be wrong - it shrinks towards 0 and inflates Z.
R is estimated online (cumulative mean during warm-up, then an exponentially weighted mean
of squared innovations); innovations beyond `clip_sigma` standard deviations are capped for
the R update only, so one shock doesn't inflate R and mute later signals. Q = diag(q_beta,
q_alpha) * R, so the hedge ratio adapts at a pace relative to the current noise.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Optional, Tuple

import numpy as np
import pandas as pd

from .config import PIP


def spread_pips(spread_log: float, y_price: float) -> float:
    """A log spread expressed in pips of the y leg."""
    return abs(spread_log) * y_price / PIP


@dataclass(frozen=True)
class HedgeOutput:
    beta: float          # hedge ratio used for this bar's forecast (before the update)
    alpha: float
    spread: float        # innovation e = y - (beta x + alpha), log units
    std: float           # sqrt(S): forecast-error standard deviation
    z: float             # NaN during warm-up
    warm: bool


class KalmanHedgeRatio:
    """Adaptive Kalman filter for y = beta * x + alpha."""

    def __init__(self, q_beta: float = 1e-5, q_alpha: float = 1e-5, r_halflife: int = 500,
                 warmup: int = 500, clip_sigma: Optional[float] = 4.0,
                 init_var: float = 1.0) -> None:
        if q_beta <= 0 or q_alpha <= 0:
            raise ValueError("q_beta and q_alpha must be positive")
        if r_halflife < 1 or warmup < 3:
            raise ValueError("r_halflife must be >= 1 and warmup >= 3")
        self.q = np.diag([q_beta, q_alpha])
        self.alpha_ewm = 1.0 - 0.5 ** (1.0 / r_halflife)
        self.warmup = warmup
        self.clip_sigma = clip_sigma
        self.init_var = init_var
        self.reset()

    def reset(self) -> None:
        self.theta = np.zeros(2)            # [beta, alpha]
        self.P = np.eye(2) * self.init_var  # very uncertain start
        self.r = 0.0
        self.n = 0
        self._sq_sum = 0.0

    @property
    def beta(self) -> float:
        return float(self.theta[0])

    @property
    def alpha(self) -> float:
        return float(self.theta[1])

    @property
    def warm(self) -> bool:
        return self.n >= self.warmup

    def update(self, y: float, x: float) -> HedgeOutput:
        """Feed one bar of log prices; returns Z computed BEFORE learning from this bar."""
        y, x = float(y), float(x)
        if not (math.isfinite(y) and math.isfinite(x)):
            raise ValueError("log prices must be finite")
        h = np.array([x, 1.0])
        if self.n == 0:
            # start at beta = 1 with alpha matching the first bar; R unknown yet
            self.theta = np.array([1.0, y - x])
            self.n = 1
            return HedgeOutput(1.0, y - x, 0.0, float("nan"), float("nan"), False)

        r_used = self.r if self.r > 0 else 1e-12
        P_pred = self.P + self.q * r_used
        e = y - float(h @ self.theta)
        hph = float(h @ P_pred @ h)
        s = hph + r_used
        std = math.sqrt(s)
        z = e / std if self.warm else float("nan")
        out = HedgeOutput(float(self.theta[0]), float(self.theta[1]), e, std, z, self.warm)

        # observation-noise estimate (robust)
        sq = e * e
        if self.clip_sigma is not None and self.n > 10 and self.r > 0:
            sq = min(sq, self.clip_sigma ** 2 * s)
        self._sq_sum += sq
        if self.n < self.warmup:
            self.r = self._sq_sum / self.n
        else:
            self.r = (1 - self.alpha_ewm) * self.r + self.alpha_ewm * max(sq - hph, 0.0)
        self.r = max(self.r, 1e-14)

        # state update with the refreshed R
        s_new = hph + self.r
        k = (P_pred @ h) / s_new
        self.theta = self.theta + k * e
        self.P = P_pred - np.outer(k, h @ P_pred)
        self.P = (self.P + self.P.T) / 2.0      # keep it symmetric
        self.n += 1
        return out

    def run(self, y: Iterable[float], x: Iterable[float]) -> pd.DataFrame:
        """Batch helper over aligned log-price sequences."""
        rows = [self.update(a, b) for a, b in zip(y, x)]
        return pd.DataFrame({"beta": [r.beta for r in rows], "alpha": [r.alpha for r in rows],
                             "spread": [r.spread for r in rows], "std": [r.std for r in rows],
                             "z": [r.z for r in rows]})


def log_prices(y_price: float, x_price: float) -> Tuple[float, float]:
    return math.log(y_price), math.log(x_price)
