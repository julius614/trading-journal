import math

import numpy as np
import pytest

from bots.statarb_3leg.kalman_statarb import (LocalLevelKalman, deviation_pips, log_spread,
                                              synthetic_eurgbp)


def test_log_spread_is_zero_when_triangle_consistent():
    eu, gu = 1.0850, 1.2710
    assert synthetic_eurgbp(eu, gu) == pytest.approx(eu / gu)
    assert log_spread(eu / gu, eu, gu) == pytest.approx(0.0, abs=1e-15)


def test_log_spread_sign_and_size():
    eu, gu = 1.10, 1.27
    eg = eu / gu * math.exp(1e-4)            # actual EURGBP 1 bp rich
    assert log_spread(eg, eu, gu) == pytest.approx(1e-4)
    assert deviation_pips(1e-4, eg) == pytest.approx(eg, rel=1e-9)   # ~0.87 pips


def test_vectorised_spread():
    eu = np.array([1.1, 1.2]); gu = np.array([1.3, 1.25])
    assert np.allclose(log_spread(eu / gu, eu, gu), 0.0)


def test_z_is_nan_during_warmup_then_finite():
    k = LocalLevelKalman(warmup=50)
    rng = np.random.default_rng(0)
    outs = [k.update(x) for x in rng.normal(0, 1e-5, 60)]
    assert all(math.isnan(o.z) for o in outs[:50])
    assert all(math.isfinite(o.z) for o in outs[51:])


def test_z_is_standard_normal_on_white_noise():
    k = LocalLevelKalman(q_ratio=1e-4, r_halflife=200, warmup=200)
    rng = np.random.default_rng(1)
    z = k.run(rng.normal(0, 2e-5, 5000))["z"].dropna()
    assert abs(z.mean()) < 0.1
    assert 0.85 < z.std() < 1.15


def test_jump_gives_large_z_and_uses_predicted_mean():
    k = LocalLevelKalman(q_ratio=1e-4, r_halflife=200, warmup=200)
    rng = np.random.default_rng(2)
    for x in rng.normal(0, 1e-5, 500):
        k.update(x)
    out = k.update(1e-4)                         # a 10-sigma dislocation
    assert out.z > 6
    assert abs(out.mean) < 5e-6                  # the jump itself is not in the mean yet
    assert out.deviation == pytest.approx(1e-4 - out.mean)


def test_mean_tracks_a_slow_level_shift():
    k = LocalLevelKalman(q_ratio=1e-3, r_halflife=200, warmup=100)
    rng = np.random.default_rng(4)
    k.run(rng.normal(0, 1e-5, 300))
    k.run(5e-5 + rng.normal(0, 1e-5, 2000))
    assert k.mean == pytest.approx(5e-5, abs=5e-6)


def test_causal():
    rng = np.random.default_rng(5)
    xs = rng.normal(0, 1e-5, 400)
    a = LocalLevelKalman(warmup=100).run(xs)
    b = LocalLevelKalman(warmup=100).run(np.r_[xs, 1.0])
    assert np.allclose(a["z"].to_numpy(), b["z"].to_numpy()[:400], equal_nan=True)


def test_rejects_bad_input():
    with pytest.raises(ValueError):
        LocalLevelKalman(q_ratio=0)
    with pytest.raises(ValueError):
        LocalLevelKalman().update(float("nan"))


def test_outlier_does_not_mute_later_signals():
    rng = np.random.default_rng(6)
    noise = rng.normal(0, 1e-5, 2000)
    robust = LocalLevelKalman(warmup=200, clip_sigma=4.0)
    naive = LocalLevelKalman(warmup=200, clip_sigma=None)
    for f in (robust, naive):
        f.run(noise[:1000])
        f.update(2e-3)                       # a 200-sigma dislocation
        f.update(0.0)
    z_robust = robust.run(noise[1000:1100])["z"].abs().mean()
    z_naive = naive.run(noise[1000:1100])["z"].abs().mean()
    assert z_robust > 0.6                    # still ~|N(0,1)| ~ 0.8
    assert z_naive < 0.2                     # inflated R squashes ordinary Z-scores
