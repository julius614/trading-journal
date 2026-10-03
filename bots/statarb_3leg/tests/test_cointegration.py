import numpy as np
import pytest

from bots.statarb_3leg.cointegration import (adf_test, engle_granger, half_life,
                                             mackinnon_pvalue, stationarity_gate)


def ar1(phi, n=250, seed=0, sd=1.0):
    rng = np.random.default_rng(seed)
    x = np.zeros(n)
    for t in range(1, n):
        x[t] = phi * x[t - 1] + rng.normal(0, sd)
    return x


def test_mackinnon_pvalue_matches_critical_values():
    assert mackinnon_pvalue(-2.86) == pytest.approx(0.05, abs=0.002)   # 5% critical value
    assert mackinnon_pvalue(-3.43) == pytest.approx(0.01, abs=0.002)   # 1%
    assert mackinnon_pvalue(-2.57) == pytest.approx(0.10, abs=0.003)   # 10%
    assert mackinnon_pvalue(5.0) == 1.0 and mackinnon_pvalue(-25.0) == 0.0


def test_mackinnon_cointegration_table_is_stricter():
    # Engle-Granger (N=2) 5% critical value is about -3.34, vs -2.86 for plain ADF
    assert mackinnon_pvalue(-3.34, n_vars=2) == pytest.approx(0.05, abs=0.005)
    assert mackinnon_pvalue(-2.86, n_vars=2) > 0.1


def test_adf_on_strongly_stationary_series():
    assert adf_test(ar1(0.8, seed=1)).pvalue < 0.01


def test_adf_detection_rates():
    stationary = [adf_test(ar1(0.9, seed=s)).pvalue < 0.05 for s in range(30)]
    walks = [adf_test(ar1(1.0, seed=s)).pvalue < 0.05 for s in range(30)]
    assert np.mean(stationary) > 0.8          # power on a half-life ~6.6 bar series
    assert np.mean(walks) < 0.2               # ~5% false positives expected


def test_half_life():
    assert half_life(ar1(0.5 ** (1 / 20), n=5000, seed=3)) == pytest.approx(20, rel=0.25)
    assert half_life(np.cumsum(np.ones(100))) > 1e6          # a trend never reverts


def test_adf_rejects_bad_input():
    with pytest.raises(ValueError):
        adf_test(np.ones(5))
    with pytest.raises(ValueError):
        adf_test(np.ones(100))                # constant series is singular


def test_engle_granger_recovers_beta_and_detects_cointegration():
    rng = np.random.default_rng(4)
    lx = np.log(0.62) + np.cumsum(rng.normal(0, 0.002, 250))
    ly = 0.9 * lx + 0.1 + ar1(0.9, seed=5, sd=5e-4)
    eg = engle_granger(ly, lx)
    assert eg.beta == pytest.approx(0.9, abs=0.1)        # estimated from 250 bars
    assert eg.pvalue < 0.05


def test_stationarity_gate():
    rng = np.random.default_rng(4)
    lx = np.log(0.62) + np.cumsum(rng.normal(0, 0.002, 250))
    good = 0.9 * lx + ar1(0.9, seed=5, sd=5e-4)                   # half-life ~6.6 bars
    ok = stationarity_gate(good, lx, 0.05, 48)
    assert ok.passed and ok.half_life < 48 and ok.beta == pytest.approx(0.9, abs=0.1)
    walk = 0.9 * lx + np.cumsum(rng.normal(0, 5e-4, 250))         # no cointegration
    fail = stationarity_gate(walk, lx, 0.05, 48)
    assert not fail.passed and "not cointegrated" in fail.reason
    slow = 0.9 * lx + ar1(0.98, seed=6, sd=5e-4)                  # half-life ~34 bars
    res = stationarity_gate(slow, lx, 0.99, 20)                   # p ok, half-life too long
    assert not res.passed and "half-life" in res.reason


def test_half_life_handles_tiny_negative_slope():
    x = np.r_[np.zeros(50), np.full(50, 1e-300)]
    assert half_life(x) in (float("inf"), 0.0) or half_life(x) > 0
