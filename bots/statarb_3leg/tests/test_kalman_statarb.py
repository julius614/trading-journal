import math

import numpy as np
import pytest

from bots.statarb_3leg.kalman_statarb import KalmanHedgeRatio, spread_pips


def cointegrated(n=4000, beta=0.6, alpha=0.05, noise=2e-4, seed=0):
    rng = np.random.default_rng(seed)
    x = np.log(1.27) + np.cumsum(rng.normal(0, 3e-3, n))
    y = beta * x + alpha + rng.normal(0, noise, n)
    return y, x


def test_recovers_hedge_ratio_and_intercept():
    y, x = cointegrated()
    k = KalmanHedgeRatio(q_beta=1e-4, q_alpha=1e-4, warmup=300)
    k.run(y, x)
    assert k.beta == pytest.approx(0.6, abs=0.05)
    assert k.alpha + k.beta * x[-1] == pytest.approx(y[-1], abs=1e-3)   # fair value


def test_z_is_standardised():
    y, x = cointegrated(seed=1)
    out = KalmanHedgeRatio(warmup=300).run(y, x)
    z = out["z"].dropna()
    assert abs(z.mean()) < 0.1
    assert 0.85 < z.std() < 1.15


def test_z_uses_full_forecast_variance():
    y, x = cointegrated(n=600, seed=2)
    k = KalmanHedgeRatio(warmup=300)
    k.run(y[:-1], x[:-1])
    h = np.array([x[-1], 1.0])
    p_pred = k.P + k.q * k.r
    expected_s = float(h @ p_pred @ h) + k.r
    out = k.update(y[-1], x[-1])
    assert out.std == pytest.approx(math.sqrt(expected_s), rel=1e-9)   # sqrt(H P H' + R)
    assert out.z == pytest.approx(out.spread / out.std, rel=1e-9)
    assert float(h @ p_pred @ h) > 0                                    # P is included


def test_jump_gives_large_z_from_predicted_state():
    y, x = cointegrated(n=1000, seed=3)
    k = KalmanHedgeRatio(warmup=300)
    k.run(y, x)
    beta_before, alpha_before = k.beta, k.alpha
    out = k.update(y[-1] + 50 * 2e-4, x[-1])      # a ~50-sigma move in y alone
    assert out.z > 10
    assert out.beta == beta_before and out.alpha == alpha_before


def test_warmup_then_finite():
    y, x = cointegrated(n=400, seed=4)
    out = KalmanHedgeRatio(warmup=300).run(y, x)
    assert out["z"].iloc[:300].isna().all()
    assert out["z"].iloc[301:].notna().all()


def test_causal():
    y, x = cointegrated(n=800, seed=5)
    a = KalmanHedgeRatio(warmup=300).run(y, x)
    b = KalmanHedgeRatio(warmup=300).run(np.r_[y, 5.0], np.r_[x, 0.0])
    assert np.allclose(a["z"].to_numpy(), b["z"].to_numpy()[:800], equal_nan=True)


def test_outlier_clipping_keeps_later_signals_alive():
    y, x = cointegrated(n=2000, seed=6)
    robust = KalmanHedgeRatio(warmup=300, clip_sigma=4.0)
    naive = KalmanHedgeRatio(warmup=300, clip_sigma=None)
    for f in (robust, naive):
        f.run(y[:1000], x[:1000])
        f.update(y[1000] + 0.05, x[1000])          # a 250-sigma shock
    zr = robust.run(y[1001:1100], x[1001:1100])["z"].abs().mean()
    zn = naive.run(y[1001:1100], x[1001:1100])["z"].abs().mean()
    assert zr > 0.5
    assert zn < zr / 3


def test_spread_pips():
    assert spread_pips(0.001, 1.10) == pytest.approx(11.0)


def test_rejects_bad_input():
    with pytest.raises(ValueError):
        KalmanHedgeRatio(q_beta=0)
    with pytest.raises(ValueError):
        KalmanHedgeRatio().update(float("nan"), 0.1)
